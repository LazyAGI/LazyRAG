package coreclient

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go.uber.org/zap"

	"github.com/lazyrag/scan_control_plane/internal/config"
	"github.com/lazyrag/scan_control_plane/internal/store"
)

type SubmitResult struct {
	DatasetID    string
	DocumentID   string
	TaskID       string
	UploadFileID string
}

type TaskState struct {
	TaskID    string
	TaskState string
}

type CreateKnowledgeBaseRequest struct {
	Name            string
	AlgoID          string
	AlgoDescription string
	AlgoDisplayName string
	CurrentUserID   string
	CurrentUserName string
}

type CreateKnowledgeBaseResult struct {
	DatasetID string
	Name      string
}

type KnowledgeBaseRef struct {
	DatasetID   string
	Name        string
	ScanManaged bool
}

type Client interface {
	Enabled() bool
	SubmitParseTask(ctx context.Context, task store.PendingTask, stagedPath string, stagedURI string, stagedSize int64) (SubmitResult, error)
	CreateKnowledgeBase(ctx context.Context, req CreateKnowledgeBaseRequest) (CreateKnowledgeBaseResult, error)
	FindKnowledgeBaseByName(ctx context.Context, name, userID, userName string) (KnowledgeBaseRef, bool, error)
	DeleteDataset(ctx context.Context, datasetID, userID, userName string) error
	SearchTasks(ctx context.Context, taskIDs []string) (map[string]TaskState, error)
	SearchTasksByDataset(ctx context.Context, datasetID string, taskIDs []string) (map[string]TaskState, error)
	SearchTasksByDatasetAs(ctx context.Context, datasetID string, taskIDs []string, currentUserID string, currentUserName string) (map[string]TaskState, error)
}

type HTTPError struct {
	StatusCode int
	Body       string
}

func (e *HTTPError) Error() string {
	if e == nil {
		return ""
	}
	return fmt.Sprintf("core returned status=%d body=%s", e.StatusCode, strings.TrimSpace(e.Body))
}

func IsConflictError(err error) bool {
	if err == nil {
		return false
	}
	var httpErr *HTTPError
	if errors.As(err, &httpErr) {
		return httpErr.StatusCode == http.StatusConflict
	}
	msg := strings.ToLower(strings.TrimSpace(err.Error()))
	return strings.Contains(msg, "status=409") || strings.Contains(msg, "already exists")
}

type httpClient struct {
	cfg    config.CoreConfig
	client *http.Client
	log    *zap.Logger
}

func New(cfg config.CoreConfig, log *zap.Logger) Client {
	if !cfg.Enabled {
		return noopClient{}
	}
	if cfg.Timeout <= 0 {
		cfg.Timeout = 60 * time.Second
	}
	if strings.TrimSpace(cfg.StartMode) == "" {
		cfg.StartMode = "ASYNC"
	}
	return &httpClient{
		cfg: cfg,
		client: &http.Client{
			Timeout: cfg.Timeout,
		},
		log: log,
	}
}

type noopClient struct{}

func NewNoop() Client {
	return noopClient{}
}

func (noopClient) Enabled() bool {
	return false
}

func (noopClient) SubmitParseTask(context.Context, store.PendingTask, string, string, int64) (SubmitResult, error) {
	return SubmitResult{}, fmt.Errorf("core client is disabled")
}

func (noopClient) CreateKnowledgeBase(context.Context, CreateKnowledgeBaseRequest) (CreateKnowledgeBaseResult, error) {
	return CreateKnowledgeBaseResult{}, fmt.Errorf("core client is disabled")
}

func (noopClient) FindKnowledgeBaseByName(context.Context, string, string, string) (KnowledgeBaseRef, bool, error) {
	return KnowledgeBaseRef{}, false, nil
}

func (noopClient) DeleteDataset(context.Context, string, string, string) error {
	return fmt.Errorf("core client is disabled")
}

func (noopClient) SearchTasks(context.Context, []string) (map[string]TaskState, error) {
	return map[string]TaskState{}, nil
}

func (noopClient) SearchTasksByDataset(context.Context, string, []string) (map[string]TaskState, error) {
	return map[string]TaskState{}, nil
}

func (noopClient) SearchTasksByDatasetAs(context.Context, string, []string, string, string) (map[string]TaskState, error) {
	return map[string]TaskState{}, nil
}

func (c *httpClient) Enabled() bool {
	return true
}

func (c *httpClient) SubmitParseTask(ctx context.Context, task store.PendingTask, stagedPath string, stagedURI string, _ int64) (SubmitResult, error) {
	datasetID, err := c.resolveDatasetID(task.SourceDatasetID)
	if err != nil {
		return SubmitResult{}, err
	}
	action := store.NormalizeTaskAction(task.TaskAction)
	displayName := filepath.Base(strings.TrimSpace(task.SourceObjectID))
	if displayName == "." || displayName == "" || displayName == string(filepath.Separator) {
		displayName = "staged-file"
	}

	switch action {
	case "DELETE":
		coreDocumentID := strings.TrimSpace(task.CoreDocumentID)
		if coreDocumentID == "" {
			return SubmitResult{}, fmt.Errorf("missing core_document_id for delete task")
		}
		if err := c.deleteDocumentAs(ctx, datasetID, coreDocumentID, task.SourceCreateUserID, task.SourceCreateUserName); err != nil {
			return SubmitResult{}, err
		}
		c.log.Info("deleted core document",
			zap.Int64("scan_task_id", task.TaskID),
			zap.String("core_dataset_id", datasetID),
			zap.String("core_document_id", coreDocumentID),
		)
		return SubmitResult{
			DatasetID:  datasetID,
			DocumentID: coreDocumentID,
		}, nil
	case "REPARSE":
		coreDocumentID := strings.TrimSpace(task.CoreDocumentID)
		if coreDocumentID == "" {
			return SubmitResult{}, fmt.Errorf("missing core_document_id for reparse task")
		}
		path := resolveLocalPath(stagedPath, stagedURI)
		if path == "" {
			return SubmitResult{}, fmt.Errorf("empty staged file path for reparse task")
		}
		targetPath, err := c.getDocumentFileSystemPathAs(ctx, datasetID, coreDocumentID, task.SourceCreateUserID, task.SourceCreateUserName)
		if err != nil {
			return SubmitResult{}, err
		}
		if err := syncFileToTarget(path, targetPath); err != nil {
			return SubmitResult{}, err
		}
		taskPayload := map[string]any{
			"items": []map[string]any{
				{
					"task": map[string]any{
						"task_type":    "TASK_TYPE_REPARSE",
						"document_id":  coreDocumentID,
						"display_name": displayName,
					},
				},
			},
		}
		taskID, documentID, err := c.createTaskAs(ctx, datasetID, taskPayload, task.SourceCreateUserID, task.SourceCreateUserName)
		if err != nil {
			return SubmitResult{}, err
		}
		if strings.TrimSpace(documentID) == "" {
			return SubmitResult{}, fmt.Errorf("empty document_id from core create task")
		}
		if err := c.startTaskAs(ctx, datasetID, taskID, task.SourceCreateUserID, task.SourceCreateUserName); err != nil {
			return SubmitResult{}, err
		}
		c.log.Info("submitted reparse task to core",
			zap.Int64("scan_task_id", task.TaskID),
			zap.String("core_dataset_id", datasetID),
			zap.String("core_document_id", firstNonEmpty(documentID, coreDocumentID)),
			zap.String("core_task_id", taskID),
		)
		return SubmitResult{
			DatasetID:  datasetID,
			DocumentID: firstNonEmpty(documentID, coreDocumentID),
			TaskID:     taskID,
		}, nil
	default:
		path := resolveLocalPath(stagedPath, stagedURI)
		if path == "" {
			return SubmitResult{}, fmt.Errorf("empty staged file path")
		}
		uploadFileID, err := c.uploadFile(ctx, datasetID, path, task)
		if err != nil {
			return SubmitResult{}, err
		}
		taskPayload := map[string]any{
			"items": []map[string]any{
				{
					"upload_file_id": uploadFileID,
					"task": map[string]any{
						"task_type":    "TASK_TYPE_PARSE_UPLOADED",
						"display_name": displayName,
					},
				},
			},
		}
		taskID, documentID, err := c.createTaskAs(ctx, datasetID, taskPayload, task.SourceCreateUserID, task.SourceCreateUserName)
		if err != nil {
			return SubmitResult{}, err
		}
		if err := c.startTaskAs(ctx, datasetID, taskID, task.SourceCreateUserID, task.SourceCreateUserName); err != nil {
			return SubmitResult{}, err
		}
		c.log.Info("submitted parse task to core",
			zap.Int64("scan_task_id", task.TaskID),
			zap.String("core_dataset_id", datasetID),
			zap.String("core_document_id", documentID),
			zap.String("core_task_id", taskID),
			zap.String("upload_file_id", uploadFileID),
		)
		return SubmitResult{
			DatasetID:    datasetID,
			DocumentID:   documentID,
			TaskID:       taskID,
			UploadFileID: uploadFileID,
		}, nil
	}
}

func (c *httpClient) CreateKnowledgeBase(ctx context.Context, req CreateKnowledgeBaseRequest) (CreateKnowledgeBaseResult, error) {
	name := strings.TrimSpace(req.Name)
	if name == "" {
		return CreateKnowledgeBaseResult{}, fmt.Errorf("name is required")
	}
	if strings.TrimSpace(req.AlgoID) == "" {
		return CreateKnowledgeBaseResult{}, fmt.Errorf("algo.algo_id is required")
	}
	currentUserID := strings.TrimSpace(req.CurrentUserID)
	if currentUserID == "" {
		return CreateKnowledgeBaseResult{}, fmt.Errorf("missing current user id")
	}
	virtualUserID, virtualUserName := c.scanVirtualUserFor(currentUserID, req.CurrentUserName)

	payload := map[string]any{
		"display_name": name,
		// Keep scan API contract simple: KB description follows KB name.
		"desc":         name,
		"tags":         []string{"scan"},
		"scan_managed": true,
		"algo": map[string]any{
			"algo_id":      strings.TrimSpace(req.AlgoID),
			"description":  strings.TrimSpace(req.AlgoDescription),
			"display_name": strings.TrimSpace(req.AlgoDisplayName),
		},
	}

	createURL := c.path("/datasets")
	var createResp map[string]any
	if err := c.doJSONAs(ctx, http.MethodPost, createURL, payload, &createResp, virtualUserID, virtualUserName); err != nil {
		return CreateKnowledgeBaseResult{}, err
	}

	datasetID := firstNonEmpty(
		stringFromAny(createResp["dataset_id"]),
		nestedStringFromMap(createResp, "data", "dataset_id"),
	)
	if datasetID == "" {
		return CreateKnowledgeBaseResult{}, fmt.Errorf("core create dataset returned empty dataset_id")
	}

	memberPayload := map[string]any{
		"user_id_list": []string{currentUserID},
		"role": map[string]any{
			"role": "dataset_user",
		},
	}
	if currentUserName := strings.TrimSpace(req.CurrentUserName); currentUserName != "" {
		memberPayload["user_name_list"] = []string{currentUserName}
	}
	var memberResp any
	if err := c.doJSONAs(
		ctx,
		http.MethodPost,
		c.path("/datasets/%s:batchAddMember", datasetID),
		memberPayload,
		&memberResp,
		virtualUserID,
		virtualUserName,
	); err != nil {
		return CreateKnowledgeBaseResult{}, err
	}

	return CreateKnowledgeBaseResult{
		DatasetID: datasetID,
		Name:      firstNonEmpty(name, stringFromAny(createResp["display_name"])),
	}, nil
}

func (c *httpClient) scanVirtualUserFor(currentUserID, currentUserName string) (string, string) {
	return scanVirtualUser(strings.TrimSpace(c.cfg.UserID), strings.TrimSpace(c.cfg.UserName), currentUserID, currentUserName)
}

func scanVirtualUser(baseUserID, baseUserName, currentUserID, currentUserName string) (string, string) {
	currentUserID = strings.TrimSpace(currentUserID)
	baseUserID = strings.TrimSpace(baseUserID)
	if baseUserID == "" {
		baseUserID = "scan-control-plane"
	}
	baseUserName = strings.TrimSpace(baseUserName)
	if baseUserName == "" {
		baseUserName = baseUserID
	}
	if currentUserID == "" {
		return baseUserID, baseUserName
	}
	sum := sha256.Sum256([]byte(currentUserID))
	suffix := hex.EncodeToString(sum[:])[:32]
	virtualUserID := baseUserID + ":" + suffix
	virtualUserName := baseUserName + ":" + suffix
	return virtualUserID, virtualUserName
}

func (c *httpClient) FindKnowledgeBaseByName(ctx context.Context, name, userID, userName string) (KnowledgeBaseRef, bool, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return KnowledgeBaseRef{}, false, fmt.Errorf("name is required")
	}
	userID, userName = c.scanVirtualUserFor(userID, userName)
	listURL := c.path("/datasets") + "?page_size=100&keyword=" + url.QueryEscape(name)
	var resp struct {
		Datasets []struct {
			DatasetID   string   `json:"dataset_id"`
			DisplayName string   `json:"display_name"`
			Tags        []string `json:"tags"`
			ScanManaged bool     `json:"scan_managed"`
		} `json:"datasets"`
	}
	if err := c.doJSONAs(ctx, http.MethodGet, listURL, nil, &resp, userID, userName); err != nil {
		return KnowledgeBaseRef{}, false, err
	}
	for _, item := range resp.Datasets {
		if strings.TrimSpace(item.DisplayName) != name {
			continue
		}
		scanManaged := item.ScanManaged
		for _, tag := range item.Tags {
			if strings.EqualFold(strings.TrimSpace(tag), "scan") {
				scanManaged = true
				break
			}
		}
		return KnowledgeBaseRef{
			DatasetID:   strings.TrimSpace(item.DatasetID),
			Name:        strings.TrimSpace(item.DisplayName),
			ScanManaged: scanManaged,
		}, true, nil
	}
	return KnowledgeBaseRef{}, false, nil
}

func (c *httpClient) DeleteDataset(ctx context.Context, datasetID, userID, userName string) error {
	datasetID = strings.TrimSpace(datasetID)
	if datasetID == "" {
		return fmt.Errorf("dataset_id is required")
	}
	virtualUserID, virtualUserName := c.scanVirtualUserFor(userID, userName)
	err := c.doJSONAs(ctx, http.MethodDelete, c.path("/datasets/%s", url.PathEscape(datasetID)), nil, nil, virtualUserID, virtualUserName)
	if err == nil {
		return nil
	}
	var httpErr *HTTPError
	if errors.As(err, &httpErr) && httpErr.StatusCode == http.StatusNotFound {
		return nil
	}
	return err
}

func (c *httpClient) SearchTasks(ctx context.Context, taskIDs []string) (map[string]TaskState, error) {
	return c.SearchTasksByDataset(ctx, c.cfg.DatasetID, taskIDs)
}

func (c *httpClient) SearchTasksByDataset(ctx context.Context, datasetID string, taskIDs []string) (map[string]TaskState, error) {
	return c.SearchTasksByDatasetAs(ctx, datasetID, taskIDs, "", "")
}

func (c *httpClient) SearchTasksByDatasetAs(ctx context.Context, datasetID string, taskIDs []string, currentUserID, currentUserName string) (map[string]TaskState, error) {
	ids := make([]string, 0, len(taskIDs))
	for _, item := range taskIDs {
		id := strings.TrimSpace(item)
		if id != "" {
			ids = append(ids, id)
		}
	}
	if len(ids) == 0 {
		return map[string]TaskState{}, nil
	}
	payload := map[string]any{
		"task_ids": ids,
	}
	var resp struct {
		Tasks []struct {
			TaskID    string `json:"task_id"`
			TaskState string `json:"task_state"`
		} `json:"tasks"`
	}
	resolvedDatasetID := strings.TrimSpace(datasetID)
	if resolvedDatasetID == "" {
		resolvedDatasetID = c.cfg.DatasetID
	}
	userID, userName := c.scanVirtualUserFor(currentUserID, currentUserName)
	if err := c.doJSONAs(ctx, http.MethodPost, c.path("/datasets/%s/tasks:search", resolvedDatasetID), payload, &resp, userID, userName); err != nil {
		return nil, err
	}
	out := make(map[string]TaskState, len(resp.Tasks))
	for _, task := range resp.Tasks {
		id := strings.TrimSpace(task.TaskID)
		if id == "" {
			continue
		}
		out[id] = TaskState{
			TaskID:    id,
			TaskState: strings.TrimSpace(task.TaskState),
		}
	}
	return out, nil
}

func (c *httpClient) uploadFile(ctx context.Context, datasetID string, stagedPath string, task store.PendingTask) (string, error) {
	file, err := os.Open(stagedPath)
	if err != nil {
		return "", fmt.Errorf("open staged file failed: %w", err)
	}
	defer file.Close()

	fileName := filepath.Base(strings.TrimSpace(task.SourceObjectID))
	if fileName == "." || fileName == "" || fileName == string(filepath.Separator) {
		fileName = filepath.Base(stagedPath)
	}

	pr, pw := io.Pipe()
	writer := multipart.NewWriter(pw)
	writeErrCh := make(chan error, 1)
	go func() {
		writeMultipartBody(writeErrCh, pw, writer, fileName, file)
	}()

	url := c.path("/datasets/%s/uploads", datasetID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, pr)
	if err != nil {
		_ = pr.CloseWithError(err)
		_ = <-writeErrCh
		return "", err
	}
	req.Header.Set("Content-Type", writer.FormDataContentType())
	userID, userName := c.scanVirtualUserFor(task.SourceCreateUserID, task.SourceCreateUserName)
	c.setAuthHeaders(req.Header, userID, userName)

	httpResp, err := c.client.Do(req)
	if err != nil {
		_ = pr.CloseWithError(err)
		_ = <-writeErrCh
		return "", fmt.Errorf("upload to core failed: %w", err)
	}
	defer httpResp.Body.Close()
	writeErr := <-writeErrCh
	if writeErr != nil && !isIgnorableUploadPipeError(writeErr) {
		return "", fmt.Errorf("stream staged file failed: %w", writeErr)
	}
	if httpResp.StatusCode >= 400 {
		body, _ := io.ReadAll(httpResp.Body)
		return "", fmt.Errorf("core upload failed: status=%d body=%s", httpResp.StatusCode, strings.TrimSpace(string(body)))
	}
	var resp struct {
		Files []struct {
			UploadFileID string `json:"upload_file_id"`
		} `json:"files"`
	}
	if err := json.NewDecoder(httpResp.Body).Decode(&resp); err != nil {
		return "", fmt.Errorf("decode upload response failed: %w", err)
	}
	if len(resp.Files) == 0 || strings.TrimSpace(resp.Files[0].UploadFileID) == "" {
		return "", fmt.Errorf("empty upload_file_id from core")
	}
	return strings.TrimSpace(resp.Files[0].UploadFileID), nil
}

func writeMultipartBody(writeErrCh chan<- error, pw *io.PipeWriter, writer *multipart.Writer, fileName string, file *os.File) {
	defer close(writeErrCh)
	part, err := writer.CreateFormFile("files", fileName)
	if err != nil {
		_ = pw.CloseWithError(err)
		writeErrCh <- err
		return
	}
	if _, err := io.Copy(part, file); err != nil {
		_ = pw.CloseWithError(err)
		writeErrCh <- err
		return
	}
	if err := writer.Close(); err != nil {
		_ = pw.CloseWithError(err)
		writeErrCh <- err
		return
	}
	writeErrCh <- pw.Close()
}

func isIgnorableUploadPipeError(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, io.ErrClosedPipe) {
		return true
	}
	msg := strings.ToLower(strings.TrimSpace(err.Error()))
	return strings.Contains(msg, "broken pipe") || strings.Contains(msg, "closed pipe")
}

func (c *httpClient) createTask(ctx context.Context, datasetID string, payload map[string]any) (string, string, error) {
	return c.createTaskAs(ctx, datasetID, payload, "", "")
}

func (c *httpClient) createTaskAs(ctx context.Context, datasetID string, payload map[string]any, currentUserID, currentUserName string) (string, string, error) {
	var resp struct {
		Tasks []struct {
			TaskID     string `json:"task_id"`
			DocumentID string `json:"document_id"`
		} `json:"tasks"`
	}
	userID, userName := c.scanVirtualUserFor(currentUserID, currentUserName)
	if err := c.doJSONAs(ctx, http.MethodPost, c.path("/datasets/%s/tasks", datasetID), payload, &resp, userID, userName); err != nil {
		return "", "", err
	}
	if len(resp.Tasks) == 0 || strings.TrimSpace(resp.Tasks[0].TaskID) == "" {
		return "", "", fmt.Errorf("empty task_id from core create task")
	}
	return strings.TrimSpace(resp.Tasks[0].TaskID), strings.TrimSpace(resp.Tasks[0].DocumentID), nil
}

func (c *httpClient) startTask(ctx context.Context, datasetID string, taskID string) error {
	return c.startTaskAs(ctx, datasetID, taskID, "", "")
}

func (c *httpClient) startTaskAs(ctx context.Context, datasetID string, taskID string, currentUserID, currentUserName string) error {
	payload := map[string]any{
		"task_ids":   []string{taskID},
		"start_mode": c.cfg.StartMode,
	}
	var resp any
	userID, userName := c.scanVirtualUserFor(currentUserID, currentUserName)
	return c.doJSONAs(ctx, http.MethodPost, c.path("/datasets/%s/tasks:start", datasetID), payload, &resp, userID, userName)
}

func (c *httpClient) resolveDatasetID(sourceDatasetID string) (string, error) {
	if v := strings.TrimSpace(sourceDatasetID); v != "" {
		return v, nil
	}
	if v := strings.TrimSpace(c.cfg.DatasetID); v != "" {
		return v, nil
	}
	return "", fmt.Errorf("missing dataset_id: source.dataset_id and core.dataset_id are both empty")
}

func resolveLocalPath(stagedPath, stagedURI string) string {
	path := strings.TrimSpace(stagedPath)
	if path == "" && strings.HasPrefix(strings.TrimSpace(stagedURI), "file://") {
		path = strings.TrimPrefix(strings.TrimSpace(stagedURI), "file://")
	}
	return strings.TrimSpace(path)
}

func (c *httpClient) deleteDocument(ctx context.Context, datasetID, documentID string) error {
	return c.deleteDocumentAs(ctx, datasetID, documentID, "", "")
}

func (c *httpClient) deleteDocumentAs(ctx context.Context, datasetID, documentID string, currentUserID, currentUserName string) error {
	url := c.path("/datasets/%s/documents/%s", datasetID, documentID)
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	userID, userName := c.scanVirtualUserFor(currentUserID, currentUserName)
	c.setAuthHeaders(req.Header, userID, userName)

	httpResp, err := c.client.Do(req)
	if err != nil {
		return fmt.Errorf("call core delete document failed: %w", err)
	}
	defer httpResp.Body.Close()
	if httpResp.StatusCode == http.StatusNotFound {
		return nil
	}
	if httpResp.StatusCode >= 400 {
		raw, _ := io.ReadAll(httpResp.Body)
		return fmt.Errorf("core delete document returned status=%d body=%s", httpResp.StatusCode, strings.TrimSpace(string(raw)))
	}
	return nil
}

func (c *httpClient) getDocumentFileSystemPath(ctx context.Context, datasetID, documentID string) (string, error) {
	return c.getDocumentFileSystemPathAs(ctx, datasetID, documentID, "", "")
}

func (c *httpClient) getDocumentFileSystemPathAs(ctx context.Context, datasetID, documentID string, currentUserID, currentUserName string) (string, error) {
	var resp struct {
		FileSystemPath string `json:"file_system_path"`
	}
	userID, userName := c.scanVirtualUserFor(currentUserID, currentUserName)
	if err := c.doJSONAs(ctx, http.MethodGet, c.path("/datasets/%s/documents/%s", datasetID, documentID), nil, &resp, userID, userName); err != nil {
		return "", err
	}
	targetPath := strings.TrimSpace(resp.FileSystemPath)
	if targetPath == "" {
		return "", fmt.Errorf("core document file_system_path is empty")
	}
	return targetPath, nil
}

func syncFileToTarget(srcPath, targetPath string) error {
	srcPath = strings.TrimSpace(srcPath)
	targetPath = strings.TrimSpace(targetPath)
	if srcPath == "" || targetPath == "" {
		return fmt.Errorf("source/target path is empty")
	}
	srcInfo, err := os.Stat(srcPath)
	if err != nil {
		return fmt.Errorf("stat staged file failed: %w", err)
	}
	if srcInfo.IsDir() {
		return fmt.Errorf("staged file path is a directory")
	}
	if err := os.MkdirAll(filepath.Dir(targetPath), 0o755); err != nil {
		return fmt.Errorf("mkdir target dir failed: %w", err)
	}
	in, err := os.Open(srcPath)
	if err != nil {
		return fmt.Errorf("open staged file failed: %w", err)
	}
	defer in.Close()
	tmp, err := os.CreateTemp(filepath.Dir(targetPath), ".scan-reparse-*")
	if err != nil {
		return fmt.Errorf("create temp target failed: %w", err)
	}
	tmpPath := tmp.Name()
	cleanup := func() {
		_ = tmp.Close()
		_ = os.Remove(tmpPath)
	}
	if _, err := io.Copy(tmp, in); err != nil {
		cleanup()
		return fmt.Errorf("copy staged file to temp target failed: %w", err)
	}
	if err := tmp.Sync(); err != nil {
		cleanup()
		return fmt.Errorf("sync temp target failed: %w", err)
	}
	if err := tmp.Close(); err != nil {
		_ = os.Remove(tmpPath)
		return fmt.Errorf("close temp target failed: %w", err)
	}
	if err := os.Rename(tmpPath, targetPath); err != nil {
		_ = os.Remove(tmpPath)
		return fmt.Errorf("replace target file failed: %w", err)
	}
	if err := os.Chtimes(targetPath, srcInfo.ModTime(), srcInfo.ModTime()); err != nil {
		return fmt.Errorf("set target mtime failed: %w", err)
	}
	return nil
}

func (c *httpClient) doJSON(ctx context.Context, method, url string, payload any, out any) error {
	return c.doJSONAs(ctx, method, url, payload, out, c.cfg.UserID, c.cfg.UserName)
}

func (c *httpClient) doJSONAs(ctx context.Context, method, url string, payload any, out any, userID, userName string) error {
	var body io.Reader
	if payload != nil {
		data, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		body = bytes.NewReader(data)
	}
	req, err := http.NewRequestWithContext(ctx, method, url, body)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	c.setAuthHeaders(req.Header, userID, userName)

	httpResp, err := c.client.Do(req)
	if err != nil {
		return fmt.Errorf("call core failed: %w", err)
	}
	defer httpResp.Body.Close()
	if httpResp.StatusCode >= 400 {
		raw, _ := io.ReadAll(httpResp.Body)
		return &HTTPError{StatusCode: httpResp.StatusCode, Body: strings.TrimSpace(string(raw))}
	}
	if out == nil {
		return nil
	}
	if err := json.NewDecoder(httpResp.Body).Decode(out); err != nil && err != io.EOF {
		return fmt.Errorf("decode core response failed: %w", err)
	}
	return nil
}

func (c *httpClient) setAuthHeaders(h http.Header, userID, userName string) {
	h.Set("X-User-Id", firstNonEmpty(strings.TrimSpace(userID), c.cfg.UserID))
	h.Set("X-User-Name", firstNonEmpty(strings.TrimSpace(userName), c.cfg.UserName))
	if token := strings.TrimSpace(c.cfg.AuthToken); token != "" {
		h.Set("Authorization", "Bearer "+token)
	}
}

func (c *httpClient) path(format string, args ...any) string {
	base := strings.TrimRight(strings.TrimSpace(c.cfg.Endpoint), "/")
	return base + fmt.Sprintf(format, args...)
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func stringFromAny(v any) string {
	switch vv := v.(type) {
	case string:
		return strings.TrimSpace(vv)
	default:
		return ""
	}
}

func nestedStringFromMap(root map[string]any, firstKey, secondKey string) string {
	if root == nil {
		return ""
	}
	raw, ok := root[firstKey]
	if !ok {
		return ""
	}
	next, ok := raw.(map[string]any)
	if !ok {
		return ""
	}
	return stringFromAny(next[secondKey])
}
