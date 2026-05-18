package worker

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/lazymind/scan_control_plane/internal/config"
	"github.com/lazymind/scan_control_plane/internal/coreclient"
	"github.com/lazymind/scan_control_plane/internal/store"
	"go.uber.org/zap"
)

func TestRetryBackoff(t *testing.T) {
	t.Parallel()
	base := 2 * time.Second
	max := 30 * time.Second
	cases := []struct {
		retry int
		want  time.Duration
	}{
		{retry: 1, want: 2 * time.Second},
		{retry: 2, want: 4 * time.Second},
		{retry: 3, want: 8 * time.Second},
		{retry: 4, want: 16 * time.Second},
		{retry: 5, want: 30 * time.Second},
		{retry: 10, want: 30 * time.Second},
	}
	for _, tc := range cases {
		if got := retryBackoff(base, max, tc.retry); got != tc.want {
			t.Fatalf("retry=%d: expected %v, got %v", tc.retry, tc.want, got)
		}
	}
}

func TestIsCloudSyncOrigin(t *testing.T) {
	t.Parallel()
	cases := []struct {
		origin string
		want   bool
	}{
		{origin: "CLOUD_SYNC", want: true},
		{origin: "cloud_sync", want: true},
		{origin: "LOCAL_FS", want: false},
		{origin: "", want: false},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.origin, func(t *testing.T) {
			t.Parallel()
			if got := isCloudSyncOrigin(tc.origin); got != tc.want {
				t.Fatalf("origin=%q, want %v, got %v", tc.origin, tc.want, got)
			}
		})
	}
}

func TestStageFromCloudMirror(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	sourceRoot := filepath.Join(dir, "src_1")
	path := filepath.Join(sourceRoot, "mirror", "docs", "doc.md")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir mirror dir failed: %v", err)
	}
	content := "hello cloud sync"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write temp mirror file failed: %v", err)
	}

	w := &Worker{log: zap.NewNop()}
	resp, err := w.stageFromCloudMirror(store.PendingTask{
		TaskID:         1,
		SourceID:       "src-1",
		SourceRootPath: sourceRoot,
		SourceObjectID: path,
	})
	if err != nil {
		t.Fatalf("stageFromCloudMirror failed: %v", err)
	}
	parseRoot := filepath.Join(sourceRoot, "parse")
	if !strings.HasPrefix(resp.HostPath, parseRoot+string(filepath.Separator)) {
		t.Fatalf("expected parse path under %q, got %q", parseRoot, resp.HostPath)
	}
	if !strings.HasPrefix(resp.URI, "file://") {
		t.Fatalf("expected file URI, got %q", resp.URI)
	}
	if resp.Size != int64(len(content)) {
		t.Fatalf("expected size %d, got %d", len(content), resp.Size)
	}
	raw, err := os.ReadFile(resp.HostPath)
	if err != nil {
		t.Fatalf("read staged parse file failed: %v", err)
	}
	if string(raw) != content {
		t.Fatalf("expected staged content %q, got %q", content, string(raw))
	}
}

func TestStageFromCloudMirrorMissingFile(t *testing.T) {
	t.Parallel()
	w := &Worker{log: zap.NewNop()}
	_, err := w.stageFromCloudMirror(store.PendingTask{
		TaskID:         1,
		SourceID:       "src-1",
		SourceObjectID: "/tmp/does-not-exist-doc.md",
	})
	if err == nil {
		t.Fatalf("expected error for missing mirror file")
	}
}

func TestExecuteTaskSkipsCoreSubmissionWhenValidationRejects(t *testing.T) {
	t.Parallel()
	st := &fakeWorkerStore{
		desiredMatches: true,
		validation: store.TaskSubmissionValidation{
			Valid:  false,
			Reason: "target_version_id no longer matches desired_version_id",
		},
	}
	core := &fakeCoreClient{}
	cfg := config.WorkerConfig{
		MaxPerTenant:     1,
		MaxPerSource:     1,
		MaxLargeFile:     1,
		RetryBaseBackoff: time.Millisecond,
		RetryMaxBackoff:  time.Millisecond,
	}
	w := &Worker{
		cfg:     cfg,
		store:   st,
		core:    core,
		log:     zap.NewNop(),
		limiter: newTaskLimiter(cfg),
	}

	w.executeTask(context.Background(), store.PendingTask{
		TaskID:          1,
		TenantID:        "tenant-1",
		SourceID:        "src-1",
		DocumentID:      10,
		TaskAction:      "DELETE",
		TargetVersionID: "d_1",
		MaxRetryCount:   1,
	})

	if core.submitCalls != 0 {
		t.Fatalf("expected stale task not to submit to core, got %d calls", core.submitCalls)
	}
	if st.supersededTaskID != 1 {
		t.Fatalf("expected task 1 superseded, got %d", st.supersededTaskID)
	}
	if st.supersededReason != "target_version_id no longer matches desired_version_id" {
		t.Fatalf("unexpected superseded reason %q", st.supersededReason)
	}
}

type fakeWorkerStore struct {
	desiredMatches   bool
	validation       store.TaskSubmissionValidation
	supersededTaskID int64
	supersededReason string
}

func (f *fakeWorkerStore) ClaimDueTasks(context.Context, string, time.Time, int, time.Duration) ([]store.PendingTask, error) {
	return nil, nil
}

func (f *fakeWorkerStore) MarkTaskSuperseded(_ context.Context, taskID int64, reason string) error {
	f.supersededTaskID = taskID
	f.supersededReason = reason
	return nil
}

func (f *fakeWorkerStore) MarkTaskStaging(context.Context, int64) error {
	return nil
}

func (f *fakeWorkerStore) ValidateTaskSubmission(context.Context, int64) (store.TaskSubmissionValidation, error) {
	return f.validation, nil
}

func (f *fakeWorkerStore) FindSubmittedTaskByIdempotencyKey(context.Context, string, string, int64) (store.SubmittedCoreTaskRef, error) {
	return store.SubmittedCoreTaskRef{}, nil
}

func (f *fakeWorkerStore) MarkTaskSubmitted(context.Context, int64, string, string, string, time.Time) error {
	return nil
}

func (f *fakeWorkerStore) MarkTaskSubmitFailed(context.Context, int64, string) error {
	return nil
}

func (f *fakeWorkerStore) MarkTaskRetryWaiting(context.Context, int64, int, time.Time, string) error {
	return nil
}

func (f *fakeWorkerStore) MarkTaskFailed(context.Context, int64, string) error {
	return nil
}

func (f *fakeWorkerStore) MarkTaskSucceeded(context.Context, int64, int64, string) error {
	return nil
}

func (f *fakeWorkerStore) DesiredVersionMatches(context.Context, int64, string) (bool, error) {
	return f.desiredMatches, nil
}

func (f *fakeWorkerStore) UpdateDocumentRunning(context.Context, int64) error {
	return nil
}

func (f *fakeWorkerStore) RequeueTimedOutCommands(context.Context, time.Time, time.Duration, int) (int64, error) {
	return 0, nil
}

func (f *fakeWorkerStore) FailExhaustedCommands(context.Context, int) (int64, error) {
	return 0, nil
}

func (f *fakeWorkerStore) MarkAgentsOffline(context.Context, time.Time, time.Duration) (int64, error) {
	return 0, nil
}

func (f *fakeWorkerStore) EnqueueStageCommand(context.Context, string, store.StageCommandPayload) (int64, error) {
	return 0, nil
}

func (f *fakeWorkerStore) AwaitCommandResult(context.Context, int64, time.Duration) (string, error) {
	return "", nil
}

type fakeCoreClient struct {
	submitCalls int
}

func (f *fakeCoreClient) Enabled() bool {
	return true
}

func (f *fakeCoreClient) SubmitParseTask(context.Context, store.PendingTask, string, string, int64) (coreclient.SubmitResult, error) {
	f.submitCalls++
	return coreclient.SubmitResult{DatasetID: "ds-1", DocumentID: "doc-1"}, nil
}

func (f *fakeCoreClient) CreateKnowledgeBase(context.Context, coreclient.CreateKnowledgeBaseRequest) (coreclient.CreateKnowledgeBaseResult, error) {
	return coreclient.CreateKnowledgeBaseResult{}, nil
}

func (f *fakeCoreClient) FindKnowledgeBaseByName(context.Context, string, string, string) (coreclient.KnowledgeBaseRef, bool, error) {
	return coreclient.KnowledgeBaseRef{}, false, nil
}

func (f *fakeCoreClient) DeleteDataset(context.Context, string, string, string) error {
	return nil
}

func (f *fakeCoreClient) SearchTasks(context.Context, []string) (map[string]coreclient.TaskState, error) {
	return nil, nil
}

func (f *fakeCoreClient) SearchTasksByDataset(context.Context, string, []string) (map[string]coreclient.TaskState, error) {
	return nil, nil
}

func (f *fakeCoreClient) SearchTasksByDatasetAs(context.Context, string, []string, string, string) (map[string]coreclient.TaskState, error) {
	return nil, nil
}
