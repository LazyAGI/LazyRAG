package worker

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"go.uber.org/zap"

	"github.com/lazyrag/scan_control_plane/internal/config"
	"github.com/lazyrag/scan_control_plane/internal/coreclient"
	"github.com/lazyrag/scan_control_plane/internal/sourcelayout"
	"github.com/lazyrag/scan_control_plane/internal/store"
)

type Store interface {
	ClaimDueTasks(ctx context.Context, leaseOwner string, now time.Time, limit int, leaseDuration time.Duration) ([]store.PendingTask, error)
	MarkTaskSuperseded(ctx context.Context, taskID int64, reason string) error
	MarkTaskStaging(ctx context.Context, taskID int64) error
	FindSubmittedTaskByIdempotencyKey(ctx context.Context, tenantID, idempotencyKey string, excludeTaskID int64) (store.SubmittedCoreTaskRef, error)
	MarkTaskSubmitted(ctx context.Context, taskID int64, coreDatasetID, coreDocumentID, coreTaskID string, submitAt time.Time) error
	MarkTaskSubmitFailed(ctx context.Context, taskID int64, lastError string) error
	MarkTaskRetryWaiting(ctx context.Context, taskID int64, retryCount int, nextRunAt time.Time, lastError string) error
	MarkTaskFailed(ctx context.Context, taskID int64, lastError string) error
	MarkTaskSucceeded(ctx context.Context, taskID int64, documentID int64, targetVersion string) error
	DesiredVersionMatches(ctx context.Context, documentID int64, targetVersion string) (bool, error)
	UpdateDocumentRunning(ctx context.Context, documentID int64) error
	RequeueTimedOutCommands(ctx context.Context, now time.Time, ackTimeout time.Duration, maxAttempts int) (int64, error)
	FailExhaustedCommands(ctx context.Context, maxAttempts int) (int64, error)
	MarkAgentsOffline(ctx context.Context, now time.Time, timeout time.Duration) (int64, error)
	EnqueueStageCommand(ctx context.Context, agentID string, payload store.StageCommandPayload) (int64, error)
	AwaitCommandResult(ctx context.Context, commandID int64, pollInterval time.Duration) (string, error)
}

type Worker struct {
	cfg     config.WorkerConfig
	store   Store
	core    coreclient.Client
	log     *zap.Logger
	owner   string
	sem     chan struct{}
	limiter *taskLimiter
}

type stageResponse struct {
	HostPath      string `json:"host_path"`
	ContainerPath string `json:"container_path"`
	URI           string `json:"uri"`
	Size          int64  `json:"size"`
}

func New(cfg config.WorkerConfig, st Store, coreClient coreclient.Client, log *zap.Logger) *Worker {
	if cfg.MaxConcurrent <= 0 {
		cfg.MaxConcurrent = 1
	}
	if coreClient == nil {
		coreClient = coreclient.NewNoop()
	}
	return &Worker{
		cfg:     cfg,
		store:   st,
		core:    coreClient,
		log:     log,
		owner:   fmt.Sprintf("worker-%d", time.Now().UnixNano()),
		sem:     make(chan struct{}, cfg.MaxConcurrent),
		limiter: newTaskLimiter(cfg),
	}
}

func (w *Worker) Run(ctx context.Context) {
	if !w.cfg.Enabled {
		w.log.Info("parse worker disabled")
		return
	}
	ticker := time.NewTicker(w.cfg.Tick)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case now := <-ticker.C:
			w.tick(ctx, now.UTC())
		}
	}
}

func (w *Worker) tick(ctx context.Context, now time.Time) {
	if _, err := w.store.RequeueTimedOutCommands(ctx, now, w.cfg.CommandAckTimeout, w.cfg.CommandMaxAttempts); err != nil {
		w.log.Warn("requeue timed out commands failed", zap.Error(err))
	}
	if _, err := w.store.FailExhaustedCommands(ctx, w.cfg.CommandMaxAttempts); err != nil {
		w.log.Warn("mark exhausted commands failed", zap.Error(err))
	}
	if _, err := w.store.MarkAgentsOffline(ctx, now, w.cfg.AgentOfflineTimeout); err != nil {
		w.log.Warn("mark offline agents failed", zap.Error(err))
	}

	available := cap(w.sem) - len(w.sem)
	if available <= 0 {
		return
	}
	limit := w.cfg.ClaimBatchSize
	if limit > available {
		limit = available
	}
	tasks, err := w.store.ClaimDueTasks(ctx, w.owner, now, limit, w.cfg.LeaseDuration)
	if err != nil {
		w.log.Warn("claim due tasks failed", zap.Error(err))
		return
	}
	if len(tasks) > 0 {
		w.log.Info("claimed due parse tasks",
			zap.Int("count", len(tasks)),
			zap.String("owner", w.owner),
		)
	}
	for _, task := range tasks {
		task := task
		w.sem <- struct{}{}
		go func() {
			defer func() { <-w.sem }()
			w.executeTask(ctx, task)
		}()
	}
}

func (w *Worker) executeTask(ctx context.Context, task store.PendingTask) {
	w.log.Info("execute parse task",
		zap.Int64("task_id", task.TaskID),
		zap.Int64("document_id", task.DocumentID),
		zap.String("source_id", task.SourceID),
		zap.String("target_version", task.TargetVersionID),
		zap.Int("retry_count", task.RetryCount),
	)
	release, ok := w.limiter.TryAcquireTask(task.TenantID, task.SourceID)
	if !ok {
		nextRunAt := time.Now().UTC().Add(2 * time.Second)
		_ = w.store.MarkTaskRetryWaiting(ctx, task.TaskID, task.RetryCount, nextRunAt, "capacity limited: tenant/source quota")
		return
	}
	defer release()

	matched, err := w.store.DesiredVersionMatches(ctx, task.DocumentID, task.TargetVersionID)
	if err != nil {
		w.failWithRetry(ctx, task, fmt.Errorf("pre-check desired_version failed: %w", err))
		return
	}
	if !matched {
		_ = w.store.MarkTaskSuperseded(ctx, task.TaskID, "pre-check desired_version mismatch")
		w.log.Info("task superseded in pre-check",
			zap.Int64("task_id", task.TaskID),
			zap.Int64("document_id", task.DocumentID),
			zap.String("target_version", task.TargetVersionID),
		)
		return
	}

	if key := strings.TrimSpace(task.IdempotencyKey); key != "" {
		existing, err := w.store.FindSubmittedTaskByIdempotencyKey(ctx, task.TenantID, key, task.TaskID)
		if err != nil {
			w.failSubmitWithRetry(ctx, task, fmt.Errorf("query idempotency task failed: %w", err))
			return
		}
		if strings.TrimSpace(existing.CoreTaskID) != "" {
			if err := w.store.MarkTaskSubmitted(ctx, task.TaskID, existing.CoreDatasetID, existing.CoreDocumentID, existing.CoreTaskID, time.Now().UTC()); err != nil {
				w.failSubmitWithRetry(ctx, task, fmt.Errorf("mark task submitted by idempotency failed: %w", err))
				return
			}
			w.log.Info("task submitted via idempotency reuse",
				zap.Int64("task_id", task.TaskID),
				zap.String("idempotency_key", key),
				zap.String("core_dataset_id", existing.CoreDatasetID),
				zap.String("core_task_id", existing.CoreTaskID),
			)
			return
		}
	}

	taskAction := store.NormalizeTaskAction(task.TaskAction)
	staged := stageResponse{}
	if taskAction != "DELETE" {
		if err := w.store.MarkTaskStaging(ctx, task.TaskID); err != nil {
			w.failSubmitWithRetry(ctx, task, fmt.Errorf("mark task staging failed: %w", err))
			return
		}

		var err error
		if isCloudSyncOrigin(task.OriginType) {
			staged, err = w.stageFromCloudMirror(task)
			if err != nil {
				w.failSubmitWithRetry(ctx, task, err)
				return
			}
		} else {
			staged, err = w.callStage(ctx, task)
			if err != nil {
				w.failSubmitWithRetry(ctx, task, err)
				return
			}
		}

		releaseLarge := func() {}
		if staged.Size >= w.cfg.LargeFileThreshold {
			var acquired bool
			releaseLarge, acquired = w.limiter.TryAcquireLarge()
			if !acquired {
				nextRunAt := time.Now().UTC().Add(2 * time.Second)
				_ = w.store.MarkTaskRetryWaiting(ctx, task.TaskID, task.RetryCount, nextRunAt, "capacity limited: large-file lane busy")
				return
			}
		}
		defer releaseLarge()
	}

	submitResult, err := w.core.SubmitParseTask(ctx, task, firstNonEmpty(staged.ContainerPath, staged.HostPath), staged.URI, staged.Size)
	if err != nil {
		w.failSubmitWithRetry(ctx, task, fmt.Errorf("submit task to core failed: %w", err))
		return
	}
	if taskAction == "DELETE" && strings.TrimSpace(submitResult.TaskID) == "" {
		if err := w.store.MarkTaskSucceeded(ctx, task.TaskID, task.DocumentID, task.TargetVersionID); err != nil {
			w.failSubmitWithRetry(ctx, task, fmt.Errorf("mark delete task succeeded failed: %w", err))
			return
		}
		w.log.Info("delete task finished",
			zap.Int64("task_id", task.TaskID),
			zap.String("core_dataset_id", submitResult.DatasetID),
			zap.String("core_document_id", submitResult.DocumentID),
		)
		return
	}
	if err := w.store.MarkTaskSubmitted(ctx, task.TaskID, submitResult.DatasetID, submitResult.DocumentID, submitResult.TaskID, time.Now().UTC()); err != nil {
		w.failSubmitWithRetry(ctx, task, fmt.Errorf("mark task submitted failed: %w", err))
		return
	}
	w.log.Info("task submitted",
		zap.Int64("task_id", task.TaskID),
		zap.String("task_action", taskAction),
		zap.String("core_dataset_id", submitResult.DatasetID),
		zap.String("core_document_id", submitResult.DocumentID),
		zap.String("core_task_id", submitResult.TaskID),
	)
}

func (w *Worker) callStage(ctx context.Context, task store.PendingTask) (stageResponse, error) {
	var resp stageResponse
	if task.AgentID == "" {
		return resp, fmt.Errorf("empty agent id for source %s", task.SourceID)
	}
	cmdID, err := w.store.EnqueueStageCommand(ctx, task.AgentID, store.StageCommandPayload{
		SourceID:   task.SourceID,
		DocumentID: fmt.Sprintf("%d", task.DocumentID),
		VersionID:  task.TargetVersionID,
		SrcPath:    task.SourceObjectID,
	})
	if err != nil {
		return resp, err
	}
	w.log.Info("stage command enqueued",
		zap.Int64("task_id", task.TaskID),
		zap.Int64("command_id", cmdID),
		zap.String("agent_id", task.AgentID),
		zap.String("source_path", task.SourceObjectID),
	)
	waitTimeout := w.cfg.AgentTimeout
	if waitTimeout <= 0 {
		waitTimeout = w.cfg.CommandAckTimeout
	}
	waitCtx, cancel := context.WithTimeout(ctx, waitTimeout)
	defer cancel()
	raw, err := w.store.AwaitCommandResult(waitCtx, cmdID, 500*time.Millisecond)
	if err != nil {
		return resp, fmt.Errorf("await stage command ack failed: %w", err)
	}
	if raw == "" {
		return resp, fmt.Errorf("stage command ack returned empty result")
	}
	if err := json.Unmarshal([]byte(raw), &resp); err != nil {
		return resp, fmt.Errorf("decode stage result failed: %w", err)
	}
	w.log.Info("stage command acked",
		zap.Int64("task_id", task.TaskID),
		zap.Int64("command_id", cmdID),
		zap.String("host_path", resp.HostPath),
		zap.String("container_path", resp.ContainerPath),
		zap.Int64("size", resp.Size),
	)
	return resp, nil
}

func (w *Worker) failWithRetry(ctx context.Context, task store.PendingTask, err error) {
	msg := err.Error()
	nextRetryCount := task.RetryCount + 1
	if nextRetryCount > task.MaxRetryCount {
		_ = w.store.MarkTaskFailed(ctx, task.TaskID, msg)
		w.log.Warn("task failed permanently", zap.Int64("task_id", task.TaskID), zap.Error(err))
		return
	}
	backoff := retryBackoff(w.cfg.RetryBaseBackoff, w.cfg.RetryMaxBackoff, nextRetryCount)
	nextRunAt := time.Now().UTC().Add(backoff)
	_ = w.store.MarkTaskRetryWaiting(ctx, task.TaskID, nextRetryCount, nextRunAt, msg)
	w.log.Warn("task retry scheduled",
		zap.Int64("task_id", task.TaskID),
		zap.Int("retry_count", nextRetryCount),
		zap.Duration("backoff", backoff),
		zap.Error(err),
	)
}

func (w *Worker) failSubmitWithRetry(ctx context.Context, task store.PendingTask, err error) {
	msg := err.Error()
	nextRetryCount := task.RetryCount + 1
	if nextRetryCount > task.MaxRetryCount {
		_ = w.store.MarkTaskSubmitFailed(ctx, task.TaskID, msg)
		w.log.Warn("task submit failed permanently", zap.Int64("task_id", task.TaskID), zap.Error(err))
		return
	}
	backoff := retryBackoff(w.cfg.RetryBaseBackoff, w.cfg.RetryMaxBackoff, nextRetryCount)
	nextRunAt := time.Now().UTC().Add(backoff)
	_ = w.store.MarkTaskRetryWaiting(ctx, task.TaskID, nextRetryCount, nextRunAt, msg)
	w.log.Warn("task submit retry scheduled",
		zap.Int64("task_id", task.TaskID),
		zap.Int("retry_count", nextRetryCount),
		zap.Duration("backoff", backoff),
		zap.Error(err),
	)
}

func retryBackoff(base, max time.Duration, retryCount int) time.Duration {
	if retryCount <= 0 {
		return base
	}
	delay := base
	for i := 1; i < retryCount; i++ {
		delay *= 2
		if delay >= max {
			return max
		}
	}
	if delay > max {
		return max
	}
	return delay
}

type taskLimiter struct {
	maxPerTenant int
	maxPerSource int
	largeSem     chan struct{}
	mu           sync.Mutex
	tenantUsage  map[string]int
	sourceUsage  map[string]int
}

func newTaskLimiter(cfg config.WorkerConfig) *taskLimiter {
	return &taskLimiter{
		maxPerTenant: maxInt(1, cfg.MaxPerTenant),
		maxPerSource: maxInt(1, cfg.MaxPerSource),
		largeSem:     make(chan struct{}, maxInt(1, cfg.MaxLargeFile)),
		tenantUsage:  make(map[string]int),
		sourceUsage:  make(map[string]int),
	}
}

func (l *taskLimiter) TryAcquireTask(tenantID, sourceID string) (func(), bool) {
	l.mu.Lock()
	defer l.mu.Unlock()
	t := l.tenantUsage[tenantID]
	s := l.sourceUsage[sourceID]
	if t >= l.maxPerTenant || s >= l.maxPerSource {
		return nil, false
	}
	l.tenantUsage[tenantID] = t + 1
	l.sourceUsage[sourceID] = s + 1
	return func() {
		l.mu.Lock()
		defer l.mu.Unlock()
		l.tenantUsage[tenantID] = maxInt(0, l.tenantUsage[tenantID]-1)
		l.sourceUsage[sourceID] = maxInt(0, l.sourceUsage[sourceID]-1)
	}, true
}

func (l *taskLimiter) TryAcquireLarge() (func(), bool) {
	select {
	case l.largeSem <- struct{}{}:
		return func() {
			<-l.largeSem
		}, true
	default:
		return nil, false
	}
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func firstNonEmpty(values ...string) string {
	for _, v := range values {
		if strings.TrimSpace(v) != "" {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

func isCloudSyncOrigin(originType string) bool {
	return strings.EqualFold(strings.TrimSpace(originType), "CLOUD_SYNC")
}

func (w *Worker) stageFromCloudMirror(task store.PendingTask) (stageResponse, error) {
	resp := stageResponse{}
	srcPath := strings.TrimSpace(task.SourceObjectID)
	if srcPath == "" {
		return resp, fmt.Errorf("empty source object path for cloud sync task")
	}
	info, err := os.Stat(srcPath)
	if err != nil {
		return resp, fmt.Errorf("cloud sync mirror stat failed: %w", err)
	}
	if info.IsDir() {
		return resp, fmt.Errorf("cloud sync mirror path is directory: %s", srcPath)
	}
	sourceRoot := filepath.Clean(strings.TrimSpace(task.SourceRootPath))
	if sourceRoot == "" || sourceRoot == "." {
		sourceRoot = deriveCloudSourceRootFromMirrorPath(srcPath)
	}
	if sourceRoot == "" || sourceRoot == "." {
		return resp, fmt.Errorf("resolve cloud source root failed for source path %s", srcPath)
	}
	parseRoot := sourcelayout.CloudParseRoot(sourceRoot)
	if err := os.MkdirAll(parseRoot, 0o755); err != nil {
		return resp, fmt.Errorf("ensure parse root failed: %w", err)
	}

	relPath, collisionDepth, err := allocateCloudParseRelativePath(parseRoot, task.SourceID, srcPath)
	if err != nil {
		return resp, err
	}
	parsePath, err := joinUnderRoot(parseRoot, relPath)
	if err != nil {
		return resp, err
	}
	if err := os.MkdirAll(filepath.Dir(parsePath), 0o755); err != nil {
		return resp, fmt.Errorf("ensure parse subdir failed: %w", err)
	}
	if existing, err := os.Stat(parsePath); err == nil && existing.Size() == info.Size() && existing.ModTime().Equal(info.ModTime()) {
		resp = stageResponse{
			HostPath:      parsePath,
			ContainerPath: parsePath,
			URI:           "file://" + parsePath,
			Size:          existing.Size(),
		}
		w.log.Info("cloud sync parse staging hit",
			zap.Int64("task_id", task.TaskID),
			zap.String("source_id", task.SourceID),
			zap.String("mirror_path", srcPath),
			zap.String("parse_path", parsePath),
			zap.String("parse_root", parseRoot),
		)
		return resp, nil
	}

	written, err := copyFileAtomic(srcPath, parsePath, info.ModTime())
	if err != nil {
		return resp, fmt.Errorf("copy cloud mirror to parse path failed: %w", err)
	}
	resp = stageResponse{
		HostPath:      parsePath,
		ContainerPath: parsePath,
		URI:           "file://" + parsePath,
		Size:          written,
	}
	w.log.Info("cloud sync mirror staged into parse layout",
		zap.Int64("task_id", task.TaskID),
		zap.String("source_id", task.SourceID),
		zap.String("mirror_path", srcPath),
		zap.String("source_root", sourceRoot),
		zap.String("parse_root", parseRoot),
		zap.String("mapped_name", relPath),
		zap.Int("collision_depth", collisionDepth),
		zap.String("parse_path", parsePath),
		zap.Int64("size", resp.Size),
	)
	return resp, nil
}

type cloudParseIndex struct {
	Entries map[string]string `json:"entries"`
}

func allocateCloudParseRelativePath(parseRoot, sourceID, srcPath string) (string, int, error) {
	safeSourceID, err := safeCloudSourceID(sourceID)
	if err != nil {
		return "", 0, fmt.Errorf("invalid source id for cloud parse staging: %w", err)
	}
	idx, err := loadCloudParseIndex(parseRoot)
	if err != nil {
		return "", 0, fmt.Errorf("load cloud parse index failed: %w", err)
	}
	key := cloudParseIndexKey(safeSourceID, srcPath)
	relPath, collisionDepth := nextCloudHashedRelativePath(safeSourceID, srcPath, key, idx.Entries)
	if strings.TrimSpace(idx.Entries[key]) != relPath {
		idx.Entries[key] = relPath
		if err := persistCloudParseIndex(parseRoot, idx); err != nil {
			return "", 0, fmt.Errorf("persist cloud parse index failed: %w", err)
		}
	}
	return relPath, collisionDepth, nil
}

func safeCloudSourceID(value string) (string, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return "", fmt.Errorf("source_id is empty")
	}
	if strings.Contains(value, "/") || strings.Contains(value, "\\") {
		return "", fmt.Errorf("source_id contains path separator")
	}
	clean := filepath.Clean(value)
	if clean != value || clean == "." || clean == ".." {
		return "", fmt.Errorf("source_id contains invalid path segment")
	}
	return value, nil
}

func cloudParseIndexPath(parseRoot string) string {
	return filepath.Join(filepath.Clean(parseRoot), ".parse-index.json")
}

func loadCloudParseIndex(parseRoot string) (cloudParseIndex, error) {
	path := cloudParseIndexPath(parseRoot)
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return cloudParseIndex{Entries: map[string]string{}}, nil
		}
		return cloudParseIndex{}, err
	}
	var idx cloudParseIndex
	if err := json.Unmarshal(data, &idx); err != nil {
		return cloudParseIndex{}, err
	}
	if idx.Entries == nil {
		idx.Entries = map[string]string{}
	}
	return idx, nil
}

func persistCloudParseIndex(parseRoot string, idx cloudParseIndex) error {
	if idx.Entries == nil {
		idx.Entries = map[string]string{}
	}
	path := cloudParseIndexPath(parseRoot)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	raw, err := json.Marshal(idx)
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), ".parse-index-*")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	if _, err := tmp.Write(raw); err != nil {
		_ = tmp.Close()
		_ = os.Remove(tmpPath)
		return err
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		_ = os.Remove(tmpPath)
		return err
	}
	if err := tmp.Close(); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}
	if err := os.Rename(tmpPath, path); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}
	return nil
}

func cloudParseIndexKey(sourceID, srcPath string) string {
	return sourceID + "|" + filepath.Clean(srcPath)
}

func nextCloudHashedRelativePath(sourceID, srcPath, key string, entries map[string]string) (string, int) {
	used := make(map[string]struct{}, len(entries))
	for k, v := range entries {
		if k == key {
			continue
		}
		name := strings.TrimSpace(v)
		if name == "" {
			continue
		}
		used[name] = struct{}{}
	}
	for salt := 0; ; salt++ {
		candidate := cloudHashedFileRelativePath(sourceID, srcPath, salt)
		if _, exists := used[candidate]; !exists {
			return candidate, salt
		}
	}
}

func cloudHashedFileRelativePath(sourceID, srcPath string, salt int) string {
	return filepath.Join("sources", sourceID, "files", cloudHashedFileName(sourceID, srcPath, salt))
}

func cloudHashedFileName(sourceID, srcPath string, salt int) string {
	cleanPath := filepath.Clean(srcPath)
	key := sourceID + "|" + cleanPath
	if salt > 0 {
		key = fmt.Sprintf("%s|%d", key, salt)
	}
	sum := sha256.Sum256([]byte(key))
	hash := hex.EncodeToString(sum[:16])
	ext := filepath.Ext(filepath.Base(cleanPath))
	if ext == "" {
		return hash
	}
	return hash + ext
}

func deriveCloudSourceRootFromMirrorPath(srcPath string) string {
	clean := filepath.Clean(strings.TrimSpace(srcPath))
	if clean == "" || clean == "." {
		return ""
	}
	needle := string(filepath.Separator) + sourcelayout.CloudMirrorDirName + string(filepath.Separator)
	idx := strings.Index(clean, needle)
	if idx <= 0 {
		return ""
	}
	return clean[:idx]
}

func joinUnderRoot(root, relPath string) (string, error) {
	cleanRoot := filepath.Clean(strings.TrimSpace(root))
	if cleanRoot == "" || cleanRoot == "." {
		return "", fmt.Errorf("empty root")
	}
	candidate := filepath.Clean(filepath.Join(cleanRoot, relPath))
	if candidate != cleanRoot && !strings.HasPrefix(candidate, cleanRoot+string(filepath.Separator)) {
		return "", fmt.Errorf("path escapes root")
	}
	return candidate, nil
}

func copyFileAtomic(src, dst string, modTime time.Time) (_ int64, retErr error) {
	in, err := os.Open(src)
	if err != nil {
		return 0, err
	}
	defer in.Close()

	tmp, err := os.CreateTemp(filepath.Dir(dst), ".stage-*")
	if err != nil {
		return 0, err
	}
	tmpPath := tmp.Name()
	defer func() {
		if retErr != nil {
			_ = os.Remove(tmpPath)
		}
	}()

	written, err := io.Copy(tmp, in)
	if err != nil {
		_ = tmp.Close()
		return 0, err
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		return 0, err
	}
	if err := tmp.Close(); err != nil {
		return 0, err
	}
	if err := os.Chtimes(tmpPath, modTime, modTime); err != nil {
		return 0, err
	}
	_ = os.Remove(dst)
	if err := os.Rename(tmpPath, dst); err != nil {
		return 0, err
	}
	return written, nil
}
