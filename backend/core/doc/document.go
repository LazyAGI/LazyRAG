package doc

import (
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"mime"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"lazyrag/core/acl"
	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/common/readonlyorm"
	"lazyrag/core/log"
	"lazyrag/core/store"

	"github.com/gorilla/mux"
)

// DocumentService implements document APIs by joining:
// - schema A (core-owned diff): orm.documents / orm.tasks
// - schema B (readonly, maintained by lazy-llm-server): lazy_llm_server.lazyllm_*

const externalDeleteFailedMessage = "textDeleteFailed，text"

func requireDatasetPermission(r *http.Request, datasetID string, action string) (*orm.Dataset, string, bool) {
	userID := strings.TrimSpace(store.UserID(r))
	if userID == "" {
		return nil, userID, false
	}
	var ds orm.Dataset
	if err := store.DB().WithContext(r.Context()).
		Where("id = ? AND deleted_at IS NULL", datasetID).
		First(&ds).Error; err != nil {
		return nil, userID, false
	}
	if !canAccessDataset(&ds, userID, action) {
		return &ds, userID, false
	}
	return &ds, userID, true
}

func replyDatasetForbidden(w http.ResponseWriter) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusForbidden)
	_, _ = w.Write([]byte(common.ForbiddenBody))
}

func publicBaseURL() string {
	if v := strings.TrimSpace(os.Getenv("LAZYRAG_PUBLIC_BASE_URL")); v != "" {
		return strings.TrimRight(v, "/")
	}
	return "http://localhost:8000/api/core"
}

func absoluteCoreURL(path string) string {
	p := strings.TrimSpace(path)
	if p == "" {
		return ""
	}
	if strings.HasPrefix(p, "/") {
		return p
	}
	return "/" + p
}

func signedFileSecret() string {
	if v := strings.TrimSpace(os.Getenv("LAZYRAG_FILE_URL_SIGN_SECRET")); v != "" {
		return v
	}
	return "lazyrag-file-url-secret"
}

func signedFileExpireSeconds() int64 {
	if v := strings.TrimSpace(os.Getenv("LAZYRAG_FILE_URL_EXPIRE_SECONDS")); v != "" {
		if n, err := strconv.ParseInt(v, 10, 64); err == nil && n > 0 {
			return n
		}
	}
	return 3600
}

func fileRelativePath(fullPath string) string {
	p := strings.TrimSpace(fullPath)
	if p == "" {
		return ""
	}
	cleanPath := filepath.Clean(p)
	roots := []string{strings.TrimSpace(uploadRoot())}
	for _, root := range roots {
		if root == "" {
			continue
		}
		cleanRoot := filepath.Clean(root)
		rel, err := filepath.Rel(cleanRoot, cleanPath)
		if err != nil || rel == "." || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
			continue
		}
		return filepath.ToSlash(rel)
	}
	return ""
}

func signStaticFile(rel string, expires int64) string {
	mac := hmac.New(sha256.New, []byte(signedFileSecret()))
	_, _ = mac.Write([]byte(rel))
	_, _ = mac.Write([]byte("\n"))
	_, _ = mac.Write([]byte(strconv.FormatInt(expires, 10)))
	return hex.EncodeToString(mac.Sum(nil))
}

func staticFileURLFromFullPath(fullPath string) string {
	rel := fileRelativePath(fullPath)
	if rel == "" {
		return ""
	}
	expires := time.Now().UTC().Unix() + signedFileExpireSeconds()
	sig := signStaticFile(rel, expires)
	return fmt.Sprintf("/static-files/%s?expires=%d&sig=%s", encodeStaticFilePath(rel), expires, sig)
}

func encodeStaticFilePath(rel string) string {
	parts := strings.Split(rel, "/")
	for i, part := range parts {
		parts[i] = url.PathEscape(part)
	}
	return strings.Join(parts, "/")
}

func documentContentPath(datasetID, docID string) string {
	return absoluteCoreURL(fmt.Sprintf("/datasets/%s/documents/%s:content", datasetID, docID))
}

func documentDownloadPath(datasetID, docID string) string {
	return absoluteCoreURL(fmt.Sprintf("/datasets/%s/documents/%s:download", datasetID, docID))
}

func uploadedFileContentPath(datasetID, uploadFileID string) string {
	return absoluteCoreURL(fmt.Sprintf("/datasets/%s/uploads/%s:content", datasetID, uploadFileID))
}

func uploadedFileDownloadPath(datasetID, uploadFileID string) string {
	return absoluteCoreURL(fmt.Sprintf("/datasets/%s/uploads/%s:download", datasetID, uploadFileID))
}

func setDocumentURI(doc *Doc) {
	if doc == nil {
		return
	}
	if strings.TrimSpace(doc.DocumentID) == "" || strings.TrimSpace(doc.DatasetID) == "" {
		return
	}
	doc.URI = documentContentPath(doc.DatasetID, doc.DocumentID)
}

func streamLocalFile(w http.ResponseWriter, fullPath, filename, fallbackContentType string, inline bool) {
	cleanPath := filepath.Clean(strings.TrimSpace(fullPath))
	root := filepath.Clean(uploadRoot())
	rel, relErr := filepath.Rel(root, cleanPath)
	if cleanPath == "" || relErr != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		common.ReplyErr(w, "file path is invalid", http.StatusBadRequest)
		return
	}
	f, err := os.Open(cleanPath)
	if err != nil {
		if os.IsNotExist(err) {
			common.ReplyErr(w, "file not found", http.StatusNotFound)
			return
		}
		common.ReplyErr(w, "open file failed", http.StatusInternalServerError)
		return
	}
	defer f.Close()
	stat, err := f.Stat()
	if err != nil {
		common.ReplyErr(w, "read file failed", http.StatusInternalServerError)
		return
	}
	name := strings.TrimSpace(filename)
	if name == "" {
		name = filepath.Base(cleanPath)
	}
	contentType := detectDocumentContentType(name, cleanPath, fallbackContentType)
	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Content-Length", strconv.FormatInt(stat.Size(), 10))
	w.Header().Set("Cache-Control", "private, max-age=300")
	w.Header().Del("ETag")
	w.Header().Del("Last-Modified")
	if inline {
		w.Header().Set("Content-Disposition", `inline; filename="preview.pdf"`)
	} else {
		w.Header().Set("Content-Disposition", fmt.Sprintf("attachment; filename=%q", name))
	}
	w.WriteHeader(http.StatusOK)
	_, _ = io.Copy(w, f)
}

func GetSignedStaticFile(w http.ResponseWriter, r *http.Request) {
	rawPath := strings.TrimSpace(common.PathVar(r, "path"))
	if rawPath == "" {
		common.ReplyErr(w, "missing path", http.StatusBadRequest)
		return
	}
	decodedPath, err := url.PathUnescape(rawPath)
	if err != nil {
		common.ReplyErr(w, "invalid path encoding", http.StatusBadRequest)
		return
	}
	relPath := strings.TrimPrefix(filepath.ToSlash(filepath.Clean("/"+decodedPath)), "/")
	if relPath == "" || relPath == "." || strings.HasPrefix(relPath, "../") {
		common.ReplyErr(w, "invalid path", http.StatusBadRequest)
		return
	}
	expiresStr := strings.TrimSpace(r.URL.Query().Get("expires"))
	sig := strings.TrimSpace(r.URL.Query().Get("sig"))
	if expiresStr == "" || sig == "" {
		common.ReplyErr(w, "missing signature", http.StatusForbidden)
		return
	}
	expires, err := strconv.ParseInt(expiresStr, 10, 64)
	if err != nil || expires <= 0 || time.Now().UTC().Unix() > expires {
		common.ReplyErr(w, "url expired", http.StatusForbidden)
		return
	}
	expected := signStaticFile(relPath, expires)
	if !hmac.Equal([]byte(sig), []byte(expected)) {
		common.ReplyErr(w, "invalid signature", http.StatusForbidden)
		return
	}
	fullPath := filepath.Join(uploadRoot(), filepath.FromSlash(relPath))
	streamLocalFile(w, fullPath, filepath.Base(fullPath), "", true)
}

func detectDocumentContentType(name, storedPath, fallback string) string {
	if v := strings.TrimSpace(fallback); v != "" {
		return v
	}
	if ext := strings.TrimSpace(filepath.Ext(name)); ext != "" {
		if ct := mime.TypeByExtension(strings.ToLower(ext)); ct != "" {
			return ct
		}
	}
	if ext := strings.TrimSpace(filepath.Ext(storedPath)); ext != "" {
		if ct := mime.TypeByExtension(strings.ToLower(ext)); ct != "" {
			return ct
		}
	}
	return "application/octet-stream"
}

func loadDocumentFileMeta(ctx context.Context, datasetID, docID string) (orm.Document, documentExt, error) {
	var row orm.Document
	if err := store.DB().WithContext(ctx).Where("id = ? AND dataset_id = ? AND deleted_at IS NULL", docID, datasetID).Take(&row).Error; err != nil {
		return orm.Document{}, documentExt{}, err
	}
	var ext documentExt
	_ = json.Unmarshal(row.Ext, &ext)
	return row, ext, nil
}

func streamDocumentFile(w http.ResponseWriter, r *http.Request, inline bool) {
	datasetID := datasetIDFromPath(r)
	docID := documentIDFromPath(r)
	if datasetID == "" || docID == "" {
		common.ReplyErr(w, "missing dataset or document", http.StatusBadRequest)
		return
	}
	if _, userID, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetRead); !ok {
		if userID == "" {
			common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		} else {
			replyDatasetForbidden(w)
		}
		return
	}
	row, ext, err := loadDocumentFileMeta(r.Context(), datasetID, docID)
	if err != nil {
		common.ReplyErr(w, "document not found", http.StatusNotFound)
		return
	}
	storedPath := previewPathForContent(ext)
	if storedPath == "" {
		common.ReplyErr(w, "document file not found", http.StatusNotFound)
		return
	}
	filename := previewFilenameForContent(ext)
	if filename == "" {
		filename = strings.TrimSpace(row.DisplayName)
	}
	streamLocalFile(w, storedPath, filename, previewContentTypeForContent(ext), inline)
}

func GetDocumentContent(w http.ResponseWriter, r *http.Request) {
	streamDocumentFile(w, r, true)
}

func DownloadDocument(w http.ResponseWriter, r *http.Request) {
	streamDocumentFile(w, r, false)
}

func GetUploadedFileContent(w http.ResponseWriter, r *http.Request) {
	streamUploadedFile(w, r, true)
}

func DownloadUploadedFile(w http.ResponseWriter, r *http.Request) {
	streamUploadedFile(w, r, false)
}

func ListDocuments(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	if datasetID == "" {
		common.ReplyErr(w, "missing dataset", http.StatusBadRequest)
		return
	}
	if _, userID, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetRead); !ok {
		if userID == "" {
			common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		} else {
			replyDatasetForbidden(w)
		}
		return
	}

	q := r.URL.Query()
	pageToken := strings.TrimSpace(q.Get("page_token"))
	pageSizeStr := strings.TrimSpace(q.Get("page_size"))
	pid := firstNonEmpty(
		strings.TrimSpace(q.Get("p_id")),
		strings.TrimSpace(q.Get("document_pid")),
		strings.TrimSpace(q.Get("pid")),
		parseDocumentPIDFromParentName(strings.TrimSpace(q.Get("parent"))),
	)

	pageSize := 20
	if pageSizeStr != "" {
		if v, err := strconv.Atoi(pageSizeStr); err == nil && v > 0 {
			pageSize = v
		}
	}
	if pageSize > 1000 {
		pageSize = 1000
	}
	offset := 0
	if pageToken != "" {
		if v, err := strconv.Atoi(pageToken); err == nil && v >= 0 {
			offset = v
		}
	}

	rows, total, err := loadDatasetDocuments(r.Context(), datasetID, "", pid, true, pageSize, offset)
	if err != nil {
		common.ReplyErr(w, "query documents failed", http.StatusInternalServerError)
		return
	}

	next := ""
	if offset+len(rows) < int(total) {
		next = strconv.Itoa(offset + len(rows))
	}

	relPaths := buildDocumentTreeRelPaths(r.Context(), rows)
	out := make([]Doc, 0, len(rows))
	for _, rr := range rows {
		rr.RelPath = relPaths[rr.DocID]
		doc := docFromRow(rr)
		setDocumentURI(&doc)
		out = append(out, doc)
	}
	common.ReplyJSON(w, ListDocumentsResponse{Documents: out, TotalSize: int32(total), NextPageToken: next})
}
func CreateDocument(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	if datasetID == "" {
		common.ReplyErr(w, "missing dataset", http.StatusBadRequest)
		return
	}
	userID := store.UserID(r)
	userName := store.UserName(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	if _, _, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetUpload); !ok {
		replyDatasetForbidden(w)
		return
	}

	docID := strings.TrimSpace(r.URL.Query().Get("document_id"))
	if docID == "" {
		docID = newDocID()
	}

	var body Doc
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	display := strings.TrimSpace(body.DisplayName)
	if display == "" {
		display = docID
	}
	pid := strings.TrimSpace(body.PID)
	fileID := strings.TrimSpace(body.FileID)
	tagsBytes, _ := json.Marshal(body.Tags)
	now := time.Now().UTC()

	row := orm.Document{
		ID:           docID,
		LazyllmDocID: "",
		DatasetID:    datasetID,
		DisplayName:  display,
		PID:          pid,
		Tags:         tagsBytes,
		FileID:       fileID,
		Ext:          json.RawMessage(`{}`),
		BaseModel: orm.BaseModel{
			CreateUserID:   userID,
			CreateUserName: userName,
			CreatedAt:      now,
			UpdatedAt:      now,
		},
	}
	if err := store.DB().WithContext(r.Context()).Create(&row).Error; err != nil {
		common.ReplyErr(w, "create document failed", http.StatusInternalServerError)
		return
	}

	common.ReplyJSON(w, docFromRow(mergedDocRow{
		DocID:         docID,
		DatasetID:     datasetID,
		DisplayName:   display,
		PID:           pid,
		Tags:          tagsBytes,
		FileID:        fileID,
		Creator:       userName,
		BaseCreatedAt: now,
		BaseUpdatedAt: now,
	}))
}
func GetDocument(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	docID := documentIDFromPath(r)
	if datasetID == "" || docID == "" {
		common.ReplyErr(w, "missing dataset or document", http.StatusBadRequest)
		return
	}
	if _, userID, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetRead); !ok {
		if userID == "" {
			common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		} else {
			replyDatasetForbidden(w)
		}
		return
	}

	rr, err := loadDocumentByID(r.Context(), datasetID, docID)
	if err != nil {
		common.ReplyErr(w, "document not found", http.StatusNotFound)
		return
	}
	doc := docFromRow(rr)
	setDocumentURI(&doc)
	common.ReplyJSON(w, doc)
}
func DeleteDocument(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	docID := documentIDFromPath(r)
	userID := store.UserID(r)
	if datasetID == "" || docID == "" {
		common.ReplyErr(w, "missing dataset or document", http.StatusBadRequest)
		return
	}
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	if _, _, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetWrite); !ok {
		replyDatasetForbidden(w)
		return
	}
	var row orm.Document
	if err := store.DB().WithContext(r.Context()).Where("id = ? AND dataset_id = ? AND deleted_at IS NULL", docID, datasetID).Take(&row).Error; err != nil {
		common.ReplyErr(w, "document not found", http.StatusNotFound)
		return
	}
	if err := deleteExternalDocs(r, datasetID, []orm.Document{row}); err != nil {
		common.ReplyErr(w, externalDeleteFailedMessage, http.StatusBadGateway)
		return
	}
	now := time.Now().UTC()
	if err := store.DB().WithContext(r.Context()).
		Model(&orm.Document{}).
		Where("id = ? AND dataset_id = ? AND deleted_at IS NULL", docID, datasetID).
		Updates(map[string]any{"deleted_at": now, "updated_at": now}).Error; err != nil {
		common.ReplyErr(w, "Delete documentFailed，text", http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)
}
func UpdateDocument(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	docID := documentIDFromPath(r)
	userID := store.UserID(r)
	userName := store.UserName(r)
	if datasetID == "" || docID == "" {
		common.ReplyErr(w, "missing dataset or document", http.StatusBadRequest)
		return
	}
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	if _, _, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetWrite); !ok {
		replyDatasetForbidden(w)
		return
	}
	var body Doc
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	updates := map[string]any{}
	if s := strings.TrimSpace(body.DisplayName); s != "" {
		updates["display_name"] = s
	}
	if s := strings.TrimSpace(body.PID); s != "" {
		updates["p_id"] = s
	}
	if body.Tags != nil {
		b, _ := json.Marshal(body.Tags)
		updates["tags"] = b
	}
	if s := strings.TrimSpace(body.FileID); s != "" {
		updates["file_id"] = s
	}
	now := time.Now().UTC()
	updates["updated_at"] = now

	db := store.DB().WithContext(r.Context())
	var cd orm.Document
	err := db.Where("id = ? AND dataset_id = ?", docID, datasetID).Take(&cd).Error
	if err != nil {
		row := orm.Document{
			ID:           docID,
			LazyllmDocID: "",
			DatasetID:    datasetID,
			DisplayName:  strings.TrimSpace(body.DisplayName),
			PID:          strings.TrimSpace(body.PID),
			FileID:       strings.TrimSpace(body.FileID),
			Tags:         func() []byte { b, _ := json.Marshal(body.Tags); return b }(),
			Ext:          json.RawMessage(`{}`),
			BaseModel: orm.BaseModel{
				CreateUserID:   userID,
				CreateUserName: userName,
				CreatedAt:      now,
				UpdatedAt:      now,
			},
		}
		if err := db.Create(&row).Error; err != nil {
			common.ReplyErr(w, "update document failed", http.StatusInternalServerError)
			return
		}
		common.ReplyJSON(w, docFromRow(mergedDocRow{
			DocID:         docID,
			DatasetID:     datasetID,
			DisplayName:   row.DisplayName,
			PID:           row.PID,
			Tags:          row.Tags,
			FileID:        row.FileID,
			Creator:       userName,
			BaseCreatedAt: now,
			BaseUpdatedAt: now,
		}))
		return
	}
	if err := db.Model(&orm.Document{}).Where("id = ? AND deleted_at IS NULL", cd.ID).Updates(updates).Error; err != nil {
		common.ReplyErr(w, "update document failed", http.StatusInternalServerError)
		return
	}
	// return refreshed
	r2 := r.Clone(r.Context())
	mux.Vars(r2)["document"] = docID
	GetDocument(w, r2)
}
func SearchDocuments(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	if datasetID == "" {
		common.ReplyErr(w, "missing dataset", http.StatusBadRequest)
		return
	}
	if _, userID, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetRead); !ok {
		if userID == "" {
			common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		} else {
			replyDatasetForbidden(w)
		}
		return
	}
	var req SearchDocumentsRequest
	if r.Body != nil {
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil && err.Error() != "EOF" {
			common.ReplyErr(w, "invalid body", http.StatusBadRequest)
			return
		}
	}

	pageSize := req.PageSize
	if pageSize <= 0 {
		pageSize = 20
	}
	if pageSize > 1000 {
		pageSize = 1000
	}
	offset := 0
	if strings.TrimSpace(req.PageToken) != "" {
		if v, err := strconv.Atoi(strings.TrimSpace(req.PageToken)); err == nil && v >= 0 {
			offset = v
		}
	}
	keyword := strings.TrimSpace(req.Keyword)
	pid := firstNonEmpty(strings.TrimSpace(req.PID), parseDocumentPIDFromParentName(strings.TrimSpace(req.Parent)))

	rows, total, err := loadDatasetDocuments(r.Context(), datasetID, keyword, pid, true, int(pageSize), offset)
	if err != nil {
		common.ReplyErr(w, "search documents failed", http.StatusInternalServerError)
		return
	}
	relPaths := buildDocumentTreeRelPaths(r.Context(), rows)
	out := make([]Doc, 0, len(rows))
	for _, rr := range rows {
		rr.RelPath = relPaths[rr.DocID]
		doc := docFromRow(rr)
		setDocumentURI(&doc)
		out = append(out, doc)
	}
	next := ""
	if offset+len(rows) < int(total) {
		next = strconv.Itoa(offset + len(rows))
	}
	common.ReplyJSON(w, ListDocumentsResponse{Documents: out, TotalSize: int32(total), NextPageToken: next})
}
func SearchAllDocuments(w http.ResponseWriter, r *http.Request) {
	userID := strings.TrimSpace(store.UserID(r))
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	var req SearchDocumentsRequest
	if r.Body != nil {
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil && err.Error() != "EOF" {
			common.ReplyErr(w, "invalid body", http.StatusBadRequest)
			return
		}
	}
	keyword := strings.TrimSpace(req.Keyword)
	if keyword == "" {
		common.ReplyJSON(w, ListDocumentsResponse{Documents: []Doc{}, TotalSize: 0, NextPageToken: ""})
		return
	}
	pageSize := req.PageSize
	if pageSize <= 0 {
		pageSize = 20
	}
	if pageSize > 1000 {
		pageSize = 1000
	}

	rows, err := searchAllDocumentsMerged(r.Context(), keyword, int(pageSize))
	if err != nil {
		common.ReplyErr(w, "search documents failed", http.StatusInternalServerError)
		return
	}
	relPaths := buildDocumentTreeRelPaths(r.Context(), rows)
	out := make([]Doc, 0, len(rows))
	for _, rr := range rows {
		if !canAccessDataset(&orm.Dataset{ID: rr.DatasetID}, userID, acl.PermissionDatasetRead) {
			continue
		}
		rr.RelPath = relPaths[rr.DocID]
		doc := docFromRow(rr)
		setDocumentURI(&doc)
		out = append(out, doc)
	}
	common.ReplyJSON(w, ListDocumentsResponse{Documents: out, TotalSize: int32(len(out)), NextPageToken: ""})
}
func BatchDeleteDocument(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	userID := store.UserID(r)
	if datasetID == "" {
		common.ReplyErr(w, "missing dataset", http.StatusBadRequest)
		return
	}
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	if _, _, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetWrite); !ok {
		replyDatasetForbidden(w)
		return
	}
	var req BatchDeleteDocumentRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if len(req.Names) == 0 {
		w.WriteHeader(http.StatusOK)
		return
	}
	var rows []orm.Document
	if err := store.DB().WithContext(r.Context()).Where("dataset_id = ? AND id IN ? AND deleted_at IS NULL", datasetID, req.Names).Find(&rows).Error; err != nil {
		common.ReplyErr(w, "query documents failed", http.StatusInternalServerError)
		return
	}
	if err := deleteExternalDocs(r, datasetID, rows); err != nil {
		common.ReplyErr(w, externalDeleteFailedMessage, http.StatusBadGateway)
		return
	}
	now := time.Now().UTC()
	if err := store.DB().WithContext(r.Context()).
		Model(&orm.Document{}).
		Where("dataset_id = ? AND id IN ? AND deleted_at IS NULL", datasetID, req.Names).
		Updates(map[string]any{"deleted_at": now, "updated_at": now}).Error; err != nil {
		common.ReplyErr(w, "BatchDelete documentFailed，text", http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)
}
func AllDocumentCreators(w http.ResponseWriter, r *http.Request) {
	type resp struct {
		Creators []UserInfo `json:"creators"`
	}
	var names []string
	_ = store.DB().WithContext(r.Context()).
		Model(&orm.Document{}).
		Where("deleted_at IS NULL").
		Distinct().
		Pluck("create_user_name", &names).Error
	sort.Strings(names)
	out := make([]UserInfo, 0, len(names))
	for _, n := range names {
		nn := strings.TrimSpace(n)
		if nn == "" {
			continue
		}
		out = append(out, UserInfo{DisplayName: nn})
	}
	common.ReplyJSON(w, resp{Creators: out})
}
func AllDocumentTags(w http.ResponseWriter, r *http.Request) {
	type resp struct {
		Tags []string `json:"tags"`
	}
	var docs []orm.Document
	_ = store.DB().WithContext(r.Context()).
		Select("tags").
		Where("deleted_at IS NULL").
		Find(&docs).Error
	seen := map[string]struct{}{}
	var tags []string
	for _, d := range docs {
		var ts []string
		_ = json.Unmarshal(d.Tags, &ts)
		for _, t := range ts {
			tt := strings.TrimSpace(t)
			if tt == "" {
				continue
			}
			if _, ok := seen[tt]; ok {
				continue
			}
			seen[tt] = struct{}{}
			tags = append(tags, tt)
		}
	}
	sort.Strings(tags)
	if tags == nil {
		tags = []string{}
	}
	common.ReplyJSON(w, resp{Tags: tags})
}

// --- types (aligned to document-apis-and-tables.md; minimal subset for now) ---

type DocumentTableColumn struct {
	ID           int32  `json:"id"`
	DisplayName  string `json:"display_name"`
	Type         string `json:"type"`
	Desc         string `json:"desc"`
	Sample       string `json:"sample"`
	SourceColumn string `json:"source_column"`
	IndexType    string `json:"index_type"`
}

type Doc struct {
	Name                   string                `json:"name"`
	DocumentID             string                `json:"document_id"`
	DisplayName            string                `json:"display_name"`
	DocumentSize           int64                 `json:"document_size"`
	DatasetID              string                `json:"dataset_id"`
	DatasetDisplay         string                `json:"dataset_display"`
	PID                    string                `json:"p_id"`
	Creator                string                `json:"creator"`
	URI                    string                `json:"uri"`
	FileURL                string                `json:"file_url,omitempty"`
	DownloadFileURL        string                `json:"download_file_url,omitempty"`
	Columns                []DocumentTableColumn `json:"columns"`
	CreateTime             string                `json:"create_time"`
	UpdateTime             string                `json:"update_time"`
	Tags                   []string              `json:"tags"`
	FileID                 string                `json:"file_id"`
	DataSourceType         string                `json:"data_source_type"`
	FileSystemPath         string                `json:"file_system_path"`
	Type                   string                `json:"type"`
	ConvertFileURI         string                `json:"convert_file_uri"`
	RelPath                string                `json:"rel_path"`
	DocumentStage          string                `json:"document_stage"`
	PDFConvertResult       string                `json:"pdf_convert_result,omitempty"`
	ChildDocumentCount     int64                 `json:"child_document_count,omitempty"`
	ChildFolderCount       int64                 `json:"child_folder_count,omitempty"`
	RecursiveDocumentCount int64                 `json:"recursive_document_count,omitempty"`
	RecursiveFolderCount   int64                 `json:"recursive_folder_count,omitempty"`
	RecursiveFileSize      int64                 `json:"recursive_file_size,omitempty"`
	Children               []Doc                 `json:"children"`
}

type ListDocumentsResponse struct {
	Documents     []Doc  `json:"documents"`
	TotalSize     int32  `json:"total_size,omitempty"`
	NextPageToken string `json:"next_page_token,omitempty"`
}

type SearchDocumentsRequest struct {
	Parent    string `json:"parent,omitempty"`
	PID       string `json:"p_id,omitempty"`
	DirPath   string `json:"dir_path,omitempty"`
	OrderBy   string `json:"order_by,omitempty"`
	PageToken string `json:"page_token,omitempty"`
	PageSize  int32  `json:"page_size,omitempty"`
	Keyword   string `json:"keyword,omitempty"`
	Recursive bool   `json:"recursive,omitempty"`
}

type BatchDeleteDocumentRequest struct {
	Parent string   `json:"parent"`
	Names  []string `json:"names"`
}

type externalDeleteDocsRequest struct {
	DocIDs         []string `json:"doc_ids"`
	KbID           string   `json:"kb_id,omitempty"`
	AlgoID         string   `json:"algo_id,omitempty"`
	IdempotencyKey string   `json:"idempotency_key,omitempty"`
}

func deleteExternalDocs(r *http.Request, datasetID string, rows []orm.Document) error {
	docIDs := make([]string, 0, len(rows))
	for _, row := range rows {
		lazyDocID := strings.TrimSpace(row.LazyllmDocID)
		if lazyDocID == "" {
			continue
		}
		docIDs = append(docIDs, lazyDocID)
	}
	if len(docIDs) == 0 {
		return nil
	}
	req := externalDeleteDocsRequest{
		DocIDs:         docIDs,
		KbID:           datasetKbIDByID(datasetID),
		AlgoID:         datasetAlgoIDByID(datasetID),
		IdempotencyKey: newDocID(),
	}
	url := common.JoinURL(parsingServiceEndpoint(), "/v1/docs/delete")
	log.Logger.Info().
		Str("handler", "DeleteDocument").
		Str("dataset_id", datasetID).
		Str("external_url", url).
		Int("doc_count", len(docIDs)).
		Any("request_body", req).
		Msg("calling external delete-docs request")
	var resp map[string]any
	if err := common.ApiPost(requestContext(r), url, req, nil, &resp, 15*time.Second); err != nil {
		log.Logger.Error().
			Err(err).
			Str("handler", "DeleteDocument").
			Str("dataset_id", datasetID).
			Str("external_url", url).
			Int("doc_count", len(docIDs)).
			Any("request_body", req).
			Msg("external delete-docs request failed")
		return err
	}
	log.Logger.Info().
		Str("handler", "DeleteDocument").
		Str("dataset_id", datasetID).
		Str("external_url", url).
		Int("doc_count", len(docIDs)).
		Any("request_body", req).
		Any("response_body", resp).
		Msg("external delete-docs request succeeded")
	return nil
}

type UserInfo struct {
	DisplayName string `json:"display_name,omitempty"`
}

func newDocID() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	return "doc_" + fmtHex(b[:])
}

func fmtHex(b []byte) string {
	const hexdigits = "0123456789abcdef"
	out := make([]byte, len(b)*2)
	for i, v := range b {
		out[i*2] = hexdigits[v>>4]
		out[i*2+1] = hexdigits[v&0x0f]
	}
	return string(out)
}

type mergedDocRow struct {
	DocID            string
	Filename         string
	Path             string
	Ext              json.RawMessage
	DatasetID        string
	DatasetDisplay   string
	BaseCreatedAt    time.Time
	BaseUpdatedAt    time.Time
	DisplayName      string
	PID              string
	Tags             []byte
	FileID           string
	Creator          string
	DocumentSize     int64
	DataSourceType   string
	Type             string
	RelPath          string
	DocumentStage    string
	PDFConvertResult string
}

func loadDatasetDocuments(ctx context.Context, datasetID, keyword, pid string, applyPIDFilter bool, limit, offset int) ([]mergedDocRow, int64, error) {
	if limit <= 0 {
		limit = 20
	}

	rows := make([]mergedDocRow, 0)

	var kbRows []readonlyorm.LazyLLMKBDocRow
	if err := store.LazyLLMDB().WithContext(ctx).
		Table((readonlyorm.LazyLLMKBDocRow{}).TableName()).
		Where("kb_id = ?", datasetID).
		Find(&kbRows).Error; err != nil {
		return nil, 0, err
	}
	if len(kbRows) > 0 {
		docIDs := make([]string, 0, len(kbRows))
		for _, row := range kbRows {
			docIDs = append(docIDs, row.DocID)
		}
		extRows, _, err := loadMergedDocumentsByDocIDs(ctx, docIDs, datasetID, keyword, pid, applyPIDFilter, len(docIDs), 0)
		if err != nil {
			return nil, 0, err
		}
		rows = append(rows, extRows...)
	}

	coreOnlyRows, err := loadCoreOnlyDocuments(ctx, datasetID, keyword, pid, applyPIDFilter)
	if err != nil {
		return nil, 0, err
	}
	rows = append(rows, coreOnlyRows...)

	sort.Slice(rows, func(i, j int) bool { return rows[i].BaseUpdatedAt.After(rows[j].BaseUpdatedAt) })
	total := int64(len(rows))
	if offset >= len(rows) {
		return []mergedDocRow{}, total, nil
	}
	end := offset + limit
	if end > len(rows) {
		end = len(rows)
	}
	return rows[offset:end], total, nil
}

func loadCoreOnlyDocuments(ctx context.Context, datasetID, keyword, pid string, applyPIDFilter bool) ([]mergedDocRow, error) {
	db := store.DB().WithContext(ctx).
		Where("dataset_id = ? AND lazyllm_doc_id = '' AND deleted_at IS NULL", datasetID)
	if applyPIDFilter {
		db = db.Where("COALESCE(p_id, '') = ?", pid)
	}

	var docs []orm.Document
	if err := db.Find(&docs).Error; err != nil {
		return nil, err
	}
	rows := make([]mergedDocRow, 0, len(docs))
	for _, doc := range docs {
		row, err := mergedDocRowFromCoreOnly(ctx, doc, datasetID)
		if err != nil {
			return nil, err
		}
		if !mergedDocMatchesKeyword(row, keyword) {
			continue
		}
		rows = append(rows, row)
	}
	return rows, nil
}

func mergedDocRowFromCoreOnly(ctx context.Context, row orm.Document, datasetID string) (mergedDocRow, error) {
	var dsDisplay string
	if row.DatasetID != "" {
		var ds orm.Dataset
		if err := store.DB().WithContext(ctx).Where("id = ? AND deleted_at IS NULL", row.DatasetID).Take(&ds).Error; err == nil {
			dsDisplay = strings.TrimSpace(ds.DisplayName)
		}
	}
	var dExt documentExt
	_ = json.Unmarshal(row.Ext, &dExt)
	documentSize := dExt.FileSize
	relPath := firstNonEmpty(strings.TrimSpace(dExt.RelativePath), relativePathFromFullPath(dExt.StoredPath))
	docType := documentTypeFromName(firstNonEmpty(strings.TrimSpace(row.DisplayName), dExt.OriginalFilename))
	return mergedDocRow{
		DocID:            row.ID,
		Filename:         row.DisplayName,
		Path:             dExt.StoredPath,
		Ext:              row.Ext,
		DatasetID:        row.DatasetID,
		DatasetDisplay:   dsDisplay,
		BaseCreatedAt:    row.CreatedAt,
		BaseUpdatedAt:    row.UpdatedAt,
		DisplayName:      row.DisplayName,
		PID:              row.PID,
		Tags:             row.Tags,
		FileID:           row.FileID,
		Creator:          row.CreateUserName,
		DocumentSize:     documentSize,
		DataSourceType:   "LOCAL_FILE",
		Type:             docType,
		RelPath:          relPath,
		DocumentStage:    "",
		PDFConvertResult: strings.TrimSpace(row.PDFConvertResult),
	}, nil
}

func loadDocumentByID(ctx context.Context, datasetID, docID string) (mergedDocRow, error) {
	var row orm.Document
	if err := store.DB().WithContext(ctx).Where("(id = ? OR lazyllm_doc_id = ?) AND dataset_id = ? AND deleted_at IS NULL", docID, docID, datasetID).Take(&row).Error; err != nil {
		return mergedDocRow{}, err
	}
	if strings.TrimSpace(row.LazyllmDocID) == "" {
		return mergedDocRowFromCoreOnly(ctx, row, datasetID)
	}
	rows, _, err := loadMergedDocumentsByDocIDs(ctx, []string{row.LazyllmDocID}, datasetID, "", "", false, 1, 0)
	if err != nil {
		return mergedDocRow{}, err
	}
	for _, rr := range rows {
		if rr.DocID == row.ID {
			return rr, nil
		}
	}
	return mergedDocRowFromCoreOnly(ctx, row, datasetID)
}

func searchAllDocumentsMerged(ctx context.Context, keyword string, limit int) ([]mergedDocRow, error) {
	if limit <= 0 {
		limit = 20
	}
	like := "%" + strings.ToLower(strings.ReplaceAll(keyword, "%", "\\%")) + "%"
	var baseRows []readonlyorm.LazyLLMDocRow
	if err := store.LazyLLMDB().WithContext(ctx).
		Table((readonlyorm.LazyLLMDocRow{}).TableName()).
		Where("LOWER(filename) LIKE ? OR LOWER(path) LIKE ?", like, like).
		Order("updated_at DESC").
		Limit(limit * 3).
		Find(&baseRows).Error; err != nil {
		return nil, err
	}
	if len(baseRows) == 0 {
		return []mergedDocRow{}, nil
	}
	docIDs := make([]string, 0, len(baseRows))
	for _, row := range baseRows {
		docIDs = append(docIDs, row.DocID)
	}
	rows, _, err := loadMergedDocumentsByDocIDs(ctx, docIDs, "", keyword, "", false, limit, 0)
	return rows, err
}

func loadMergedDocumentsByDocIDs(ctx context.Context, docIDs []string, datasetID, keyword, pid string, applyPIDFilter bool, limit, offset int) ([]mergedDocRow, int64, error) {
	if len(docIDs) == 0 {
		return []mergedDocRow{}, 0, nil
	}
	var baseRows []readonlyorm.LazyLLMDocRow
	baseQuery := store.LazyLLMDB().WithContext(ctx).
		Table((readonlyorm.LazyLLMDocRow{}).TableName()).
		Where("doc_id IN ?", docIDs)
	if keyword != "" && strings.TrimSpace(datasetID) == "" {
		like := "%" + strings.ToLower(strings.ReplaceAll(keyword, "%", "\\%")) + "%"
		baseQuery = baseQuery.Where("LOWER(filename) LIKE ? OR LOWER(path) LIKE ?", like, like)
	}
	if err := baseQuery.Find(&baseRows).Error; err != nil {
		return nil, 0, err
	}
	if len(baseRows) == 0 {
		return []mergedDocRow{}, 0, nil
	}
	baseByExternalID := make(map[string]readonlyorm.LazyLLMDocRow, len(baseRows))
	filteredExternalIDs := make([]string, 0, len(baseRows))
	for _, row := range baseRows {
		baseByExternalID[row.DocID] = row
		filteredExternalIDs = append(filteredExternalIDs, row.DocID)
	}

	latestTaskStatusByExternalID := make(map[string]string, len(filteredExternalIDs))
	if len(filteredExternalIDs) > 0 {
		var extTasks []readonlyorm.LazyLLMDocServiceTaskRow
		if err := store.LazyLLMDB().WithContext(ctx).
			Table((readonlyorm.LazyLLMDocServiceTaskRow{}).TableName()).
			Where("doc_id IN ?", filteredExternalIDs).
			Order("updated_at DESC").
			Find(&extTasks).Error; err != nil {
			return nil, 0, err
		}
		for _, task := range extTasks {
			if _, ok := latestTaskStatusByExternalID[task.DocID]; !ok {
				latestTaskStatusByExternalID[task.DocID] = strings.TrimSpace(task.Status)
			}
		}
	}

	var diffs []orm.Document
	diffQuery := store.DB().WithContext(ctx).
		Where("lazyllm_doc_id IN ? AND deleted_at IS NULL", filteredExternalIDs)
	if datasetID != "" {
		diffQuery = diffQuery.Where("dataset_id = ?", datasetID)
	}
	if applyPIDFilter {
		diffQuery = diffQuery.Where("COALESCE(p_id, '') = ?", pid)
	}
	if err := diffQuery.Find(&diffs).Error; err != nil {
		return nil, 0, err
	}
	diffByLazyllmID := make(map[string]orm.Document, len(diffs))
	coreIDs := make([]string, 0, len(diffs))
	datasetIDs := make([]string, 0, len(diffs))
	datasetSeen := make(map[string]struct{}, len(diffs))
	for _, diff := range diffs {
		diffByLazyllmID[diff.LazyllmDocID] = diff
		coreIDs = append(coreIDs, diff.ID)
		if diff.DatasetID != "" {
			if _, ok := datasetSeen[diff.DatasetID]; !ok {
				datasetSeen[diff.DatasetID] = struct{}{}
				datasetIDs = append(datasetIDs, diff.DatasetID)
			}
		}
	}

	latestTaskDataSourceByExternalID := make(map[string]string, len(filteredExternalIDs))
	if len(coreIDs) > 0 {
		var coreTasks []orm.Task
		if err := store.DB().WithContext(ctx).
			Where("doc_id IN ? AND deleted_at IS NULL", coreIDs).
			Order("updated_at DESC").
			Find(&coreTasks).Error; err != nil {
			return nil, 0, err
		}
		for _, task := range coreTasks {
			var doc orm.Document
			for _, d := range diffs {
				if d.ID == task.DocID {
					doc = d
					break
				}
			}
			if strings.TrimSpace(doc.LazyllmDocID) == "" {
				continue
			}
			if _, ok := latestTaskDataSourceByExternalID[doc.LazyllmDocID]; ok {
				continue
			}
			var ext taskExt
			_ = json.Unmarshal(task.Ext, &ext)
			if s := strings.TrimSpace(ext.DataSourceType); s != "" {
				latestTaskDataSourceByExternalID[doc.LazyllmDocID] = s
			}
		}
	}

	datasetDisplayByID := make(map[string]string, len(datasetIDs))
	if len(datasetIDs) > 0 {
		var datasets []orm.Dataset
		if err := store.DB().WithContext(ctx).Where("id IN ? AND deleted_at IS NULL", datasetIDs).Find(&datasets).Error; err != nil {
			return nil, 0, err
		}
		for _, ds := range datasets {
			datasetDisplayByID[ds.ID] = strings.TrimSpace(ds.DisplayName)
		}
	}

	rows := make([]mergedDocRow, 0, len(baseRows))
	likeKeyword := strings.ToLower(strings.TrimSpace(keyword))
	for _, extDocID := range filteredExternalIDs {
		base := baseByExternalID[extDocID]
		diff, ok := diffByLazyllmID[extDocID]
		if datasetID != "" && !ok {
			continue
		}
		coreDocID := extDocID
		if ok {
			coreDocID = diff.ID
		}
		displayName := strings.TrimSpace(base.Filename)
		pidValue := ""
		var tags []byte
		fileID := ""
		creator := ""
		documentSize := int64(0)
		if base.SizeBytes != nil {
			documentSize = int64(*base.SizeBytes)
		}
		docType := documentTypeFromName(base.Filename)
		relPath := ""
		documentStage := strings.TrimSpace(base.UploadStatus)
		dataSourceType := ""
		datasetValue := datasetID
		datasetDisplay := ""
		if s, ok := latestTaskDataSourceByExternalID[base.DocID]; ok && strings.TrimSpace(s) != "" {
			dataSourceType = strings.TrimSpace(s)
		}
		if ok {
			datasetValue = diff.DatasetID
			datasetDisplay = datasetDisplayByID[diff.DatasetID]
			if strings.TrimSpace(diff.DisplayName) != "" {
				displayName = strings.TrimSpace(diff.DisplayName)
			}
			pidValue = diff.PID
			tags = diff.Tags
			fileID = diff.FileID
			creator = diff.CreateUserName
			var dExt documentExt
			_ = json.Unmarshal(diff.Ext, &dExt)
			if dExt.FileSize > 0 {
				documentSize = dExt.FileSize
			}
			if strings.TrimSpace(dExt.RelativePath) != "" {
				relPath = strings.TrimSpace(dExt.RelativePath)
			}
			if strings.TrimSpace(dExt.OriginalFilename) != "" {
				docType = documentTypeFromName(dExt.OriginalFilename)
			}
			if strings.TrimSpace(base.SourceType) != "" {
				dataSourceType = dataSourceTypeFromSourceType(base.SourceType)
			}
			if taskStatus, ok2 := latestTaskStatusByExternalID[base.DocID]; ok2 && strings.TrimSpace(taskStatus) != "" {
				documentStage = strings.TrimSpace(taskStatus)
			}
		}
		if strings.TrimSpace(dataSourceType) == "" && strings.TrimSpace(base.SourceType) != "" {
			dataSourceType = dataSourceTypeFromSourceType(base.SourceType)
		}
		if strings.TrimSpace(dataSourceType) == "" {
			dataSourceType = "LOCAL_FILE"
		}
		if relPath == "" {
			relPath = relativePathFromFullPath(base.Path)
		}
		row := mergedDocRow{
			DocID:            coreDocID,
			Filename:         base.Filename,
			Path:             base.Path,
			Ext:              diff.Ext,
			DatasetID:        datasetValue,
			DatasetDisplay:   datasetDisplay,
			BaseCreatedAt:    base.CreatedAt,
			BaseUpdatedAt:    base.UpdatedAt,
			DisplayName:      displayName,
			PID:              pidValue,
			Tags:             tags,
			FileID:           fileID,
			Creator:          creator,
			DocumentSize:     documentSize,
			DataSourceType:   dataSourceType,
			Type:             docType,
			RelPath:          relPath,
			DocumentStage:    documentStage,
			PDFConvertResult: strings.TrimSpace(diff.PDFConvertResult),
		}
		if likeKeyword != "" && !mergedDocMatchesKeyword(row, likeKeyword) {
			continue
		}
		rows = append(rows, row)
	}
	sort.Slice(rows, func(i, j int) bool { return rows[i].BaseUpdatedAt.After(rows[j].BaseUpdatedAt) })
	total := int64(len(rows))
	if offset >= len(rows) {
		return []mergedDocRow{}, total, nil
	}
	end := offset + limit
	if end > len(rows) {
		end = len(rows)
	}
	return rows[offset:end], total, nil
}

func mergedDocMatchesKeyword(row mergedDocRow, keyword string) bool {
	kw := strings.ToLower(strings.TrimSpace(keyword))
	if kw == "" {
		return true
	}
	if strings.Contains(strings.ToLower(strings.TrimSpace(row.DisplayName)), kw) {
		return true
	}
	if strings.Contains(strings.ToLower(strings.TrimSpace(row.Filename)), kw) {
		return true
	}
	if strings.Contains(strings.ToLower(strings.TrimSpace(row.Path)), kw) {
		return true
	}
	if strings.Contains(strings.ToLower(strings.TrimSpace(row.Creator)), kw) {
		return true
	}

	var tags []string
	_ = json.Unmarshal(row.Tags, &tags)
	for _, t := range tags {
		if strings.Contains(strings.ToLower(strings.TrimSpace(t)), kw) {
			return true
		}
	}
	return false
}

func docFromRow(row mergedDocRow) Doc {
	var tags []string
	_ = json.Unmarshal(row.Tags, &tags)
	if tags == nil {
		tags = []string{}
	}
	stats := folderStatsFromExt(row.Ext)
	pdfConvertResult := strings.TrimSpace(row.PDFConvertResult)
	displayName := strings.TrimSpace(row.DisplayName)
	if displayName == "" {
		displayName = strings.TrimSpace(row.Filename)
	}
	if displayName == "" {
		displayName = row.DocID
	}
	originalPath := originalStoredPathFromRow(row)
	previewPath := strings.TrimSpace(row.Path)
	if previewPath == "" {
		previewPath = originalPath
	}
	if extPath := parseStoredPathFromExt(row.Ext); extPath != "" {
		previewPath = extPath
	}
	ct := ""
	ut := ""
	if !row.BaseCreatedAt.IsZero() {
		ct = row.BaseCreatedAt.UTC().Format(time.RFC3339)
	}
	if !row.BaseUpdatedAt.IsZero() {
		ut = row.BaseUpdatedAt.UTC().Format(time.RFC3339)
	}
	documentSize := row.DocumentSize
	if strings.EqualFold(strings.TrimSpace(row.Type), "FOLDER") && stats.RecursiveFileSize > 0 {
		documentSize = stats.RecursiveFileSize
	}
	return Doc{
		Name:                   "datasets/" + row.DatasetID + "/documents/" + row.DocID,
		DocumentID:             row.DocID,
		DisplayName:            displayName,
		DocumentSize:           documentSize,
		DatasetID:              row.DatasetID,
		DatasetDisplay:         row.DatasetDisplay,
		PID:                    row.PID,
		Creator:                row.Creator,
		URI:                    "",
		FileURL:                staticFileURLFromFullPath(previewPath),
		DownloadFileURL:        staticFileURLFromFullPath(originalPath),
		Columns:                []DocumentTableColumn{},
		CreateTime:             ct,
		UpdateTime:             ut,
		Tags:                   tags,
		FileID:                 row.FileID,
		DataSourceType:         row.DataSourceType,
		FileSystemPath:         row.Path,
		Type:                   row.Type,
		ConvertFileURI:         "",
		RelPath:                row.RelPath,
		DocumentStage:          row.DocumentStage,
		PDFConvertResult:       pdfConvertResult,
		ChildDocumentCount:     stats.ChildDocumentCount,
		ChildFolderCount:       stats.ChildFolderCount,
		RecursiveDocumentCount: stats.RecursiveDocumentCount,
		RecursiveFolderCount:   stats.RecursiveFolderCount,
		RecursiveFileSize:      stats.RecursiveFileSize,
		Children:               []Doc{},
	}
}

func buildDocumentTreeRelPaths(ctx context.Context, rows []mergedDocRow) map[string]string {
	paths := make(map[string]string, len(rows))
	if len(rows) == 0 {
		return paths
	}
	byID := make(map[string]mergedDocRow, len(rows))
	for _, row := range rows {
		byID[row.DocID] = row
	}
	getDisplayName := func(row mergedDocRow) string {
		name := strings.TrimSpace(row.DisplayName)
		if name == "" {
			name = strings.TrimSpace(row.Filename)
		}
		if name == "" {
			name = row.DocID
		}
		return name
	}
	var build func(docID string) string
	build = func(docID string) string {
		if p, ok := paths[docID]; ok {
			return p
		}
		row, ok := byID[docID]
		if !ok {
			return ""
		}
		selfName := getDisplayName(row)
		pid := strings.TrimSpace(row.PID)
		if pid == "" {
			paths[docID] = selfName
			return selfName
		}
		parent, ok := byID[pid]
		if !ok {
			var parentRow orm.Document
			if err := store.DB().WithContext(ctx).Where("id = ? AND dataset_id = ? AND deleted_at IS NULL", pid, row.DatasetID).Take(&parentRow).Error; err != nil {
				paths[docID] = selfName
				return selfName
			}
			parent = mergedDocRow{DocID: parentRow.ID, DatasetID: parentRow.DatasetID, PID: parentRow.PID, DisplayName: parentRow.DisplayName}
			byID[pid] = parent
		}
		parentPath := build(pid)
		if strings.TrimSpace(parentPath) == "" {
			paths[docID] = selfName
		} else {
			paths[docID] = parentPath + "/" + selfName
		}
		return paths[docID]
	}
	for _, row := range rows {
		_ = build(row.DocID)
	}
	return paths
}

type folderStats struct {
	ChildDocumentCount     int64
	ChildFolderCount       int64
	RecursiveDocumentCount int64
	RecursiveFolderCount   int64
	RecursiveFileSize      int64
}

func folderStatsFromExt(raw json.RawMessage) folderStats {
	if len(raw) == 0 {
		return folderStats{}
	}
	var extMap map[string]any
	if err := json.Unmarshal(raw, &extMap); err != nil {
		return folderStats{}
	}
	return folderStats{
		ChildDocumentCount:     int64FromAny(extMap["child_document_count"]),
		ChildFolderCount:       int64FromAny(extMap["child_folder_count"]),
		RecursiveDocumentCount: int64FromAny(extMap["recursive_document_count"]),
		RecursiveFolderCount:   int64FromAny(extMap["recursive_folder_count"]),
		RecursiveFileSize:      int64FromAny(extMap["recursive_file_size"]),
	}
}

func int64FromAny(v any) int64 {
	switch x := v.(type) {
	case int:
		return int64(x)
	case int32:
		return int64(x)
	case int64:
		return x
	case float32:
		return int64(x)
	case float64:
		return int64(x)
	case json.Number:
		n, _ := x.Int64()
		return n
	case string:
		n, _ := strconv.ParseInt(strings.TrimSpace(x), 10, 64)
		return n
	default:
		return 0
	}
}

func parseStoredPathFromExt(raw json.RawMessage) string {
	if len(raw) == 0 {
		return ""
	}
	var ext documentExt
	if err := json.Unmarshal(raw, &ext); err != nil {
		return ""
	}
	return strings.TrimSpace(ext.ParseStoredPath)
}

func originalStoredPathFromRow(row mergedDocRow) string {
	if len(row.Ext) > 0 {
		var ext documentExt
		if err := json.Unmarshal(row.Ext, &ext); err == nil {
			if v := strings.TrimSpace(ext.SourceStoredPath); v != "" {
				return v
			}
			if v := strings.TrimSpace(ext.StoredPath); v != "" {
				return v
			}
		}
	}
	return strings.TrimSpace(row.Path)
}

func relativePathFromFullPath(path string) string {
	p := strings.TrimSpace(path)
	if p == "" {
		return ""
	}
	dir := filepath.Dir(p)
	if dir == "." || dir == "/" {
		return ""
	}
	marker := string(filepath.Separator) + "docs" + string(filepath.Separator)
	idx := strings.Index(dir, marker)
	if idx >= 0 {
		rel := strings.TrimPrefix(dir[idx+len(marker):], string(filepath.Separator))
		parts := strings.Split(rel, string(filepath.Separator))
		for i := 0; i < len(parts); i++ {
			if parts[i] == "files" {
				if i == 0 {
					return ""
				}
				return filepath.Join(parts[:i]...)
			}
		}
		return rel
	}
	return dir
}

func documentTypeFromName(name string) string {
	ext := strings.ToLower(strings.TrimSpace(filepath.Ext(name)))
	switch ext {
	case "":
		return "FOLDER"
	case ".txt":
		return "TXT"
	case ".pdf":
		return "PDF"
	case ".html", ".htm":
		return "HTML"
	case ".xlsx":
		return "XLSX"
	case ".xls":
		return "XLS"
	case ".docx", ".doc":
		return "DOCX"
	case ".csv":
		return "CSV"
	case ".pptx":
		return "PPTX"
	case ".ppt":
		return "PPT"
	case ".xml":
		return "XML"
	case ".md", ".markdown":
		return "MARKDOWN"
	case ".json", ".jsonl":
		return "JSON"
	default:
		return "DOCUMENT_TYPE_UNSPECIFIED"
	}
}

func dataSourceTypeFromSourceType(sourceType string) string {
	switch strings.ToUpper(strings.TrimSpace(sourceType)) {
	case "LOCAL_FILE", "FILE", "UPLOAD":
		return "LOCAL_FILE"
	case "FILE_SYSTEM", "FILESYSTEM":
		return "FILE_SYSTEM"
	default:
		return "DATA_SOURCE_TYPE_UNSPECIFIED"
	}
}
