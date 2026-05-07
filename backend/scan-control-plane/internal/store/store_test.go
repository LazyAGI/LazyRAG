package store

import (
	"context"
	"errors"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"go.uber.org/zap"

	"github.com/lazyrag/scan_control_plane/internal/model"
	"github.com/lazyrag/scan_control_plane/internal/sourcelayout"
)

func newTestStore(t *testing.T) *Store {
	t.Helper()
	dbPath := filepath.Join(t.TempDir(), "cp.db")
	st, err := New("sqlite", dbPath, 10*time.Second, zap.NewNop())
	if err != nil {
		t.Fatalf("new store failed: %v", err)
	}
	t.Cleanup(func() {
		_ = st.Close()
	})
	return st
}

func createTestSource(t *testing.T, st *Store) model.Source {
	t.Helper()
	src, err := st.CreateSource(context.Background(), model.CreateSourceRequest{
		TenantID:          "tenant-1",
		Name:              "src",
		RootPath:          "/tmp/watch",
		AgentID:           "agent-1",
		WatchEnabled:      true,
		IdleWindowSeconds: 10,
	})
	if err != nil {
		t.Fatalf("create source failed: %v", err)
	}
	return src
}

func TestBatchApplyDocumentMutationsLatestWins(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)

	newer := time.Now().UTC()
	older := newer.Add(-10 * time.Second)

	events := []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: "/tmp/watch/a.txt", OccurredAt: newer},
	}
	mutations, err := st.BuildMutationsFromEvents(context.Background(), events)
	if err != nil {
		t.Fatalf("build mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(context.Background(), mutations); err != nil {
		t.Fatalf("apply newer mutation failed: %v", err)
	}

	events = []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: "/tmp/watch/a.txt", OccurredAt: older},
	}
	mutations, err = st.BuildMutationsFromEvents(context.Background(), events)
	if err != nil {
		t.Fatalf("build older mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(context.Background(), mutations); err != nil {
		t.Fatalf("apply older mutation failed: %v", err)
	}

	var doc documentEntity
	if err := st.db.WithContext(context.Background()).
		Where("tenant_id = ? AND source_id = ? AND source_object_id = ?", src.TenantID, src.ID, "/tmp/watch/a.txt").
		Take(&doc).Error; err != nil {
		t.Fatalf("load document failed: %v", err)
	}
	if doc.LastModifiedAt == nil {
		t.Fatalf("last_modified_at should not be nil")
	}
	if !doc.LastModifiedAt.Equal(newer) {
		t.Fatalf("expected last_modified_at=%v, got %v", newer, doc.LastModifiedAt)
	}
}

func TestBatchApplyDocumentMutationsCloudRenameByOriginRef(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()

	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:              "tenant-cloud",
		Name:                  "cloud-src",
		AgentID:               "agent-1",
		DefaultOriginType:     string(model.OriginTypeCloudSync),
		DefaultOriginPlatform: "FEISHU",
	})
	if err != nil {
		t.Fatalf("create cloud source failed: %v", err)
	}

	originRef := "obj_rename_001"
	oldPath := "/tmp/cloud/src/mirror/docs/spec.md"
	newPath := "/tmp/cloud/src/mirror/docs/spec.docx"
	firstAt := time.Now().UTC().Add(-2 * time.Minute)
	secondAt := firstAt.Add(10 * time.Second)

	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{
			SourceID:       src.ID,
			EventType:      "modified",
			Path:           oldPath,
			OccurredAt:     firstAt,
			OriginType:     string(model.OriginTypeCloudSync),
			OriginPlatform: "FEISHU",
			OriginRef:      originRef,
		},
	})
	if err != nil {
		t.Fatalf("build first cloud mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply first cloud mutations failed: %v", err)
	}
	doc := loadDocumentByPath(t, st, src, oldPath)
	if err := st.db.WithContext(ctx).Model(&documentEntity{}).Where("id = ?", doc.ID).Updates(map[string]any{
		"core_document_id":   "core_doc_rename",
		"current_version_id": "v_old",
	}).Error; err != nil {
		t.Fatalf("prepare core document fields failed: %v", err)
	}

	mutations, err = st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{
			SourceID:       src.ID,
			EventType:      "modified",
			Path:           newPath,
			OccurredAt:     secondAt,
			OriginType:     string(model.OriginTypeCloudSync),
			OriginPlatform: "FEISHU",
			OriginRef:      originRef,
		},
	})
	if err != nil {
		t.Fatalf("build rename cloud mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply rename cloud mutations failed: %v", err)
	}

	var docs []documentEntity
	if err := st.db.WithContext(ctx).Where("source_id = ?", src.ID).Find(&docs).Error; err != nil {
		t.Fatalf("query cloud documents failed: %v", err)
	}
	if len(docs) != 1 {
		t.Fatalf("expected 1 document after rename, got %d", len(docs))
	}
	renamed := docs[0]
	if renamed.SourceObjectID != newPath {
		t.Fatalf("expected renamed source_object_id=%s, got %s", newPath, renamed.SourceObjectID)
	}
	if renamed.CoreDocumentID != "core_doc_rename" {
		t.Fatalf("expected core_document_id to be preserved, got %s", renamed.CoreDocumentID)
	}

	var oldCount int64
	if err := st.db.WithContext(ctx).
		Model(&documentEntity{}).
		Where("source_id = ? AND source_object_id = ?", src.ID, oldPath).
		Count(&oldCount).Error; err != nil {
		t.Fatalf("count old path failed: %v", err)
	}
	if oldCount != 0 {
		t.Fatalf("expected old path document removed after rename, still has %d rows", oldCount)
	}

	created, err := st.ScheduleDueParses(ctx, secondAt.Add(20*time.Second))
	if err != nil {
		t.Fatalf("schedule due parses after rename failed: %v", err)
	}
	if created != 1 {
		t.Fatalf("expected created parse task count=1, got %d", created)
	}
	tasks := loadTasksByDocumentID(t, st, renamed.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected 1 parse task for renamed document, got %d", len(tasks))
	}
	if normalizeTaskAction(tasks[0].TaskAction) != taskActionReparse {
		t.Fatalf("expected task_action REPARSE for renamed document, got %s", tasks[0].TaskAction)
	}
}

func TestPullAndAckCommandFlow(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	_ = createTestSource(t, st)

	resp, err := st.PullPendingCommands(context.Background(), model.PullCommandsRequest{
		AgentID:  "agent-1",
		TenantID: "tenant-1",
	})
	if err != nil {
		t.Fatalf("pull pending commands failed: %v", err)
	}
	if len(resp.Commands) == 0 {
		t.Fatalf("expected at least one command")
	}
	cmd := resp.Commands[0]
	if cmd.ID <= 0 {
		t.Fatalf("expected command id > 0")
	}

	if err := st.AckCommand(context.Background(), model.AckCommandRequest{
		AgentID:   "agent-1",
		CommandID: cmd.ID,
		Success:   true,
	}); err != nil {
		t.Fatalf("ack command failed: %v", err)
	}

	var entity agentCommandEntity
	if err := st.db.WithContext(context.Background()).Take(&entity, "id = ?", cmd.ID).Error; err != nil {
		t.Fatalf("load command failed: %v", err)
	}
	if entity.Status != commandStatusAcked {
		t.Fatalf("expected status %s, got %s", commandStatusAcked, entity.Status)
	}
}

func TestPullPendingCommandsSkipsDecodeFailedPayload(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()

	if err := st.db.WithContext(ctx).Where("1 = 1").Delete(&agentCommandEntity{}).Error; err != nil {
		t.Fatalf("clear commands failed: %v", err)
	}

	now := time.Now().UTC()
	bad := agentCommandEntity{
		AgentID:     src.AgentID,
		Type:        string(model.CommandStartSource),
		Payload:     "{not-json",
		Status:      commandStatusPending,
		NextRetryAt: &now,
		CreatedAt:   now,
	}
	if err := st.db.WithContext(ctx).Create(&bad).Error; err != nil {
		t.Fatalf("create bad command failed: %v", err)
	}
	good := agentCommandEntity{
		AgentID:     src.AgentID,
		Type:        string(model.CommandStartSource),
		Payload:     `{"source_id":"src-ok","tenant_id":"tenant-1","root_path":"/tmp/watch"}`,
		Status:      commandStatusPending,
		CreatedAt:   now.Add(1 * time.Millisecond),
		NextRetryAt: &now,
	}
	if err := st.db.WithContext(ctx).Create(&good).Error; err != nil {
		t.Fatalf("create good command failed: %v", err)
	}

	pulled, err := st.PullPendingCommands(ctx, model.PullCommandsRequest{
		AgentID:  src.AgentID,
		TenantID: src.TenantID,
	})
	if err != nil {
		t.Fatalf("pull pending commands failed: %v", err)
	}
	if len(pulled.Commands) != 1 {
		t.Fatalf("expected exactly 1 decodable command, got %d", len(pulled.Commands))
	}
	if pulled.Commands[0].ID != good.ID {
		t.Fatalf("expected pulled command id=%d, got %d", good.ID, pulled.Commands[0].ID)
	}

	var badAfter agentCommandEntity
	if err := st.db.WithContext(ctx).Take(&badAfter, "id = ?", bad.ID).Error; err != nil {
		t.Fatalf("load bad command failed: %v", err)
	}
	if badAfter.Status != commandStatusPending {
		t.Fatalf("expected bad command stay pending, got %s", badAfter.Status)
	}
	if badAfter.DispatchedAt != nil {
		t.Fatalf("expected bad command dispatched_at to remain nil")
	}

	var goodAfter agentCommandEntity
	if err := st.db.WithContext(ctx).Take(&goodAfter, "id = ?", good.ID).Error; err != nil {
		t.Fatalf("load good command failed: %v", err)
	}
	if goodAfter.Status != commandStatusDispatched {
		t.Fatalf("expected good command status %s, got %s", commandStatusDispatched, goodAfter.Status)
	}
	if goodAfter.DispatchedAt == nil || goodAfter.DispatchedAt.IsZero() {
		t.Fatalf("expected good command dispatched_at to be set")
	}
}

func TestScheduleDueParsesKeepsHistoryAfterSuccess(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	path := "/tmp/watch/a.txt"

	firstAt := time.Now().UTC().Add(-40 * time.Second)
	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: firstAt},
	})
	if err != nil {
		t.Fatalf("build first mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply first mutations failed: %v", err)
	}

	created, err := st.ScheduleDueParses(ctx, firstAt.Add(12*time.Second))
	if err != nil {
		t.Fatalf("schedule first due parse failed: %v", err)
	}
	if created != 1 {
		t.Fatalf("expected first created=1, got %d", created)
	}

	doc := loadDocumentByPath(t, st, src, path)
	tasks := loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected 1 task after first schedule, got %d", len(tasks))
	}
	if tasks[0].Status != "PENDING" {
		t.Fatalf("expected first task status PENDING, got %s", tasks[0].Status)
	}

	if err := st.MarkTaskSucceeded(ctx, tasks[0].ID, doc.ID, tasks[0].TargetVersionID); err != nil {
		t.Fatalf("mark first task succeeded failed: %v", err)
	}

	secondAt := firstAt.Add(20 * time.Second)
	mutations, err = st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: secondAt},
	})
	if err != nil {
		t.Fatalf("build second mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply second mutations failed: %v", err)
	}

	created, err = st.ScheduleDueParses(ctx, secondAt.Add(12*time.Second))
	if err != nil {
		t.Fatalf("schedule second due parse failed: %v", err)
	}
	if created != 1 {
		t.Fatalf("expected second created=1, got %d", created)
	}

	tasks = loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 2 {
		t.Fatalf("expected 2 task history rows, got %d", len(tasks))
	}
	if tasks[0].Status != "SUCCEEDED" {
		t.Fatalf("expected first task status SUCCEEDED, got %s", tasks[0].Status)
	}
	if tasks[1].Status != "PENDING" {
		t.Fatalf("expected second task status PENDING, got %s", tasks[1].Status)
	}
	if tasks[0].ID == tasks[1].ID {
		t.Fatalf("expected distinct task rows, got same id=%d", tasks[0].ID)
	}
}

func TestScheduleDueParsesMergesSinglePendingTask(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	path := "/tmp/watch/b.txt"

	firstAt := time.Now().UTC().Add(-40 * time.Second)
	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: firstAt},
	})
	if err != nil {
		t.Fatalf("build first mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply first mutations failed: %v", err)
	}

	created, err := st.ScheduleDueParses(ctx, firstAt.Add(12*time.Second))
	if err != nil {
		t.Fatalf("schedule first due parse failed: %v", err)
	}
	if created != 1 {
		t.Fatalf("expected first created=1, got %d", created)
	}

	doc := loadDocumentByPath(t, st, src, path)
	tasks := loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected 1 pending task, got %d", len(tasks))
	}
	firstTarget := tasks[0].TargetVersionID

	secondAt := firstAt.Add(20 * time.Second)
	mutations, err = st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: secondAt},
	})
	if err != nil {
		t.Fatalf("build second mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply second mutations failed: %v", err)
	}

	created, err = st.ScheduleDueParses(ctx, secondAt.Add(12*time.Second))
	if err != nil {
		t.Fatalf("schedule second due parse failed: %v", err)
	}
	if created != 0 {
		t.Fatalf("expected second created=0 (merge pending), got %d", created)
	}

	doc = loadDocumentByPath(t, st, src, path)
	tasks = loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected still 1 task row, got %d", len(tasks))
	}
	if tasks[0].Status != "PENDING" {
		t.Fatalf("expected merged task status PENDING, got %s", tasks[0].Status)
	}
	if tasks[0].TargetVersionID == firstTarget {
		t.Fatalf("expected merged task target_version to be refreshed, still %s", tasks[0].TargetVersionID)
	}
	if tasks[0].TargetVersionID != doc.DesiredVersionID {
		t.Fatalf("expected merged task target_version=%s, got %s", doc.DesiredVersionID, tasks[0].TargetVersionID)
	}
}

func TestCreateSourceReusesSameRootPath(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	req := model.CreateSourceRequest{
		TenantID:          "tenant-1",
		Name:              "src-1",
		RootPath:          "/tmp/watch",
		AgentID:           "agent-1",
		WatchEnabled:      false,
		IdleWindowSeconds: 10,
	}
	first, err := st.CreateSource(ctx, req)
	if err != nil {
		t.Fatalf("create first source failed: %v", err)
	}
	req.Name = "src-2"
	second, err := st.CreateSource(ctx, req)
	if err != nil {
		t.Fatalf("create second source failed: %v", err)
	}
	if first.ID != second.ID {
		t.Fatalf("expected same source id, got first=%s second=%s", first.ID, second.ID)
	}
	var count int64
	if err := st.db.WithContext(ctx).Model(&sourceEntity{}).Count(&count).Error; err != nil {
		t.Fatalf("count sources failed: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected only 1 source row, got %d", count)
	}
	var cmdCount int64
	if err := st.db.WithContext(ctx).Model(&agentCommandEntity{}).Count(&cmdCount).Error; err != nil {
		t.Fatalf("count commands failed: %v", err)
	}
	if cmdCount != 0 {
		t.Fatalf("expected no commands when watch disabled, got %d", cmdCount)
	}
}

func TestCreateCloudSourceAutoRootPath(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()

	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:              "tenant-cloud",
		Name:                  "cloud-src",
		RootPath:              "",
		AgentID:               "agent-1",
		DefaultOriginType:     "CLOUD_SYNC",
		DefaultOriginPlatform: "FEISHU",
	})
	if err != nil {
		t.Fatalf("create cloud source failed: %v", err)
	}
	if !strings.HasPrefix(src.RootPath, sourcelayout.CloudSourceBaseRoot+string(filepath.Separator)) {
		t.Fatalf("expected auto cloud root path under %q, got %q", sourcelayout.CloudSourceBaseRoot, src.RootPath)
	}
	if src.SourceType != "cloud_sync" {
		t.Fatalf("expected source_type=cloud_sync, got %s", src.SourceType)
	}
	if src.WatchEnabled {
		t.Fatalf("expected cloud source watch_enabled=false")
	}
	if !strings.EqualFold(src.DefaultOriginType, "CLOUD_SYNC") {
		t.Fatalf("expected default_origin_type=CLOUD_SYNC, got %s", src.DefaultOriginType)
	}
}

func TestGenerateTasksForSourceQueuesBaselineSnapshot(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:          "tenant-1",
		Name:              "src",
		RootPath:          "/tmp/watch",
		AgentID:           "agent-1",
		WatchEnabled:      false,
		IdleWindowSeconds: 10,
	})
	if err != nil {
		t.Fatalf("create source failed: %v", err)
	}
	resp, err := st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:  "partial",
		Paths: []string{"/tmp/watch/a.txt"},
	})
	if err != nil {
		t.Fatalf("generate tasks failed: %v", err)
	}
	if !resp.BaselineSnapshotQueued {
		t.Fatalf("expected baseline snapshot queued")
	}
	if resp.AcceptedCount != 1 {
		t.Fatalf("expected accepted_count=1, got %d", resp.AcceptedCount)
	}

	pulled, err := st.PullPendingCommands(ctx, model.PullCommandsRequest{
		AgentID:  "agent-1",
		TenantID: "tenant-1",
	})
	if err != nil {
		t.Fatalf("pull commands failed: %v", err)
	}
	if len(pulled.Commands) != 1 {
		t.Fatalf("expected 1 command, got %d", len(pulled.Commands))
	}
	if pulled.Commands[0].Type != model.CommandSnapshotSource {
		t.Fatalf("expected snapshot_source command, got %s", pulled.Commands[0].Type)
	}
}

func TestGenerateTasksForSourceCreatesManualPullJob(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:          "tenant-1",
		Name:              "src-jobs",
		RootPath:          "/tmp/watch",
		AgentID:           "agent-1",
		WatchEnabled:      false,
		IdleWindowSeconds: 10,
	})
	if err != nil {
		t.Fatalf("create source failed: %v", err)
	}
	resp, err := st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:  "partial",
		Paths: []string{"/tmp/watch/job-a.txt", "/tmp/watch/job-b.txt"},
	})
	if err != nil {
		t.Fatalf("generate tasks failed: %v", err)
	}
	if strings.TrimSpace(resp.ManualPullJobID) == "" {
		t.Fatalf("expected non-empty manual_pull_job_id")
	}
	list, err := st.ListManualPullJobs(ctx, src.ID, model.ListManualPullJobsRequest{
		Page:     1,
		PageSize: 10,
	})
	if err != nil {
		t.Fatalf("list manual pull jobs failed: %v", err)
	}
	if len(list.Items) != 1 {
		t.Fatalf("expected 1 manual pull job, got %d", len(list.Items))
	}
	job := list.Items[0]
	if job.JobID != resp.ManualPullJobID {
		t.Fatalf("expected job_id=%s, got %s", resp.ManualPullJobID, job.JobID)
	}
	if job.Status != "SUCCEEDED" {
		t.Fatalf("expected status SUCCEEDED, got %s", job.Status)
	}
	if job.AcceptedCount != 2 {
		t.Fatalf("expected accepted_count=2, got %d", job.AcceptedCount)
	}
}

func TestDisableSourceWatchEnqueuesSnapshotThenStop(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	src := createTestSource(t, st)

	// clear initial start_source command
	pulled, err := st.PullPendingCommands(ctx, model.PullCommandsRequest{
		AgentID:  "agent-1",
		TenantID: "tenant-1",
	})
	if err != nil {
		t.Fatalf("pull initial commands failed: %v", err)
	}
	for _, cmd := range pulled.Commands {
		if err := st.AckCommand(ctx, model.AckCommandRequest{
			AgentID:   "agent-1",
			CommandID: cmd.ID,
			Success:   true,
		}); err != nil {
			t.Fatalf("ack initial command %d failed: %v", cmd.ID, err)
		}
	}

	updated, baselineQueued, err := st.DisableSourceWatch(ctx, src.ID)
	if err != nil {
		t.Fatalf("disable source watch failed: %v", err)
	}
	if !baselineQueued {
		t.Fatalf("expected baseline snapshot queued")
	}
	if updated.WatchEnabled {
		t.Fatalf("expected watch_enabled=false")
	}

	pulled, err = st.PullPendingCommands(ctx, model.PullCommandsRequest{
		AgentID:  "agent-1",
		TenantID: "tenant-1",
	})
	if err != nil {
		t.Fatalf("pull commands failed: %v", err)
	}
	if len(pulled.Commands) != 2 {
		t.Fatalf("expected 2 commands, got %d", len(pulled.Commands))
	}
	if pulled.Commands[0].Type != model.CommandSnapshotSource {
		t.Fatalf("expected first command snapshot_source, got %s", pulled.Commands[0].Type)
	}
	if pulled.Commands[1].Type != model.CommandStopSource {
		t.Fatalf("expected second command stop_source, got %s", pulled.Commands[1].Type)
	}
}

func TestExpediteTasksByPathsUpdatesExistingPendingTask(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	path := "/tmp/watch/expedite.txt"
	eventAt := time.Now().UTC().Add(-40 * time.Second)

	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: eventAt},
	})
	if err != nil {
		t.Fatalf("build mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply mutations failed: %v", err)
	}
	if _, err := st.ScheduleDueParses(ctx, eventAt.Add(12*time.Second)); err != nil {
		t.Fatalf("schedule due parse failed: %v", err)
	}
	doc := loadDocumentByPath(t, st, src, path)
	tasks := loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected 1 task, got %d", len(tasks))
	}
	taskID := tasks[0].ID
	future := time.Now().UTC().Add(1 * time.Hour)
	if err := st.db.WithContext(ctx).Model(&parseTaskEntity{}).Where("id = ?", taskID).Update("next_run_at", future).Error; err != nil {
		t.Fatalf("set future next_run_at failed: %v", err)
	}

	exp, err := st.ExpediteTasksByPaths(ctx, src.ID, model.ExpediteTasksRequest{
		Paths: []string{path},
	})
	if err != nil {
		t.Fatalf("expedite tasks failed: %v", err)
	}
	if exp.UpdatedExistingTaskCount != 1 {
		t.Fatalf("expected updated_existing_task_count=1, got %d", exp.UpdatedExistingTaskCount)
	}
	tasks = loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 || tasks[0].ID != taskID {
		t.Fatalf("expected same single task id=%d, got %+v", taskID, tasks)
	}
	if tasks[0].NextRunAt.After(time.Now().UTC().Add(2 * time.Second)) {
		t.Fatalf("expected next_run_at updated to now, got %v", tasks[0].NextRunAt)
	}
}

func loadDocumentByPath(t *testing.T, st *Store, src model.Source, path string) documentEntity {
	t.Helper()
	var doc documentEntity
	if err := st.db.WithContext(context.Background()).
		Where("tenant_id = ? AND source_id = ? AND source_object_id = ?", src.TenantID, src.ID, path).
		Take(&doc).Error; err != nil {
		t.Fatalf("load document failed: %v", err)
	}
	return doc
}

func loadTasksByDocumentID(t *testing.T, st *Store, documentID int64) []parseTaskEntity {
	t.Helper()
	var tasks []parseTaskEntity
	if err := st.db.WithContext(context.Background()).
		Where("document_id = ?", documentID).
		Order("id ASC").
		Find(&tasks).Error; err != nil {
		t.Fatalf("load tasks failed: %v", err)
	}
	return tasks
}

func findTreeNodeByPath(items []model.TreeNode, path string) (model.TreeNode, bool) {
	for _, item := range items {
		if item.Key == path {
			return item, true
		}
		if len(item.Children) > 0 {
			if found, ok := findTreeNodeByPath(item.Children, path); ok {
				return found, true
			}
		}
	}
	return model.TreeNode{}, false
}

func TestListParseTasksAndStats(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	path := "/tmp/watch/list-task.txt"
	eventAt := time.Now().UTC().Add(-40 * time.Second)

	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: eventAt},
	})
	if err != nil {
		t.Fatalf("build mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply mutations failed: %v", err)
	}
	if _, err := st.ScheduleDueParses(ctx, eventAt.Add(12*time.Second)); err != nil {
		t.Fatalf("schedule due parses failed: %v", err)
	}

	listResp, err := st.ListParseTasks(ctx, model.ListParseTasksRequest{
		TenantID: src.TenantID,
		SourceID: src.ID,
		Page:     1,
		PageSize: 20,
	})
	if err != nil {
		t.Fatalf("list parse tasks failed: %v", err)
	}
	if listResp.Total != 1 {
		t.Fatalf("expected total=1, got %d", listResp.Total)
	}
	if len(listResp.Items) != 1 {
		t.Fatalf("expected 1 item, got %d", len(listResp.Items))
	}
	if listResp.Items[0].SourceObjectID != path {
		t.Fatalf("expected source_object_id=%s, got %s", path, listResp.Items[0].SourceObjectID)
	}
	if listResp.Items[0].Status != "PENDING" {
		t.Fatalf("expected task status PENDING, got %s", listResp.Items[0].Status)
	}

	stats, err := st.CountParseTasksByStatusWithFilter(ctx, src.TenantID, src.ID)
	if err != nil {
		t.Fatalf("count parse tasks by status failed: %v", err)
	}
	if stats["PENDING"] != 1 {
		t.Fatalf("expected PENDING=1, got %d", stats["PENDING"])
	}
}

func TestDeleteSourceCascadesAndStopsWatcher(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	path := "/tmp/watch/delete-source.txt"
	eventAt := time.Now().UTC().Add(-40 * time.Second)

	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: eventAt},
	})
	if err != nil {
		t.Fatalf("build mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply mutations failed: %v", err)
	}
	if _, err := st.ScheduleDueParses(ctx, eventAt.Add(12*time.Second)); err != nil {
		t.Fatalf("schedule due parses failed: %v", err)
	}
	doc := loadDocumentByPath(t, st, src, path)
	tasks := loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected one parse task, got %d", len(tasks))
	}
	if err := st.MarkTaskFailed(ctx, tasks[0].ID, "delete source test failure"); err != nil {
		t.Fatalf("mark task failed failed: %v", err)
	}
	if _, _, err := st.BuildTreeUpdateState(ctx, src.ID, []model.TreeNode{{Title: "delete-source.txt", Key: path, IsDir: false}}, nil); err != nil {
		t.Fatalf("build tree update state failed: %v", err)
	}
	if _, err := st.UpsertCloudSourceBinding(ctx, src.ID, model.UpsertCloudSourceBindingRequest{
		Provider:         "feishu",
		Enabled:          boolPtr(true),
		AuthConnectionID: "conn_delete_source",
		ScheduleExpr:     "daily@05:00",
		ScheduleTZ:       "Asia/Shanghai",
	}); err != nil {
		t.Fatalf("upsert cloud binding failed: %v", err)
	}
	if _, err := st.TriggerCloudSync(ctx, src.ID, model.TriggerCloudSyncRequest{TriggerType: "manual"}); err != nil {
		t.Fatalf("trigger cloud sync failed: %v", err)
	}
	if err := st.UpsertCloudObjectIndexBatch(ctx, src.ID, "feishu", []CloudObjectIndexRecord{
		{ExternalObjectID: "obj_delete_source", ExternalPath: "/docs/delete-source.txt", LocalAbsPath: path},
	}, time.Now().UTC()); err != nil {
		t.Fatalf("upsert cloud object index failed: %v", err)
	}
	now := time.Now().UTC()
	if err := st.db.WithContext(ctx).Create(&reconcileSnapshotEntity{
		SourceID:    src.ID,
		SnapshotRef: "local://snapshot/delete-source.json",
		FileCount:   1,
		TakenAt:     now,
		UpdatedAt:   now,
	}).Error; err != nil {
		t.Fatalf("create reconcile snapshot failed: %v", err)
	}
	if err := st.db.WithContext(ctx).Create(&sourceBaselineSnapshotEntity{
		SourceID:    src.ID,
		SnapshotRef: "local://baseline/delete-source.json",
		FileCount:   1,
		TakenAt:     now,
		Reason:      "DELETE_SOURCE_TEST",
		UpdatedAt:   now,
	}).Error; err != nil {
		t.Fatalf("create baseline snapshot failed: %v", err)
	}
	if err := st.db.WithContext(ctx).Create(&manualPullJobEntity{
		JobID:     "mpj_delete_source",
		TenantID:  src.TenantID,
		SourceID:  src.ID,
		Status:    "SUCCEEDED",
		Mode:      "partial",
		CreatedAt: now,
		UpdatedAt: now,
	}).Error; err != nil {
		t.Fatalf("create manual pull job failed: %v", err)
	}

	if err := st.DeleteSource(ctx, src.ID); err != nil {
		t.Fatalf("delete source failed: %v", err)
	}
	if _, err := st.GetSource(ctx, src.ID); err == nil {
		t.Fatalf("expected deleted source lookup to fail")
	}

	for name, target := range map[string]any{
		"documents":                  &documentEntity{},
		"parse_tasks":                &parseTaskEntity{},
		"parse_task_dead_letters":    &parseTaskDeadLetterEntity{},
		"source_file_snapshots":      &sourceFileSnapshotEntity{},
		"source_file_snapshot_items": &sourceFileSnapshotItemEntity{},
		"source_snapshot_relations":  &sourceSnapshotRelationEntity{},
		"source_baseline_snapshots":  &sourceBaselineSnapshotEntity{},
		"reconcile_snapshots":        &reconcileSnapshotEntity{},
		"manual_pull_jobs":           &manualPullJobEntity{},
		"cloud_source_bindings":      &cloudSourceBindingEntity{},
		"cloud_sync_checkpoints":     &cloudSyncCheckpointEntity{},
		"cloud_sync_runs":            &cloudSyncRunEntity{},
		"cloud_object_index":         &cloudObjectIndexEntity{},
	} {
		var count int64
		if err := st.db.WithContext(ctx).Model(target).Count(&count).Error; err != nil {
			t.Fatalf("count %s failed: %v", name, err)
		}
		if count != 0 {
			t.Fatalf("expected %s to be empty after delete, got %d", name, count)
		}
	}

	var commands []agentCommandEntity
	if err := st.db.WithContext(ctx).Order("id ASC").Find(&commands).Error; err != nil {
		t.Fatalf("list agent commands failed: %v", err)
	}
	if len(commands) != 1 {
		t.Fatalf("expected only stop_source command after delete, got %+v", commands)
	}
	if commands[0].Type != string(model.CommandStopSource) {
		t.Fatalf("expected stop_source command, got %s", commands[0].Type)
	}
	if !strings.Contains(commands[0].Payload, `"source_id":"`+src.ID+`"`) {
		t.Fatalf("expected stop command payload to reference source_id %s, got %s", src.ID, commands[0].Payload)
	}
}

func TestRetryParseTask(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	path := "/tmp/watch/retry-task.txt"
	eventAt := time.Now().UTC().Add(-40 * time.Second)

	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: eventAt},
	})
	if err != nil {
		t.Fatalf("build mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply mutations failed: %v", err)
	}
	if _, err := st.ScheduleDueParses(ctx, eventAt.Add(12*time.Second)); err != nil {
		t.Fatalf("schedule due parses failed: %v", err)
	}
	doc := loadDocumentByPath(t, st, src, path)
	tasks := loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected 1 task, got %d", len(tasks))
	}
	taskID := tasks[0].ID
	if err := st.MarkTaskSubmitFailed(ctx, taskID, "mock submit failure"); err != nil {
		t.Fatalf("mark task submit failed failed: %v", err)
	}

	detail, err := st.RetryParseTask(ctx, taskID)
	if err != nil {
		t.Fatalf("retry parse task failed: %v", err)
	}
	if detail.Status != "PENDING" {
		t.Fatalf("expected status PENDING after retry, got %s", detail.Status)
	}
	if detail.ScanOrchestrationStatus != "PENDING" {
		t.Fatalf("expected scan_orchestration_status PENDING, got %s", detail.ScanOrchestrationStatus)
	}
	if detail.RetryCount != 0 {
		t.Fatalf("expected retry_count=0, got %d", detail.RetryCount)
	}
	if detail.LastError != "" {
		t.Fatalf("expected last_error cleared, got %q", detail.LastError)
	}

	doc = loadDocumentByPath(t, st, src, path)
	if doc.ParseStatus != "QUEUED" {
		t.Fatalf("expected document parse_status QUEUED after retry, got %s", doc.ParseStatus)
	}
}

func TestRetryParseTaskRejectsNonSubmitFailed(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	path := "/tmp/watch/retry-reject.txt"
	eventAt := time.Now().UTC().Add(-40 * time.Second)

	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: eventAt},
	})
	if err != nil {
		t.Fatalf("build mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply mutations failed: %v", err)
	}
	if _, err := st.ScheduleDueParses(ctx, eventAt.Add(12*time.Second)); err != nil {
		t.Fatalf("schedule due parses failed: %v", err)
	}
	doc := loadDocumentByPath(t, st, src, path)
	tasks := loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected 1 task, got %d", len(tasks))
	}
	taskID := tasks[0].ID
	if err := st.MarkTaskFailed(ctx, taskID, "mock failure"); err != nil {
		t.Fatalf("mark task failed failed: %v", err)
	}
	if _, err := st.RetryParseTask(ctx, taskID); err == nil {
		t.Fatalf("expected retry to fail for FAILED status")
	}
}

func TestListSourceDocumentsWithUpdateTypeFilter(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	baseAt := time.Now().UTC().Add(-2 * time.Minute)

	newPath := "/tmp/watch/new-file.txt"
	deletePath := "/tmp/watch/deleted-file.txt"

	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: newPath, OccurredAt: baseAt.Add(1 * time.Second)},
		{SourceID: src.ID, EventType: "modified", Path: deletePath, OccurredAt: baseAt.Add(2 * time.Second)},
	})
	if err != nil {
		t.Fatalf("build initial mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply initial mutations failed: %v", err)
	}
	delMutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "deleted", Path: deletePath, OccurredAt: baseAt.Add(3 * time.Second)},
	})
	if err != nil {
		t.Fatalf("build delete mutation failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, delMutations); err != nil {
		t.Fatalf("apply delete mutation failed: %v", err)
	}

	resp, err := st.ListSourceDocuments(ctx, src.ID, model.ListSourceDocumentsRequest{
		TenantID: src.TenantID,
		Page:     1,
		PageSize: 20,
	})
	if err != nil {
		t.Fatalf("list source documents failed: %v", err)
	}
	if resp.Total != 2 {
		t.Fatalf("expected total=2, got %d", resp.Total)
	}
	if resp.Summary.NewCount != 1 {
		t.Fatalf("expected new_count=1, got %d", resp.Summary.NewCount)
	}
	if resp.Summary.DeletedCount != 1 {
		t.Fatalf("expected deleted_count=1, got %d", resp.Summary.DeletedCount)
	}

	filtered, err := st.ListSourceDocuments(ctx, src.ID, model.ListSourceDocumentsRequest{
		TenantID:   src.TenantID,
		UpdateType: "NEW",
		Page:       1,
		PageSize:   20,
	})
	if err != nil {
		t.Fatalf("list source documents with update_type filter failed: %v", err)
	}
	if filtered.Total != 1 {
		t.Fatalf("expected filtered total=1, got %d", filtered.Total)
	}
	if len(filtered.Items) != 1 || filtered.Items[0].Path != newPath {
		t.Fatalf("expected only new file %s, got %+v", newPath, filtered.Items)
	}
}

func TestListSourceDocumentsShowsProcessingDuringResync(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	path := "/tmp/watch/resync-after-failed.txt"
	firstAt := time.Now().UTC().Add(-3 * time.Minute)

	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: firstAt},
	})
	if err != nil {
		t.Fatalf("build first mutation failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply first mutation failed: %v", err)
	}
	if _, err := st.ScheduleDueParses(ctx, firstAt.Add(12*time.Second)); err != nil {
		t.Fatalf("schedule first parse failed: %v", err)
	}
	doc := loadDocumentByPath(t, st, src, path)
	tasks := loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected first task, got %d", len(tasks))
	}
	if err := st.MarkTaskFailed(ctx, tasks[0].ID, "mock old failure"); err != nil {
		t.Fatalf("mark old task failed failed: %v", err)
	}
	if err := st.db.WithContext(ctx).Model(&documentEntity{}).
		Where("id = ?", doc.ID).
		Update("parse_status", "FAILED").Error; err != nil {
		t.Fatalf("mark document failed failed: %v", err)
	}

	secondAt := firstAt.Add(2 * time.Minute)
	mutations, err = st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: secondAt},
	})
	if err != nil {
		t.Fatalf("build second mutation failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply second mutation failed: %v", err)
	}
	resp, err := st.ListSourceDocuments(ctx, src.ID, model.ListSourceDocumentsRequest{
		TenantID: src.TenantID,
		Page:     1,
		PageSize: 20,
	})
	if err != nil {
		t.Fatalf("list source documents after second mutation failed: %v", err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("expected 1 source document, got %d", len(resp.Items))
	}
	if resp.Items[0].ParseState != "PENDING" {
		t.Fatalf("expected pending parse state while resync is queued, got %s", resp.Items[0].ParseState)
	}

	if _, err := st.ScheduleDueParses(ctx, secondAt.Add(12*time.Second)); err != nil {
		t.Fatalf("schedule second parse failed: %v", err)
	}
	resp, err = st.ListSourceDocuments(ctx, src.ID, model.ListSourceDocumentsRequest{
		TenantID: src.TenantID,
		Page:     1,
		PageSize: 20,
	})
	if err != nil {
		t.Fatalf("list source documents after second schedule failed: %v", err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("expected 1 source document after second schedule, got %d", len(resp.Items))
	}
	if resp.Items[0].ParseState != "PENDING" {
		t.Fatalf("expected latest pending task to override old failure, got %s", resp.Items[0].ParseState)
	}
}

func TestGenerateTasksForSourceUpdatedOnly(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	baseAt := time.Now().UTC().Add(-2 * time.Minute)

	unchangedPath := "/tmp/watch/unchanged.txt"
	newPath := "/tmp/watch/new-for-updated-only.txt"

	// Build one unchanged document by creating and marking the parse task as succeeded.
	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: unchangedPath, OccurredAt: baseAt},
	})
	if err != nil {
		t.Fatalf("build mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply mutations failed: %v", err)
	}
	if _, err := st.ScheduleDueParses(ctx, baseAt.Add(12*time.Second)); err != nil {
		t.Fatalf("schedule due parses failed: %v", err)
	}
	doc := loadDocumentByPath(t, st, src, unchangedPath)
	tasks := loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected 1 task, got %d", len(tasks))
	}
	if err := st.MarkTaskSucceeded(ctx, tasks[0].ID, doc.ID, tasks[0].TargetVersionID); err != nil {
		t.Fatalf("mark task succeeded failed: %v", err)
	}

	treeItems := []model.TreeNode{
		{Title: "unchanged.txt", Key: unchangedPath, IsDir: false},
		{Title: "new-for-updated-only.txt", Key: newPath, IsDir: false},
	}
	_, token, err := st.BuildTreeUpdateState(ctx, src.ID, treeItems, nil)
	if err != nil {
		t.Fatalf("build tree update state failed: %v", err)
	}
	if token == "" {
		t.Fatalf("expected non-empty selection token")
	}

	resp, err := st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:           "partial",
		Paths:          []string{unchangedPath, newPath},
		UpdatedOnly:    true,
		SelectionToken: token,
	})
	if err != nil {
		t.Fatalf("generate tasks with updated_only failed: %v", err)
	}
	if resp.IgnoredUnchangedCount != 1 {
		t.Fatalf("expected ignored_unchanged_count=1, got %d", resp.IgnoredUnchangedCount)
	}
	if resp.AcceptedCount != 1 {
		t.Fatalf("expected accepted_count=1, got %d", resp.AcceptedCount)
	}
}

func boolPtr(v bool) *bool {
	return &v
}

func TestCloudBindingUsesStoreDefaultScheduleTZ(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	st.SetDefaultCloudScheduleTZ("UTC")
	src := createTestSource(t, st)
	ctx := context.Background()

	binding, err := st.UpsertCloudSourceBinding(ctx, src.ID, model.UpsertCloudSourceBindingRequest{
		Provider:         "feishu",
		Enabled:          boolPtr(true),
		AuthConnectionID: "conn_tz_default_001",
		ScheduleExpr:     "daily@05:00",
	})
	if err != nil {
		t.Fatalf("upsert cloud binding failed: %v", err)
	}
	if binding.ScheduleTZ != "UTC" {
		t.Fatalf("expected schedule_tz to fallback to store default UTC, got %s", binding.ScheduleTZ)
	}
}

func TestCloudBindingUpsertAndTriggerSyncRun(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()

	binding, err := st.UpsertCloudSourceBinding(ctx, src.ID, model.UpsertCloudSourceBindingRequest{
		Provider:              "feishu",
		Enabled:               boolPtr(true),
		AuthConnectionID:      "conn_feishu_001",
		TargetType:            "wiki_space",
		TargetRef:             "wikcn_test",
		ScheduleExpr:          "daily@05:00",
		ScheduleTZ:            "Asia/Shanghai",
		ReconcileAfterSync:    boolPtr(true),
		ReconcileDelayMinutes: 10,
		IncludePatterns:       []string{"*.md", "*.docx"},
		ExcludePatterns:       []string{"*.tmp"},
		MaxObjectSizeBytes:    1024 * 1024,
		ProviderOptions: map[string]any{
			"space_name": "test-space",
		},
	})
	if err != nil {
		t.Fatalf("upsert cloud binding failed: %v", err)
	}
	if binding.Provider != "feishu" {
		t.Fatalf("expected provider=feishu, got %s", binding.Provider)
	}
	if binding.AuthConnectionID != "conn_feishu_001" {
		t.Fatalf("expected auth_connection_id=conn_feishu_001, got %s", binding.AuthConnectionID)
	}
	if binding.NextSyncAt == nil {
		t.Fatalf("expected next_sync_at to be set")
	}

	run, err := st.TriggerCloudSync(ctx, src.ID, model.TriggerCloudSyncRequest{TriggerType: "manual"})
	if err != nil {
		t.Fatalf("trigger cloud sync failed: %v", err)
	}
	if strings.TrimSpace(run.RunID) == "" {
		t.Fatalf("expected non-empty run_id")
	}
	if run.Status != "RUNNING" {
		t.Fatalf("expected run status RUNNING, got %s", run.Status)
	}

	runs, err := st.ListCloudSyncRuns(ctx, src.ID, 20)
	if err != nil {
		t.Fatalf("list cloud sync runs failed: %v", err)
	}
	if len(runs) != 1 {
		t.Fatalf("expected 1 cloud sync run, got %d", len(runs))
	}
	if runs[0].RunID != run.RunID {
		t.Fatalf("expected run_id=%s, got %s", run.RunID, runs[0].RunID)
	}
}

func TestTriggerCloudSyncWithManualPaths(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()

	_, err := st.UpsertCloudSourceBinding(ctx, src.ID, model.UpsertCloudSourceBindingRequest{
		Provider:         "feishu",
		Enabled:          boolPtr(true),
		AuthConnectionID: "conn_feishu_manual_paths_001",
		ScheduleExpr:     "daily@05:00",
		ScheduleTZ:       "Asia/Shanghai",
	})
	if err != nil {
		t.Fatalf("upsert cloud binding failed: %v", err)
	}

	run, err := st.TriggerCloudSync(ctx, src.ID, model.TriggerCloudSyncRequest{
		TriggerType: "manual",
		Paths: []string{
			filepath.Join(src.RootPath, "mirror", "docs", "a.md"),
			filepath.Join(src.RootPath, "mirror", "docs", "a.md"), // duplicate
		},
	})
	if err != nil {
		t.Fatalf("trigger cloud sync with manual paths failed: %v", err)
	}
	if len(run.RequestedPaths) != 1 {
		t.Fatalf("expected 1 normalized requested path, got %d (%v)", len(run.RequestedPaths), run.RequestedPaths)
	}
	if want := filepath.Join(src.RootPath, "mirror", "docs", "a.md"); run.RequestedPaths[0] != want {
		t.Fatalf("expected requested path %s, got %s", want, run.RequestedPaths[0])
	}

	_, err = st.TriggerCloudSync(ctx, src.ID, model.TriggerCloudSyncRequest{
		TriggerType: "scheduled",
		Paths:       []string{filepath.Join(src.RootPath, "mirror", "docs", "b.md")},
	})
	if err == nil || !strings.Contains(strings.ToLower(err.Error()), "only supported when trigger_type is manual") {
		t.Fatalf("expected scheduled+paths to fail, got %v", err)
	}

	_, err = st.TriggerCloudSync(ctx, src.ID, model.TriggerCloudSyncRequest{
		TriggerType: "manual",
		Paths:       []string{"/tmp/not-under-mirror/docs/c.md"},
	})
	if err == nil || !strings.Contains(strings.ToLower(err.Error()), "paths must be inside cloud mirror root") {
		t.Fatalf("expected invalid manual paths to fail, got %v", err)
	}
}

func TestTriggerCloudSyncDoesNotAdvanceLastSyncAt(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()

	_, err := st.UpsertCloudSourceBinding(ctx, src.ID, model.UpsertCloudSourceBindingRequest{
		Provider:         "feishu",
		Enabled:          boolPtr(true),
		AuthConnectionID: "conn_lastsync_001",
		ScheduleExpr:     "daily@01:00",
		ScheduleTZ:       "Asia/Shanghai",
	})
	if err != nil {
		t.Fatalf("upsert cloud binding failed: %v", err)
	}

	run, err := st.TriggerCloudSync(ctx, src.ID, model.TriggerCloudSyncRequest{TriggerType: "manual"})
	if err != nil {
		t.Fatalf("trigger cloud sync failed: %v", err)
	}

	var checkpoint cloudSyncCheckpointEntity
	if err := st.db.WithContext(ctx).Take(&checkpoint, "source_id = ?", src.ID).Error; err != nil {
		t.Fatalf("load checkpoint failed: %v", err)
	}
	if checkpoint.LastSyncAt != nil {
		t.Fatalf("expected last_sync_at to stay nil before run finishes, got %v", checkpoint.LastSyncAt)
	}
	if strings.TrimSpace(checkpoint.LastRunID) != run.RunID {
		t.Fatalf("expected last_run_id=%s, got %s", run.RunID, checkpoint.LastRunID)
	}
}

func TestTriggerCloudSyncRejectsDisabledBinding(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()

	_, err := st.UpsertCloudSourceBinding(ctx, src.ID, model.UpsertCloudSourceBindingRequest{
		Provider:         "feishu",
		Enabled:          boolPtr(false),
		AuthConnectionID: "conn_disabled_001",
		ScheduleExpr:     "daily@01:00",
		ScheduleTZ:       "Asia/Shanghai",
	})
	if err != nil {
		t.Fatalf("upsert cloud binding failed: %v", err)
	}

	_, err = st.TriggerCloudSync(ctx, src.ID, model.TriggerCloudSyncRequest{TriggerType: "manual"})
	if err == nil {
		t.Fatalf("expected trigger cloud sync to fail for disabled binding")
	}
	if !strings.Contains(strings.ToLower(err.Error()), "disabled") {
		t.Fatalf("expected disabled error, got %v", err)
	}

	var runCount int64
	if err := st.db.WithContext(ctx).Model(&cloudSyncRunEntity{}).
		Where("source_id = ?", src.ID).
		Count(&runCount).Error; err != nil {
		t.Fatalf("count cloud sync runs failed: %v", err)
	}
	if runCount != 0 {
		t.Fatalf("expected no cloud sync run rows, got %d", runCount)
	}
}

func TestBuildCloudTreeByPath(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:              "tenant-cloud",
		Name:                  "src-cloud",
		RootPath:              "/tmp/cloud-mirror/src-cloud",
		AgentID:               "agent-1",
		WatchEnabled:          true,
		IdleWindowSeconds:     10,
		DefaultOriginType:     "CLOUD_SYNC",
		DefaultOriginPlatform: "FEISHU",
	})
	if err != nil {
		t.Fatalf("create cloud source failed: %v", err)
	}

	now := time.Now().UTC()
	rows := []cloudObjectIndexEntity{
		{
			SourceID:         src.ID,
			Provider:         "feishu",
			ExternalObjectID: "fld_docs",
			ExternalName:     "docs",
			ExternalKind:     "folder",
			LocalRelPath:     "docs",
			LocalAbsPath:     "/tmp/cloud-mirror/src-cloud/mirror/docs",
			CreatedAt:        now,
			UpdatedAt:        now,
		},
		{
			SourceID:         src.ID,
			Provider:         "feishu",
			ExternalObjectID: "doc_a",
			ExternalName:     "a.md",
			ExternalKind:     "file",
			LocalRelPath:     "docs/a.md",
			LocalAbsPath:     "/tmp/cloud-mirror/src-cloud/mirror/docs/a.md",
			CreatedAt:        now,
			UpdatedAt:        now,
		},
		{
			SourceID:         src.ID,
			Provider:         "feishu",
			ExternalObjectID: "fld_sub",
			ExternalName:     "sub",
			ExternalKind:     "folder",
			LocalRelPath:     "docs/sub",
			LocalAbsPath:     "/tmp/cloud-mirror/src-cloud/mirror/docs/sub",
			CreatedAt:        now,
			UpdatedAt:        now,
		},
		{
			SourceID:         src.ID,
			Provider:         "feishu",
			ExternalObjectID: "doc_b",
			ExternalName:     "b.md",
			ExternalKind:     "file",
			LocalRelPath:     "docs/sub/b.md",
			LocalAbsPath:     "/tmp/cloud-mirror/src-cloud/mirror/docs/sub/b.md",
			CreatedAt:        now,
			UpdatedAt:        now,
		},
		{
			SourceID:         src.ID,
			Provider:         "feishu",
			ExternalObjectID: "doc_readme",
			ExternalName:     "readme.md",
			ExternalKind:     "file",
			LocalRelPath:     "readme.md",
			LocalAbsPath:     "/tmp/cloud-mirror/src-cloud/mirror/readme.md",
			CreatedAt:        now,
			UpdatedAt:        now,
		},
	}
	if err := st.db.WithContext(ctx).Create(&rows).Error; err != nil {
		t.Fatalf("seed cloud_object_index failed: %v", err)
	}

	items, err := st.BuildCloudTreeByPath(ctx, src.ID, "/tmp/cloud-mirror/src-cloud/mirror/docs", 2, true)
	if err != nil {
		t.Fatalf("build cloud tree failed: %v", err)
	}
	nodeA, ok := findTreeNodeByPath(items, "/tmp/cloud-mirror/src-cloud/mirror/docs/a.md")
	if !ok {
		t.Fatalf("expected node a.md")
	}
	if nodeA.IsDir {
		t.Fatalf("expected a.md to be file node")
	}
	if nodeA.ExternalFileID != "doc_a" {
		t.Fatalf("expected external_file_id=doc_a, got %s", nodeA.ExternalFileID)
	}
	nodeSub, ok := findTreeNodeByPath(items, "/tmp/cloud-mirror/src-cloud/mirror/docs/sub")
	if !ok || !nodeSub.IsDir {
		t.Fatalf("expected docs/sub directory node")
	}
	if _, ok := findTreeNodeByPath(items, "/tmp/cloud-mirror/src-cloud/mirror/readme.md"); ok {
		t.Fatalf("unexpected readme.md in docs subtree")
	}

	itemsNoFiles, err := st.BuildCloudTreeByPath(ctx, src.ID, "/tmp/cloud-mirror/src-cloud/mirror/docs", 1, false)
	if err != nil {
		t.Fatalf("build cloud tree without files failed: %v", err)
	}
	if _, ok := findTreeNodeByPath(itemsNoFiles, "/tmp/cloud-mirror/src-cloud/mirror/docs/a.md"); ok {
		t.Fatalf("did not expect file node when include_files=false")
	}
	if _, ok := findTreeNodeByPath(itemsNoFiles, "/tmp/cloud-mirror/src-cloud/mirror/docs/sub/b.md"); ok {
		t.Fatalf("did not expect depth>1 node when max_depth=1")
	}

	_, err = st.BuildCloudTreeByPath(ctx, src.ID, "/tmp/cloud-mirror/src-cloud/mirror/not-found", 2, true)
	if !errors.Is(err, ErrTreePathInvalid) {
		t.Fatalf("expected ErrTreePathInvalid, got %v", err)
	}
}

func TestCloudSyncClaimAndFinishLifecycle(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()

	_, err := st.UpsertCloudSourceBinding(ctx, src.ID, model.UpsertCloudSourceBindingRequest{
		Provider:         "feishu",
		Enabled:          boolPtr(true),
		AuthConnectionID: "conn_001",
		ScheduleExpr:     "daily@02:00",
		ScheduleTZ:       "Asia/Shanghai",
	})
	if err != nil {
		t.Fatalf("upsert cloud binding failed: %v", err)
	}
	run, err := st.TriggerCloudSync(ctx, src.ID, model.TriggerCloudSyncRequest{TriggerType: "manual"})
	if err != nil {
		t.Fatalf("trigger cloud sync failed: %v", err)
	}

	now := time.Now().UTC().Add(2 * time.Second)
	claims, err := st.ClaimDueCloudSources(ctx, "ut-lock-owner", now, 10, 2*time.Minute)
	if err != nil {
		t.Fatalf("claim due cloud sources failed: %v", err)
	}
	if len(claims) != 1 {
		t.Fatalf("expected 1 due claim, got %d", len(claims))
	}
	claim := claims[0]
	if claim.SourceID != src.ID {
		t.Fatalf("expected source_id=%s, got %s", src.ID, claim.SourceID)
	}
	if claim.ExistingRunID != run.RunID {
		t.Fatalf("expected existing_run_id=%s, got %s", run.RunID, claim.ExistingRunID)
	}

	startedRun, err := st.StartCloudSyncRun(ctx, src.ID, "manual", claim.ExistingRunID, now)
	if err != nil {
		t.Fatalf("start cloud sync run failed: %v", err)
	}
	if startedRun.RunID != run.RunID {
		t.Fatalf("expected reused run_id=%s, got %s", run.RunID, startedRun.RunID)
	}

	if err := st.FinishCloudSyncRun(ctx, src.ID, CloudSyncRunFinalize{
		RunID:        run.RunID,
		Status:       "SUCCEEDED",
		FinishedAt:   now.Add(5 * time.Second),
		RemoteTotal:  5,
		CreatedCount: 2,
		UpdatedCount: 1,
		DeletedCount: 1,
		SkippedCount: 1,
		FailedCount:  0,
	}); err != nil {
		t.Fatalf("finish cloud sync run failed: %v", err)
	}

	runs, err := st.ListCloudSyncRuns(ctx, src.ID, 10)
	if err != nil {
		t.Fatalf("list cloud sync runs failed: %v", err)
	}
	if len(runs) != 1 {
		t.Fatalf("expected 1 run, got %d", len(runs))
	}
	if runs[0].Status != "SUCCEEDED" {
		t.Fatalf("expected run status SUCCEEDED, got %s", runs[0].Status)
	}
	if runs[0].FinishedAt == nil || runs[0].FinishedAt.IsZero() {
		t.Fatalf("expected finished_at to be set")
	}

	var checkpoint cloudSyncCheckpointEntity
	if err := st.db.WithContext(ctx).Take(&checkpoint, "source_id = ?", src.ID).Error; err != nil {
		t.Fatalf("load checkpoint failed: %v", err)
	}
	if strings.TrimSpace(checkpoint.LockOwner) != "" || checkpoint.LockUntil != nil {
		t.Fatalf("expected checkpoint lock released, got owner=%q lock_until=%v", checkpoint.LockOwner, checkpoint.LockUntil)
	}
	if checkpoint.LastSuccessAt == nil || checkpoint.LastSuccessAt.IsZero() {
		t.Fatalf("expected checkpoint.last_success_at to be set")
	}
}

func TestCloudSyncClaimDueDoesNotReuseFinishedRun(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()

	_, err := st.UpsertCloudSourceBinding(ctx, src.ID, model.UpsertCloudSourceBindingRequest{
		Provider:         "feishu",
		Enabled:          boolPtr(true),
		AuthConnectionID: "conn_002",
		ScheduleExpr:     "daily@02:00",
		ScheduleTZ:       "Asia/Shanghai",
	})
	if err != nil {
		t.Fatalf("upsert cloud binding failed: %v", err)
	}

	firstRun, err := st.TriggerCloudSync(ctx, src.ID, model.TriggerCloudSyncRequest{TriggerType: "manual"})
	if err != nil {
		t.Fatalf("trigger cloud sync failed: %v", err)
	}
	finishedAt := time.Now().UTC().Add(2 * time.Second)
	if err := st.FinishCloudSyncRun(ctx, src.ID, CloudSyncRunFinalize{
		RunID:      firstRun.RunID,
		Status:     "SUCCEEDED",
		FinishedAt: finishedAt,
	}); err != nil {
		t.Fatalf("finish first cloud sync run failed: %v", err)
	}

	dueAt := finishedAt.Add(2 * time.Second)
	if err := st.db.WithContext(ctx).Model(&cloudSyncCheckpointEntity{}).
		Where("source_id = ?", src.ID).
		Updates(map[string]any{
			"next_sync_at": &dueAt,
			"lock_owner":   "",
			"lock_until":   nil,
			"updated_at":   dueAt,
		}).Error; err != nil {
		t.Fatalf("force next_sync_at failed: %v", err)
	}

	claims, err := st.ClaimDueCloudSources(ctx, "ut-lock-owner-2", dueAt.Add(time.Second), 10, 2*time.Minute)
	if err != nil {
		t.Fatalf("claim due cloud sources failed: %v", err)
	}
	if len(claims) != 1 {
		t.Fatalf("expected 1 due claim, got %d", len(claims))
	}
	if claims[0].ExistingRunID != "" {
		t.Fatalf("expected empty existing_run_id for finished run, got %s", claims[0].ExistingRunID)
	}

	secondRun, err := st.StartCloudSyncRun(ctx, src.ID, "scheduled", claims[0].ExistingRunID, dueAt.Add(time.Second))
	if err != nil {
		t.Fatalf("start scheduled cloud sync run failed: %v", err)
	}
	if secondRun.RunID == firstRun.RunID {
		t.Fatalf("expected new run_id for scheduled run, got reused %s", secondRun.RunID)
	}
}

func TestCloudObjectIndexUpsertAndMarkDelete(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	now := time.Now().UTC()

	err := st.UpsertCloudObjectIndexBatch(ctx, src.ID, "feishu", []CloudObjectIndexRecord{
		{
			ExternalObjectID: "obj_a",
			ExternalPath:     "docs/a.md",
			ExternalName:     "a.md",
			ExternalKind:     "file",
			ExternalVersion:  "v1",
			LocalRelPath:     "docs/a.md",
			LocalAbsPath:     filepath.Join(src.RootPath, "docs/a.md"),
			Checksum:         "sha-a",
			SizeBytes:        11,
		},
		{
			ExternalObjectID: "obj_b",
			ExternalPath:     "docs/b.md",
			ExternalName:     "b.md",
			ExternalKind:     "file",
			ExternalVersion:  "v1",
			LocalRelPath:     "docs/b.md",
			LocalAbsPath:     filepath.Join(src.RootPath, "docs/b.md"),
			Checksum:         "sha-b",
			SizeBytes:        22,
		},
	}, now)
	if err != nil {
		t.Fatalf("upsert cloud object index failed: %v", err)
	}

	items, err := st.ListCloudObjectIndex(ctx, src.ID)
	if err != nil {
		t.Fatalf("list cloud object index failed: %v", err)
	}
	if len(items) != 2 {
		t.Fatalf("expected 2 index records, got %d", len(items))
	}

	if err := st.MarkCloudObjectsDeleted(ctx, src.ID, []string{"obj_b"}, now.Add(2*time.Second)); err != nil {
		t.Fatalf("mark cloud object deleted failed: %v", err)
	}
	items, err = st.ListCloudObjectIndex(ctx, src.ID)
	if err != nil {
		t.Fatalf("list cloud object index failed: %v", err)
	}
	deleted := 0
	for _, item := range items {
		if item.IsDeleted {
			deleted++
		}
	}
	if deleted != 1 {
		t.Fatalf("expected 1 deleted record, got %d", deleted)
	}
}

func TestBuildTreeUpdateState(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	baseAt := time.Now().UTC().Add(-3 * time.Minute)

	newPath := "/tmp/watch/tree-new.txt"
	unchangedPath := "/tmp/watch/tree-unchanged.txt"

	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: newPath, OccurredAt: baseAt.Add(1 * time.Second)},
		{SourceID: src.ID, EventType: "modified", Path: unchangedPath, OccurredAt: baseAt.Add(2 * time.Second)},
	})
	if err != nil {
		t.Fatalf("build mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply mutations failed: %v", err)
	}
	if _, err := st.ScheduleDueParses(ctx, baseAt.Add(20*time.Second)); err != nil {
		t.Fatalf("schedule due parses failed: %v", err)
	}

	unchangedDoc := loadDocumentByPath(t, st, src, unchangedPath)
	unchangedTasks := loadTasksByDocumentID(t, st, unchangedDoc.ID)
	if len(unchangedTasks) != 1 {
		t.Fatalf("expected unchanged path to have one task, got %d", len(unchangedTasks))
	}
	if err := st.MarkTaskSucceeded(ctx, unchangedTasks[0].ID, unchangedDoc.ID, unchangedTasks[0].TargetVersionID); err != nil {
		t.Fatalf("mark unchanged task succeeded failed: %v", err)
	}

	treeItems := []model.TreeNode{
		{Title: "tree-new.txt", Key: newPath, IsDir: false},
		{Title: "tree-unchanged.txt", Key: unchangedPath, IsDir: false},
	}
	items, token, err := st.BuildTreeUpdateState(ctx, src.ID, treeItems, nil)
	if err != nil {
		t.Fatalf("build tree update state failed: %v", err)
	}
	if token == "" {
		t.Fatalf("expected non-empty selection token")
	}
	if len(items) != 2 {
		t.Fatalf("expected 2 tree items, got %d", len(items))
	}

	var newItem, unchangedItem *model.TreeNode
	for i := range items {
		if items[i].Key == newPath {
			newItem = &items[i]
		}
		if items[i].Key == unchangedPath {
			unchangedItem = &items[i]
		}
	}
	if newItem == nil || unchangedItem == nil {
		t.Fatalf("missing expected tree items after enrichment: %+v", items)
	}
	if newItem.UpdateType != "NEW" {
		t.Fatalf("expected new item update_type NEW, got %s", newItem.UpdateType)
	}
	if newItem.HasUpdate == nil || !*newItem.HasUpdate {
		t.Fatalf("expected new item has_update=true, got %+v", newItem.HasUpdate)
	}
	if newItem.StatusSource != "DOCUMENTS" {
		t.Fatalf("expected new item status_source DOCUMENTS, got %s", newItem.StatusSource)
	}

	if unchangedItem.UpdateType != "UNCHANGED" {
		t.Fatalf("expected unchanged item update_type UNCHANGED, got %s", unchangedItem.UpdateType)
	}
	if unchangedItem.HasUpdate == nil || *unchangedItem.HasUpdate {
		t.Fatalf("expected unchanged item has_update=false, got %+v", unchangedItem.HasUpdate)
	}
	if unchangedItem.StatusSource != "DOCUMENTS" {
		t.Fatalf("expected unchanged item status_source DOCUMENTS, got %s", unchangedItem.StatusSource)
	}
}

func TestBuildTreeUpdateStateIgnoresStaleParseQueueTask(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	src := createTestSource(t, st)
	ctx := context.Background()
	baseAt := time.Now().UTC().Add(-3 * time.Minute)

	path := "/tmp/watch/tree-stale-task.txt"
	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{SourceID: src.ID, EventType: "modified", Path: path, OccurredAt: baseAt},
	})
	if err != nil {
		t.Fatalf("build mutation failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply mutation failed: %v", err)
	}
	if _, err := st.ScheduleDueParses(ctx, baseAt.Add(20*time.Second)); err != nil {
		t.Fatalf("schedule parse failed: %v", err)
	}
	doc := loadDocumentByPath(t, st, src, path)
	tasks := loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected one parse task, got %d", len(tasks))
	}
	if err := st.db.WithContext(ctx).Model(&documentEntity{}).
		Where("id = ?", doc.ID).
		Updates(map[string]any{
			"desired_version_id": tasks[0].TargetVersionID + "_new",
			"current_version_id": tasks[0].TargetVersionID,
			"parse_status":       "PENDING",
		}).Error; err != nil {
		t.Fatalf("seed newer desired version failed: %v", err)
	}

	treeItems := []model.TreeNode{{Title: "tree-stale-task.txt", Key: path, IsDir: false}}
	items, _, err := st.BuildTreeUpdateState(ctx, src.ID, treeItems, nil)
	if err != nil {
		t.Fatalf("build tree update state failed: %v", err)
	}
	node, ok := findTreeNodeByPath(items, path)
	if !ok {
		t.Fatalf("missing node for path %s", path)
	}
	if node.ParseQueueState != "" {
		t.Fatalf("expected stale task not to set parse_queue_state, got %s", node.ParseQueueState)
	}
	if node.UpdateType != "MODIFIED" {
		t.Fatalf("expected document update_type MODIFIED, got %s", node.UpdateType)
	}
}

func TestNonWatchSnapshotDiffAndSelectionToken(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:          "tenant-1",
		Name:              "src-non-watch",
		RootPath:          "/tmp/watch",
		AgentID:           "agent-1",
		WatchEnabled:      false,
		IdleWindowSeconds: 10,
	})
	if err != nil {
		t.Fatalf("create non-watch source failed: %v", err)
	}

	pathA := "/tmp/watch/a.txt"
	pathB := "/tmp/watch/b.txt"
	pathC := "/tmp/watch/c.txt"
	modA1 := time.Now().UTC().Add(-2 * time.Minute)
	modB1 := modA1

	items := []model.TreeNode{
		{Title: "a.txt", Key: pathA, IsDir: false},
		{Title: "b.txt", Key: pathB, IsDir: false},
	}
	stats1 := map[string]model.TreeFileStat{
		pathA: {Path: pathA, Size: 10, ModTime: &modA1},
		pathB: {Path: pathB, Size: 20, ModTime: &modB1},
	}
	tree1, token1, err := st.BuildTreeUpdateState(ctx, src.ID, items, stats1)
	if err != nil {
		t.Fatalf("build first snapshot tree state failed: %v", err)
	}
	if token1 == "" {
		t.Fatalf("expected first selection token")
	}
	for _, item := range tree1 {
		if item.UpdateType != "NEW" {
			t.Fatalf("expected first preview update_type NEW, got %s for %s", item.UpdateType, item.Key)
		}
		if item.StatusSource != "SNAPSHOT" {
			t.Fatalf("expected first preview status_source SNAPSHOT, got %s", item.StatusSource)
		}
	}

	resp, err := st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:           "partial",
		Paths:          []string{pathA, pathB},
		SelectionToken: token1,
	})
	if err != nil {
		t.Fatalf("generate tasks with first selection token failed: %v", err)
	}
	if resp.AcceptedCount != 2 {
		t.Fatalf("expected accepted_count=2, got %d", resp.AcceptedCount)
	}

	var relation sourceSnapshotRelationEntity
	if err := st.db.WithContext(ctx).Take(&relation, "source_id = ?", src.ID).Error; err != nil {
		t.Fatalf("load snapshot relation failed: %v", err)
	}
	if relation.LastCommittedSnapshotID == "" {
		t.Fatalf("expected committed snapshot after generate")
	}

	modA2 := modA1.Add(3 * time.Minute)
	modC2 := modA1.Add(1 * time.Minute)
	items2 := []model.TreeNode{
		{Title: "a.txt", Key: pathA, IsDir: false},
		{Title: "c.txt", Key: pathC, IsDir: false},
	}
	stats2 := map[string]model.TreeFileStat{
		pathA: {Path: pathA, Size: 11, ModTime: &modA2},
		pathC: {Path: pathC, Size: 30, ModTime: &modC2},
	}
	tree2, token2, err := st.BuildTreeUpdateState(ctx, src.ID, items2, stats2)
	if err != nil {
		t.Fatalf("build second snapshot tree state failed: %v", err)
	}
	if token2 == "" {
		t.Fatalf("expected second selection token")
	}
	nodeA, ok := findTreeNodeByPath(tree2, pathA)
	if !ok {
		t.Fatalf("missing node for path %s", pathA)
	}
	if nodeA.UpdateType != "MODIFIED" {
		t.Fatalf("expected %s MODIFIED, got %s", pathA, nodeA.UpdateType)
	}
	nodeB, ok := findTreeNodeByPath(tree2, pathB)
	if !ok {
		t.Fatalf("missing node for path %s", pathB)
	}
	if nodeB.UpdateType != "DELETED" {
		t.Fatalf("expected %s DELETED, got %s", pathB, nodeB.UpdateType)
	}
	nodeC, ok := findTreeNodeByPath(tree2, pathC)
	if !ok {
		t.Fatalf("missing node for path %s", pathC)
	}
	if nodeC.UpdateType != "NEW" {
		t.Fatalf("expected %s NEW, got %s", pathC, nodeC.UpdateType)
	}

	_, err = st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:           "partial",
		Paths:          []string{"/tmp/watch/not-in-preview.txt"},
		SelectionToken: token2,
	})
	if err == nil {
		t.Fatalf("expected error when path is not in selected snapshot")
	}

	resp, err = st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:           "partial",
		Paths:          []string{pathA, pathB, pathC},
		UpdatedOnly:    true,
		SelectionToken: token2,
	})
	if err != nil {
		t.Fatalf("generate tasks with updated_only + selection token failed: %v", err)
	}
	if resp.IgnoredUnchangedCount != 0 {
		t.Fatalf("expected ignored_unchanged_count=0, got %d", resp.IgnoredUnchangedCount)
	}
	if resp.AcceptedCount != 3 {
		t.Fatalf("expected accepted_count=3, got %d", resp.AcceptedCount)
	}
	docB := loadDocumentByPath(t, st, src, pathB)
	if docB.ParseStatus != "DELETED" {
		t.Fatalf("expected deleted path parse_status=DELETED, got %s", docB.ParseStatus)
	}
}

func TestSnapshotSourceAckDoesNotReplaceCommittedSnapshotItems(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:          "tenant-1",
		Name:              "src-ack-baseline",
		RootPath:          "/tmp/watch",
		AgentID:           "agent-1",
		WatchEnabled:      false,
		IdleWindowSeconds: 10,
	})
	if err != nil {
		t.Fatalf("create non-watch source failed: %v", err)
	}

	path := "/tmp/watch/a.txt"
	modAt := time.Now().UTC().Add(-2 * time.Minute)
	items := []model.TreeNode{{Title: "a.txt", Key: path, IsDir: false}}
	stats := map[string]model.TreeFileStat{
		path: {Path: path, Size: 10, ModTime: &modAt},
	}
	_, token, err := st.BuildTreeUpdateState(ctx, src.ID, items, stats)
	if err != nil {
		t.Fatalf("build initial tree state failed: %v", err)
	}
	if _, err := st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:           "partial",
		Paths:          []string{path},
		SelectionToken: token,
	}); err != nil {
		t.Fatalf("generate tasks with selection token failed: %v", err)
	}

	var before sourceSnapshotRelationEntity
	if err := st.db.WithContext(ctx).Take(&before, "source_id = ?", src.ID).Error; err != nil {
		t.Fatalf("load relation before ack failed: %v", err)
	}
	if before.LastCommittedSnapshotID == "" {
		t.Fatalf("expected committed snapshot before ack")
	}

	pulled, err := st.PullPendingCommands(ctx, model.PullCommandsRequest{
		AgentID:  "agent-1",
		TenantID: "tenant-1",
	})
	if err != nil {
		t.Fatalf("pull commands failed: %v", err)
	}
	if len(pulled.Commands) != 1 || pulled.Commands[0].Type != model.CommandSnapshotSource {
		t.Fatalf("expected one snapshot_source command, got %+v", pulled.Commands)
	}
	resultJSON := `{"snapshot_ref":"local://snapshot/src-ack-baseline/snapshot.json","file_count":1,"taken_at":"` + time.Now().UTC().Format(time.RFC3339Nano) + `"}`
	if err := st.AckCommand(ctx, model.AckCommandRequest{
		AgentID:    "agent-1",
		CommandID:  pulled.Commands[0].ID,
		Success:    true,
		ResultJSON: resultJSON,
	}); err != nil {
		t.Fatalf("ack snapshot_source failed: %v", err)
	}

	var after sourceSnapshotRelationEntity
	if err := st.db.WithContext(ctx).Take(&after, "source_id = ?", src.ID).Error; err != nil {
		t.Fatalf("load relation after ack failed: %v", err)
	}
	if after.LastCommittedSnapshotID != before.LastCommittedSnapshotID {
		t.Fatalf("snapshot_source ack replaced committed snapshot: before=%s after=%s", before.LastCommittedSnapshotID, after.LastCommittedSnapshotID)
	}

	tree, _, err := st.BuildTreeUpdateState(ctx, src.ID, items, stats)
	if err != nil {
		t.Fatalf("build tree state after ack failed: %v", err)
	}
	node, ok := findTreeNodeByPath(tree, path)
	if !ok {
		t.Fatalf("missing node for path %s", path)
	}
	if node.UpdateType != "UNCHANGED" {
		t.Fatalf("expected unchanged after snapshot_source ack, got %s", node.UpdateType)
	}
}

func TestSourceFileSnapshotSelectionTokenIndexAllowsCommittedSnapshotsWithoutTokens(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	if err := st.db.WithContext(ctx).Exec("DROP INDEX IF EXISTS idx_source_file_snapshots_selection_token").Error; err != nil {
		t.Fatalf("drop selection token index failed: %v", err)
	}
	if err := st.db.WithContext(ctx).Exec("CREATE UNIQUE INDEX idx_source_file_snapshots_selection_token ON source_file_snapshots (selection_token)").Error; err != nil {
		t.Fatalf("create legacy selection token index failed: %v", err)
	}
	if err := st.ensureSourceFileSnapshotIndexes(ctx); err != nil {
		t.Fatalf("rebuild legacy selection token index failed: %v", err)
	}

	src := createTestSource(t, st)
	now := time.Now().UTC()

	committed := []sourceFileSnapshotEntity{
		{
			SnapshotID:   "ss_empty_token_1",
			SourceID:     src.ID,
			TenantID:     src.TenantID,
			SnapshotType: "COMMITTED",
			FileCount:    1,
			CreatedAt:    now,
		},
		{
			SnapshotID:   "ss_empty_token_2",
			SourceID:     src.ID,
			TenantID:     src.TenantID,
			SnapshotType: "COMMITTED",
			FileCount:    2,
			CreatedAt:    now.Add(time.Nanosecond),
		},
	}
	for _, snap := range committed {
		if err := st.db.WithContext(ctx).Create(&snap).Error; err != nil {
			t.Fatalf("create committed snapshot with empty selection token failed: %v", err)
		}
	}

	token := "sel_duplicate_token"
	preview := sourceFileSnapshotEntity{
		SnapshotID:     "ss_token_1",
		SourceID:       src.ID,
		TenantID:       src.TenantID,
		SnapshotType:   "PREVIEW",
		SelectionToken: token,
		FileCount:      1,
		CreatedAt:      now.Add(2 * time.Nanosecond),
	}
	if err := st.db.WithContext(ctx).Create(&preview).Error; err != nil {
		t.Fatalf("create preview snapshot with token failed: %v", err)
	}
	preview.SnapshotID = "ss_token_2"
	preview.CreatedAt = now.Add(3 * time.Nanosecond)
	if err := st.db.WithContext(ctx).Create(&preview).Error; err == nil {
		t.Fatalf("expected duplicate non-empty selection token to fail")
	}
}

func TestListSourceDocumentsUsesLatestNonWatchSnapshotState(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:          "tenant-1",
		Name:              "src-non-watch-doc-list",
		RootPath:          "/tmp/watch",
		AgentID:           "agent-1",
		WatchEnabled:      false,
		IdleWindowSeconds: 10,
	})
	if err != nil {
		t.Fatalf("create non-watch source failed: %v", err)
	}

	path := "/tmp/watch/a.txt"
	modAt := time.Now().UTC().Add(-2 * time.Minute)
	items := []model.TreeNode{{Title: "a.txt", Key: path, IsDir: false}}
	stats := map[string]model.TreeFileStat{
		path: {Path: path, Size: 10, ModTime: &modAt},
	}
	_, token, err := st.BuildTreeUpdateState(ctx, src.ID, items, stats)
	if err != nil {
		t.Fatalf("build initial tree state failed: %v", err)
	}
	if _, err := st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:           "partial",
		Paths:          []string{path},
		SelectionToken: token,
	}); err != nil {
		t.Fatalf("generate tasks with selection token failed: %v", err)
	}

	doc := loadDocumentByPath(t, st, src, path)
	if err := st.db.WithContext(ctx).Model(&documentEntity{}).
		Where("id = ?", doc.ID).
		Updates(map[string]any{
			"desired_version_id": "v_stale_desired",
			"current_version_id": "v_current",
			"parse_status":       "SUCCEEDED",
		}).Error; err != nil {
		t.Fatalf("seed stale document versions failed: %v", err)
	}

	_, _, err = st.BuildTreeUpdateState(ctx, src.ID, items, stats)
	if err != nil {
		t.Fatalf("build unchanged preview failed: %v", err)
	}

	resp, err := st.ListSourceDocuments(ctx, src.ID, model.ListSourceDocumentsRequest{
		TenantID: src.TenantID,
		Page:     1,
		PageSize: 20,
	})
	if err != nil {
		t.Fatalf("list source documents failed: %v", err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("expected 1 document, got %d", len(resp.Items))
	}
	if resp.Items[0].UpdateType != "UNCHANGED" {
		t.Fatalf("expected snapshot state to mark document UNCHANGED, got %s", resp.Items[0].UpdateType)
	}
	if resp.Items[0].HasUpdate == nil || *resp.Items[0].HasUpdate {
		t.Fatalf("expected has_update=false from snapshot state, got %+v", resp.Items[0].HasUpdate)
	}
	if resp.Summary.ModifiedCount != 0 || resp.Summary.PendingPullCount != 0 {
		t.Fatalf("expected snapshot state to clear pending counts, got modified=%d pending=%d", resp.Summary.ModifiedCount, resp.Summary.PendingPullCount)
	}
}

func TestListSourceDocumentsIgnoresConsumedNonWatchPreview(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:          "tenant-1",
		Name:              "src-consumed-preview-doc-list",
		RootPath:          "/tmp/watch",
		AgentID:           "agent-1",
		WatchEnabled:      false,
		IdleWindowSeconds: 10,
	})
	if err != nil {
		t.Fatalf("create non-watch source failed: %v", err)
	}

	path := "/tmp/watch/a.txt"
	modAt := time.Now().UTC().Add(-2 * time.Minute)
	items := []model.TreeNode{{Title: "a.txt", Key: path, IsDir: false}}
	stats := map[string]model.TreeFileStat{
		path: {Path: path, Size: 10, ModTime: &modAt},
	}
	_, token, err := st.BuildTreeUpdateState(ctx, src.ID, items, stats)
	if err != nil {
		t.Fatalf("build initial tree state failed: %v", err)
	}
	if _, err := st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:           "partial",
		Paths:          []string{path},
		SelectionToken: token,
	}); err != nil {
		t.Fatalf("generate tasks with selection token failed: %v", err)
	}

	var consumed sourceFileSnapshotEntity
	if err := st.db.WithContext(ctx).
		Where("source_id = ? AND selection_token = ?", src.ID, token).
		Take(&consumed).Error; err != nil {
		t.Fatalf("load consumed snapshot failed: %v", err)
	}
	if consumed.ConsumedAt == nil {
		t.Fatalf("expected preview to be consumed after generate tasks")
	}

	doc := loadDocumentByPath(t, st, src, path)
	if _, err := st.ScheduleDueParses(ctx, time.Now().UTC().Add(20*time.Second)); err != nil {
		t.Fatalf("schedule due parses failed: %v", err)
	}
	tasks := loadTasksByDocumentID(t, st, doc.ID)
	if len(tasks) != 1 {
		t.Fatalf("expected 1 parse task, got %d", len(tasks))
	}
	if err := st.MarkTaskSucceeded(ctx, tasks[0].ID, doc.ID, tasks[0].TargetVersionID); err != nil {
		t.Fatalf("mark task succeeded failed: %v", err)
	}

	resp, err := st.ListSourceDocuments(ctx, src.ID, model.ListSourceDocumentsRequest{
		TenantID: src.TenantID,
		Page:     1,
		PageSize: 20,
	})
	if err != nil {
		t.Fatalf("list source documents failed: %v", err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("expected 1 document, got %d", len(resp.Items))
	}
	if resp.Items[0].UpdateType != "UNCHANGED" {
		t.Fatalf("expected consumed preview to leave document UNCHANGED, got %s", resp.Items[0].UpdateType)
	}
	if resp.Items[0].HasUpdate == nil || *resp.Items[0].HasUpdate {
		t.Fatalf("expected has_update=false after consumed preview, got %+v", resp.Items[0].HasUpdate)
	}
	if resp.Summary.PendingPullCount != 0 {
		t.Fatalf("expected pending_pull_count=0 after consumed preview, got %d", resp.Summary.PendingPullCount)
	}
}

func TestGenerateTasksWithoutSelectionTokenConsumesNonWatchPreview(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:          "tenant-1",
		Name:              "src-no-token-preview",
		RootPath:          "/tmp/watch",
		AgentID:           "agent-1",
		WatchEnabled:      false,
		IdleWindowSeconds: 10,
	})
	if err != nil {
		t.Fatalf("create non-watch source failed: %v", err)
	}

	path := "/tmp/watch/a.txt"
	items := []model.TreeNode{{Title: "a.txt", Key: path, IsDir: false}}
	stats := map[string]model.TreeFileStat{
		path: {Path: path, Size: 10},
	}
	_, token, err := st.BuildTreeUpdateState(ctx, src.ID, items, stats)
	if err != nil {
		t.Fatalf("build initial tree state failed: %v", err)
	}
	resp, err := st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:  "partial",
		Paths: []string{path},
	})
	if err != nil {
		t.Fatalf("generate tasks without selection token failed: %v", err)
	}
	if resp.AcceptedCount != 1 {
		t.Fatalf("expected accepted_count=1, got %d", resp.AcceptedCount)
	}
	var consumed sourceFileSnapshotEntity
	if err := st.db.WithContext(ctx).
		Where("source_id = ? AND selection_token = ?", src.ID, token).
		Take(&consumed).Error; err != nil {
		t.Fatalf("load consumed snapshot failed: %v", err)
	}
	if consumed.ConsumedAt == nil {
		t.Fatalf("expected preview to be consumed after tokenless generate tasks")
	}
}

func TestBuildTreeUpdateStateFallsBackFromEmptyCommittedSnapshot(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:          "tenant-1",
		Name:              "src-empty-committed",
		RootPath:          "/tmp/watch",
		AgentID:           "agent-1",
		WatchEnabled:      false,
		IdleWindowSeconds: 10,
	})
	if err != nil {
		t.Fatalf("create non-watch source failed: %v", err)
	}

	path := "/tmp/watch/a.txt"
	modAt := time.Now().UTC().Add(-2 * time.Minute)
	items := []model.TreeNode{{Title: "a.txt", Key: path, IsDir: false}}
	stats := map[string]model.TreeFileStat{
		path: {Path: path, Size: 10, ModTime: &modAt},
	}
	_, token, err := st.BuildTreeUpdateState(ctx, src.ID, items, stats)
	if err != nil {
		t.Fatalf("build initial tree state failed: %v", err)
	}
	if _, err := st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:           "partial",
		Paths:          []string{path},
		SelectionToken: token,
	}); err != nil {
		t.Fatalf("generate tasks with selection token failed: %v", err)
	}

	var relation sourceSnapshotRelationEntity
	if err := st.db.WithContext(ctx).Take(&relation, "source_id = ?", src.ID).Error; err != nil {
		t.Fatalf("load relation failed: %v", err)
	}
	validCommittedID := relation.LastCommittedSnapshotID
	if validCommittedID == "" {
		t.Fatalf("expected valid committed snapshot")
	}

	emptyCommittedID := sourceSnapshotID()
	if err := st.db.WithContext(ctx).Create(&sourceFileSnapshotEntity{
		SnapshotID:     emptyCommittedID,
		SourceID:       src.ID,
		TenantID:       src.TenantID,
		SnapshotType:   "COMMITTED",
		BaseSnapshotID: validCommittedID,
		FileCount:      1,
		CreatedAt:      time.Now().UTC(),
	}).Error; err != nil {
		t.Fatalf("create empty committed snapshot failed: %v", err)
	}
	if err := st.db.WithContext(ctx).Model(&sourceSnapshotRelationEntity{}).
		Where("source_id = ?", src.ID).
		Updates(map[string]any{
			"last_committed_snapshot_id": emptyCommittedID,
			"updated_at":                 time.Now().UTC(),
		}).Error; err != nil {
		t.Fatalf("point relation at empty committed snapshot failed: %v", err)
	}

	tree, token2, err := st.BuildTreeUpdateState(ctx, src.ID, items, stats)
	if err != nil {
		t.Fatalf("build tree state with empty committed baseline failed: %v", err)
	}
	node, ok := findTreeNodeByPath(tree, path)
	if !ok {
		t.Fatalf("missing node for path %s", path)
	}
	if node.UpdateType != "UNCHANGED" {
		t.Fatalf("expected fallback baseline to mark unchanged, got %s", node.UpdateType)
	}
	preview, err := st.loadPreviewSnapshotBySelectionToken(ctx, src.ID, token2)
	if err != nil {
		t.Fatalf("load preview snapshot failed: %v", err)
	}
	if preview.BaseSnapshotID != validCommittedID {
		t.Fatalf("expected preview base snapshot %s, got %s", validCommittedID, preview.BaseSnapshotID)
	}
}

func TestNonWatchSnapshotDiffMixedDirectoryAndSiblingFiles(t *testing.T) {
	t.Parallel()
	st := newTestStore(t)
	ctx := context.Background()
	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:          "tenant-1",
		Name:              "src-mixed-tree",
		RootPath:          "/tmp/watch",
		AgentID:           "agent-1",
		WatchEnabled:      false,
		IdleWindowSeconds: 10,
	})
	if err != nil {
		t.Fatalf("create non-watch source failed: %v", err)
	}

	dirPath := "/tmp/watch/test"
	nestedPath := "/tmp/watch/test/perm_1.md"
	siblingPath := "/tmp/watch/alpha.txt"
	modAt := time.Now().UTC().Add(-2 * time.Minute)
	items := []model.TreeNode{
		{
			Title: "test",
			Key:   dirPath,
			IsDir: true,
			Children: []model.TreeNode{
				{Title: "perm_1", Key: nestedPath, IsDir: false},
			},
		},
		{Title: "alpha.txt", Key: siblingPath, IsDir: false},
	}
	stats := map[string]model.TreeFileStat{
		nestedPath:  {Path: nestedPath, Size: 10, Checksum: "v1", ModTime: &modAt},
		siblingPath: {Path: siblingPath, Size: 20, Checksum: "v1", ModTime: &modAt},
	}

	_, token1, err := st.BuildTreeUpdateState(ctx, src.ID, items, stats)
	if err != nil {
		t.Fatalf("build first snapshot tree state failed: %v", err)
	}
	resp, err := st.GenerateTasksForSource(ctx, src.ID, model.GenerateTasksRequest{
		Mode:           "partial",
		Paths:          []string{nestedPath, siblingPath},
		SelectionToken: token1,
	})
	if err != nil {
		t.Fatalf("generate tasks with first selection token failed: %v", err)
	}
	if resp.AcceptedCount != 2 {
		t.Fatalf("expected accepted_count=2, got %d", resp.AcceptedCount)
	}

	tree2, _, err := st.BuildTreeUpdateState(ctx, src.ID, items, stats)
	if err != nil {
		t.Fatalf("build second snapshot tree state failed: %v", err)
	}
	for _, path := range []string{nestedPath, siblingPath} {
		node, ok := findTreeNodeByPath(tree2, path)
		if !ok {
			t.Fatalf("missing node for path %s", path)
		}
		if node.UpdateType != "UNCHANGED" {
			t.Fatalf("expected %s UNCHANGED, got %s", path, node.UpdateType)
		}
		if node.HasUpdate == nil || *node.HasUpdate {
			t.Fatalf("expected %s has_update=false, got %+v", path, node.HasUpdate)
		}
	}
}
