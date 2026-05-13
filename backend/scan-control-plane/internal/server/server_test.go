package server

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"go.uber.org/zap"

	"github.com/lazyrag/scan_control_plane/internal/coreclient"
	"github.com/lazyrag/scan_control_plane/internal/model"
	"github.com/lazyrag/scan_control_plane/internal/store"
)

func newServerTestStore(t *testing.T) *store.Store {
	t.Helper()
	dbPath := filepath.Join(t.TempDir(), "cp.db")
	st, err := store.New("sqlite", dbPath, 10*time.Second, zap.NewNop())
	if err != nil {
		t.Fatalf("new store failed: %v", err)
	}
	t.Cleanup(func() {
		_ = st.Close()
	})
	return st
}

func TestFetchTreeFileStatsRunsInParallel(t *testing.T) {
	t.Parallel()

	var inFlight int64
	var maxInFlight int64
	var ts *httptest.Server
	func() {
		defer func() {
			if r := recover(); r != nil {
				t.Skipf("skip: httptest listener not available in current sandbox: %v", r)
			}
		}()
		ts = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/fs/stat" {
				http.NotFound(w, r)
				return
			}
			var req struct {
				Path string `json:"path"`
			}
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				http.Error(w, "bad json", http.StatusBadRequest)
				return
			}
			current := atomic.AddInt64(&inFlight, 1)
			for {
				prev := atomic.LoadInt64(&maxInFlight)
				if current <= prev {
					break
				}
				if atomic.CompareAndSwapInt64(&maxInFlight, prev, current) {
					break
				}
			}
			defer atomic.AddInt64(&inFlight, -1)
			time.Sleep(50 * time.Millisecond)

			_ = json.NewEncoder(w).Encode(map[string]any{
				"path":     req.Path,
				"size":     123,
				"mod_time": time.Now().UTC(),
				"is_dir":   false,
				"checksum": "sha1",
			})
		}))
	}()
	if ts == nil {
		return
	}
	defer ts.Close()

	h := &Handler{
		client: &http.Client{Timeout: 2 * time.Second},
		log:    zap.NewNop(),
	}

	items := []model.TreeNode{
		{Key: "/tmp/watch/a.txt", IsDir: false},
		{Key: "/tmp/watch/b.txt", IsDir: false},
		{Key: "/tmp/watch/c.txt", IsDir: false},
		{Key: "/tmp/watch/d.txt", IsDir: false},
		{Key: "/tmp/watch/e.txt", IsDir: false},
		{Key: "/tmp/watch/f.txt", IsDir: false},
	}

	stats, err := h.fetchTreeFileStats(context.Background(), ts.URL, items)
	if err != nil {
		t.Fatalf("fetchTreeFileStats failed: %v", err)
	}
	if len(stats) != len(items) {
		t.Fatalf("expected %d stats, got %d", len(items), len(stats))
	}
	if atomic.LoadInt64(&maxInFlight) <= 1 {
		t.Fatalf("expected concurrent fs/stat calls, max in-flight=%d", atomic.LoadInt64(&maxInFlight))
	}
}

func TestDecodeJSONRejectsUnknownFields(t *testing.T) {
	t.Parallel()

	req := httptest.NewRequest(http.MethodPost, "/decode", strings.NewReader(`{"agent_id":"a1","tenant_id":"t1","unknown":"x"}`))
	w := httptest.NewRecorder()
	var out model.PullCommandsRequest
	if ok := decodeJSON(w, req, &out); ok {
		t.Fatalf("expected decodeJSON to reject unknown fields")
	}
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 status, got %d", w.Code)
	}
}

func TestDecodeJSONRejectsMultipleJSONValues(t *testing.T) {
	t.Parallel()

	req := httptest.NewRequest(http.MethodPost, "/decode", strings.NewReader(`{"agent_id":"a1","tenant_id":"t1"} {"x":1}`))
	w := httptest.NewRecorder()
	var out model.PullCommandsRequest
	if ok := decodeJSON(w, req, &out); ok {
		t.Fatalf("expected decodeJSON to reject multiple JSON payloads")
	}
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 status, got %d", w.Code)
	}
}

func TestOpenAPISpecHidesAgentFSCompatAliases(t *testing.T) {
	t.Parallel()

	spec := buildOpenAPISpec()
	paths, ok := spec["paths"].(map[string]any)
	if !ok {
		t.Fatalf("expected OpenAPI paths map, got %#v", spec["paths"])
	}

	for _, path := range []string{
		"/api/scan/agents/fs/tree",
		"/api/scan/agents/fs/validate",
	} {
		if _, ok := paths[path]; !ok {
			t.Fatalf("expected canonical path %s in OpenAPI spec", path)
		}
	}
	for _, path := range []string{
		"/api/v1/agents/fs/tree",
		"/api/v1/agents/fs/validate",
	} {
		if _, ok := paths[path]; ok {
			t.Fatalf("compat alias %s should not be exposed in OpenAPI spec", path)
		}
	}
}

type fakeKnowledgeBaseCore struct {
	createResult coreclient.CreateKnowledgeBaseResult
	createErr    error
	foundKB      coreclient.KnowledgeBaseRef
	found        bool
	findErr      error
}

func (f fakeKnowledgeBaseCore) Enabled() bool { return true }

func (f fakeKnowledgeBaseCore) SubmitParseTask(context.Context, store.PendingTask, string, string, int64) (coreclient.SubmitResult, error) {
	return coreclient.SubmitResult{}, nil
}

func (f fakeKnowledgeBaseCore) CreateKnowledgeBase(context.Context, coreclient.CreateKnowledgeBaseRequest) (coreclient.CreateKnowledgeBaseResult, error) {
	return f.createResult, f.createErr
}

func (f fakeKnowledgeBaseCore) FindKnowledgeBaseByName(context.Context, string, string, string) (coreclient.KnowledgeBaseRef, bool, error) {
	return f.foundKB, f.found, f.findErr
}

func (f fakeKnowledgeBaseCore) SearchTasks(context.Context, []string) (map[string]coreclient.TaskState, error) {
	return map[string]coreclient.TaskState{}, nil
}

func (f fakeKnowledgeBaseCore) SearchTasksByDataset(context.Context, string, []string) (map[string]coreclient.TaskState, error) {
	return map[string]coreclient.TaskState{}, nil
}

func TestCreateKnowledgeBaseReusesUnboundScanManagedDataset(t *testing.T) {
	t.Parallel()

	st := newServerTestStore(t)
	h := &Handler{
		store: st,
		core: fakeKnowledgeBaseCore{
			createErr: &coreclient.HTTPError{StatusCode: http.StatusConflict, Body: "dataset name already exists"},
			foundKB: coreclient.KnowledgeBaseRef{
				DatasetID:   "ds_scan_half_created",
				Name:        "local kb",
				ScanManaged: true,
			},
			found: true,
		},
		log: zap.NewNop(),
	}

	req := httptest.NewRequest(http.MethodPost, "/api/scan/knowledge-bases", strings.NewReader(`{"name":"local kb","algo":{"algo_id":"algo-1"}}`))
	req.Header.Set("X-User-Id", "user-1")
	w := httptest.NewRecorder()

	h.createKnowledgeBase(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", w.Code, w.Body.String())
	}
	var resp model.CreateKnowledgeBaseResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response failed: %v", err)
	}
	if resp.DatasetID != "ds_scan_half_created" || resp.Name != "local kb" {
		t.Fatalf("expected reused dataset, got %#v", resp)
	}
}

func TestCreateKnowledgeBaseDoesNotReuseBoundScanManagedDataset(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	st := newServerTestStore(t)
	if err := st.RegisterAgent(ctx, model.RegisterAgentRequest{
		AgentID:  "agent-1",
		TenantID: "tenant-1",
		Hostname: "test",
		Version:  "v1",
	}); err != nil {
		t.Fatalf("register agent failed: %v", err)
	}
	if _, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:     "tenant-1",
		CreateUserID: "user-1",
		Name:         "bound source",
		AgentID:      "agent-1",
		RootPath:     "/tmp/bound-source",
		DatasetID:    "ds_scan_bound",
	}); err != nil {
		t.Fatalf("create source failed: %v", err)
	}

	h := &Handler{
		store: st,
		core: fakeKnowledgeBaseCore{
			createErr: &coreclient.HTTPError{StatusCode: http.StatusConflict, Body: "dataset name already exists"},
			foundKB: coreclient.KnowledgeBaseRef{
				DatasetID:   "ds_scan_bound",
				Name:        "local kb",
				ScanManaged: true,
			},
			found: true,
		},
		log: zap.NewNop(),
	}

	req := httptest.NewRequest(http.MethodPost, "/api/scan/knowledge-bases", strings.NewReader(`{"name":"local kb","algo":{"algo_id":"algo-1"}}`))
	req.Header.Set("X-User-Id", "user-1")
	w := httptest.NewRecorder()

	h.createKnowledgeBase(w, req)

	if w.Code != http.StatusConflict {
		t.Fatalf("expected status 409, got %d body=%s", w.Code, w.Body.String())
	}
}

func TestFilterTreeByKeywordKeepsMatchingAncestors(t *testing.T) {
	t.Parallel()

	items := []model.TreeNode{
		{Title: "root", Key: "/root", IsDir: true, Children: []model.TreeNode{
			{Title: "docs", Key: "/root/docs", IsDir: true, Children: []model.TreeNode{
				{Title: "ReleaseNotes.md", Key: "/root/docs/ReleaseNotes.md", IsDir: false},
				{Title: "guide.txt", Key: "/root/docs/guide.txt", IsDir: false},
			}},
			{Title: "assets", Key: "/root/assets", IsDir: true, Children: []model.TreeNode{
				{Title: "logo.png", Key: "/root/assets/logo.png", IsDir: false},
			}},
		}},
	}

	got := filterTreeByKeyword(items, "release")
	if len(got) != 1 {
		t.Fatalf("expected root to be kept, got %d nodes", len(got))
	}
	if len(got[0].Children) != 1 || got[0].Children[0].Title != "docs" {
		t.Fatalf("expected only docs ancestor, got %#v", got[0].Children)
	}
	docs := got[0].Children[0]
	if len(docs.Children) != 1 || docs.Children[0].Title != "ReleaseNotes.md" {
		t.Fatalf("expected only matching release file, got %#v", docs.Children)
	}
}

func TestPathTreeByAgentFiltersKeywordWhenAgentReturnsFullTree(t *testing.T) {
	t.Parallel()

	var receivedKeyword string
	var ts *httptest.Server
	func() {
		defer func() {
			if r := recover(); r != nil {
				t.Skipf("skip: httptest listener not available in current sandbox: %v", r)
			}
		}()
		ts = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/fs/tree" {
				http.NotFound(w, r)
				return
			}
			var req map[string]any
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				http.Error(w, "bad json", http.StatusBadRequest)
				return
			}
			receivedKeyword, _ = req["keyword"].(string)
			_ = json.NewEncoder(w).Encode(model.AgentPathTreeResponse{
				Items: []model.TreeNode{
					{Title: "root", Key: "/root", IsDir: true, Children: []model.TreeNode{
						{Title: "ReleaseNotes.md", Key: "/root/ReleaseNotes.md", IsDir: false},
						{Title: "guide.txt", Key: "/root/guide.txt", IsDir: false},
					}},
				},
			})
		}))
	}()
	if ts == nil {
		return
	}
	defer ts.Close()

	ctx := context.Background()
	st := newServerTestStore(t)
	if err := st.RegisterAgent(ctx, model.RegisterAgentRequest{
		AgentID:    "agent-keyword",
		TenantID:   "tenant-1",
		Hostname:   "test",
		Version:    "v1",
		ListenAddr: ts.URL,
	}); err != nil {
		t.Fatalf("register agent failed: %v", err)
	}
	h := &Handler{
		store:  st,
		client: &http.Client{Timeout: 2 * time.Second},
		log:    zap.NewNop(),
	}

	body := `{"agent_id":"agent-keyword","path":"/root","keyword":"release","include_files":true}`
	req := httptest.NewRequest(http.MethodPost, "/api/scan/agents/fs/tree", strings.NewReader(body))
	w := httptest.NewRecorder()

	h.pathTreeByAgent(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200 status, got %d: %s", w.Code, w.Body.String())
	}
	if receivedKeyword != "release" {
		t.Fatalf("expected keyword to be forwarded, got %q", receivedKeyword)
	}
	var resp model.AgentPathTreeResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response failed: %v", err)
	}
	if len(resp.Items) != 1 || len(resp.Items[0].Children) != 1 {
		t.Fatalf("expected filtered tree, got %#v", resp.Items)
	}
	if resp.Items[0].Children[0].Title != "ReleaseNotes.md" {
		t.Fatalf("expected matching release file, got %#v", resp.Items[0].Children)
	}
}

func TestApplyCoreTaskStateUsesCoreParseStateWithoutChangingSnapshotUpdate(t *testing.T) {
	t.Parallel()

	hasUpdate := true
	item := model.SourceDocumentItem{
		DocumentID:             1,
		HasUpdate:              &hasUpdate,
		UpdateType:             "NEW",
		UpdateDesc:             "新文件待解析",
		ParseState:             "QUEUED",
		DesiredVersionID:       "v2",
		CurrentVersionID:       "",
		ParseTaskID:            10,
		ParseTaskAction:        "CREATE",
		ParseTaskTargetVersion: "v2",
	}

	applyCoreTaskStateToSourceDocumentItem(&item, "SUCCEEDED")

	if item.UpdateType != "NEW" {
		t.Fatalf("expected snapshot update_type NEW to be preserved, got %s", item.UpdateType)
	}
	if item.HasUpdate == nil || !*item.HasUpdate {
		t.Fatalf("expected snapshot has_update=true to be preserved, got %+v", item.HasUpdate)
	}
	if item.ParseState != "SUCCEEDED" {
		t.Fatalf("expected parse_state SUCCEEDED, got %s", item.ParseState)
	}
	if !shouldMarkSourceDocumentSucceededFromCore(item) {
		t.Fatalf("expected core success to be persisted")
	}
}

func TestApplyCoreTaskStateNormalizesSubmittedToRunning(t *testing.T) {
	t.Parallel()

	hasUpdate := true
	item := model.SourceDocumentItem{
		DocumentID:             1,
		HasUpdate:              &hasUpdate,
		UpdateType:             "MODIFIED",
		UpdateDesc:             "内容变化待重解析",
		ParseState:             "SUBMITTED",
		DesiredVersionID:       "v2",
		CurrentVersionID:       "v1",
		ParseTaskID:            10,
		ParseTaskAction:        "REPARSE",
		ParseTaskTargetVersion: "v2",
	}

	applyCoreTaskStateToSourceDocumentItem(&item, "TASK_STATE_SUBMITTED")

	if item.ParseState != "RUNNING" {
		t.Fatalf("expected submitted core state to be normalized to RUNNING, got %s", item.ParseState)
	}
	if item.CoreTaskState != "RUNNING" {
		t.Fatalf("expected core_task_state RUNNING, got %s", item.CoreTaskState)
	}
	if item.UpdateType != "MODIFIED" {
		t.Fatalf("expected snapshot update_type MODIFIED to be preserved, got %s", item.UpdateType)
	}
}

func TestApplyCoreTaskStateKeepsUpdateForStaleTaskVersion(t *testing.T) {
	t.Parallel()

	hasUpdate := true
	item := model.SourceDocumentItem{
		DocumentID:             1,
		HasUpdate:              &hasUpdate,
		UpdateType:             "MODIFIED",
		UpdateDesc:             "内容变化待重解析",
		ParseState:             "QUEUED",
		DesiredVersionID:       "v2",
		CurrentVersionID:       "v1",
		ParseTaskID:            10,
		ParseTaskAction:        "REPARSE",
		ParseTaskTargetVersion: "v1",
	}

	applyCoreTaskStateToSourceDocumentItem(&item, "SUCCEEDED")

	if item.UpdateType != "MODIFIED" {
		t.Fatalf("expected stale task to keep update_type MODIFIED, got %s", item.UpdateType)
	}
	if item.ParseState != "QUEUED" {
		t.Fatalf("expected stale task to keep parse_state QUEUED, got %s", item.ParseState)
	}
	if item.HasUpdate == nil || !*item.HasUpdate {
		t.Fatalf("expected has_update=true for stale task, got %+v", item.HasUpdate)
	}
	if shouldMarkSourceDocumentSucceededFromCore(item) {
		t.Fatalf("did not expect stale core success to be persisted")
	}
}

func TestApplyCoreTaskStateIgnoresStaleFailure(t *testing.T) {
	t.Parallel()

	hasUpdate := true
	item := model.SourceDocumentItem{
		DocumentID:             1,
		HasUpdate:              &hasUpdate,
		UpdateType:             "MODIFIED",
		UpdateDesc:             "内容变化待重解析",
		ParseState:             "PENDING",
		DesiredVersionID:       "v2",
		CurrentVersionID:       "v1",
		ParseTaskID:            10,
		ParseTaskAction:        "REPARSE",
		ParseTaskTargetVersion: "v1",
		CoreTaskID:             "core-task-old",
	}

	applyCoreTaskStateToSourceDocumentItem(&item, "FAILED")

	if item.ParseState != "PENDING" {
		t.Fatalf("expected stale failed task to keep parse_state PENDING, got %s", item.ParseState)
	}
	if item.CoreTaskState != "" {
		t.Fatalf("expected stale failed task not to set core_task_state, got %s", item.CoreTaskState)
	}
	if item.UpdateType != "MODIFIED" {
		t.Fatalf("expected stale failed task to keep update_type MODIFIED, got %s", item.UpdateType)
	}
}

func TestPublicParseStateCollapsesInternalAndCoreStates(t *testing.T) {
	t.Parallel()

	cases := []struct {
		in   string
		want string
	}{
		{in: "", want: ""},
		{in: "PENDING", want: "PROCESSING"},
		{in: "QUEUED", want: "PROCESSING"},
		{in: "RUNNING", want: "PROCESSING"},
		{in: "STAGING", want: "PROCESSING"},
		{in: "SUBMITTED", want: "PROCESSING"},
		{in: "RETRY_WAITING", want: "PROCESSING"},
		{in: "CREATING", want: "PROCESSING"},
		{in: "UPLOADING", want: "PROCESSING"},
		{in: "UPLOADED", want: "PROCESSING"},
		{in: "TASK_STATE_SUBMITTED", want: "PROCESSING"},
		{in: "SUCCEEDED", want: "SUCCESS"},
		{in: "SUCCESS", want: "SUCCESS"},
		{in: "TASK_STATE_SUCCEEDED", want: "SUCCESS"},
		{in: "DELETED", want: "SUCCESS"},
		{in: "FAILED", want: "FAILED"},
		{in: "SUBMIT_FAILED", want: "FAILED"},
		{in: "CANCELED", want: "FAILED"},
		{in: "SUSPENDED", want: "FAILED"},
	}

	for _, tc := range cases {
		if got := publicParseState(tc.in); got != tc.want {
			t.Fatalf("publicParseState(%q) = %q, want %q", tc.in, got, tc.want)
		}
	}
}

func TestNormalizeSourceDocumentParseStatesForResponse(t *testing.T) {
	t.Parallel()

	items := []model.SourceDocumentItem{
		{
			ParseState:              "STAGING",
			CoreTaskState:           "TASK_STATE_SUBMITTED",
			ScanOrchestrationStatus: "SUCCEEDED",
		},
	}

	normalizeSourceDocumentParseStatesForResponse(items)
	if items[0].ParseState != "PROCESSING" {
		t.Fatalf("expected parse_state PROCESSING, got %s", items[0].ParseState)
	}
	if items[0].CoreTaskState != "PROCESSING" {
		t.Fatalf("expected core_task_state PROCESSING, got %s", items[0].CoreTaskState)
	}
	if items[0].ScanOrchestrationStatus != "SUCCESS" {
		t.Fatalf("expected scan_orchestration_status SUCCESS, got %s", items[0].ScanOrchestrationStatus)
	}
}

func TestNormalizeTreeParseQueueStatesForResponse(t *testing.T) {
	t.Parallel()

	items := []model.TreeNode{
		{Key: "/root/a.md", ParseQueueState: "STAGING", CoreTaskState: "TASK_STATE_SUBMITTED"},
		{Key: "/root/dir", IsDir: true, Children: []model.TreeNode{
			{Key: "/root/dir/b.md", ParseQueueState: "SUCCEEDED"},
			{Key: "/root/dir/c.md", ParseQueueState: "SUBMIT_FAILED"},
		}},
	}

	got := normalizeTreeParseQueueStatesForResponse(items)
	if got[0].ParseQueueState != "PROCESSING" {
		t.Fatalf("expected first node PROCESSING, got %s", got[0].ParseQueueState)
	}
	if got[0].CoreTaskState != "PROCESSING" {
		t.Fatalf("expected first node core_task_state PROCESSING, got %s", got[0].CoreTaskState)
	}
	if got[1].Children[0].ParseQueueState != "SUCCESS" {
		t.Fatalf("expected child success state, got %s", got[1].Children[0].ParseQueueState)
	}
	if got[1].Children[1].ParseQueueState != "FAILED" {
		t.Fatalf("expected child failed state, got %s", got[1].Children[1].ParseQueueState)
	}
}

func TestListSourcesIncludesCurrentUserBatchOverview(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	st := newServerTestStore(t)
	if err := st.RegisterAgent(ctx, model.RegisterAgentRequest{
		AgentID:  "agent-1",
		TenantID: "tenant-1",
		Hostname: "test",
		Version:  "v1",
	}); err != nil {
		t.Fatalf("register agent failed: %v", err)
	}

	src, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:              "tenant-1",
		CreateUserID:          "user-1",
		Name:                  "cloud source",
		AgentID:               "agent-1",
		DefaultOriginType:     string(model.OriginTypeCloudSync),
		DefaultOriginPlatform: "FEISHU",
		DefaultTriggerPolicy:  string(model.TriggerPolicyImmediate),
	})
	if err != nil {
		t.Fatalf("create source failed: %v", err)
	}
	if _, err := st.CreateSource(ctx, model.CreateSourceRequest{
		TenantID:              "tenant-1",
		CreateUserID:          "user-2",
		Name:                  "other source",
		AgentID:               "agent-1",
		DefaultOriginType:     string(model.OriginTypeCloudSync),
		DefaultOriginPlatform: "FEISHU",
	}); err != nil {
		t.Fatalf("create other source failed: %v", err)
	}

	enabled := true
	if _, err := st.UpsertCloudSourceBinding(ctx, src.ID, model.UpsertCloudSourceBindingRequest{
		Provider:         "feishu",
		Enabled:          &enabled,
		AuthConnectionID: "conn-1",
		TargetType:       "wiki_space",
		TargetRef:        "space-1",
	}); err != nil {
		t.Fatalf("upsert cloud binding failed: %v", err)
	}

	mutations, err := st.BuildMutationsFromEvents(ctx, []model.FileEvent{
		{
			SourceID:       src.ID,
			EventType:      "modified",
			Path:           "/tmp/watch/a.txt",
			OccurredAt:     time.Now().UTC(),
			OriginType:     string(model.OriginTypeCloudSync),
			OriginPlatform: "FEISHU",
			TriggerPolicy:  string(model.TriggerPolicyImmediate),
		},
	})
	if err != nil {
		t.Fatalf("build mutations failed: %v", err)
	}
	if err := st.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		t.Fatalf("apply mutations failed: %v", err)
	}

	h := &Handler{store: st, core: coreclient.NewNoop(), log: zap.NewNop()}
	req := httptest.NewRequest(http.MethodGet, "/api/scan/sources?tenant_id=tenant-1", nil)
	req.Header.Set("X-User-Id", "user-1")
	w := httptest.NewRecorder()
	h.listSources(w, req)
	if w.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", w.Code, w.Body.String())
	}

	var resp struct {
		Items []model.Source `json:"items"`
	}
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response failed: %v", err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("expected current user's source only, got %d", len(resp.Items))
	}
	item := resp.Items[0]
	if item.ID != src.ID {
		t.Fatalf("expected source %s, got %s", src.ID, item.ID)
	}
	if item.CloudBinding == nil || item.CloudBinding.Status != "ACTIVE" {
		t.Fatalf("expected active cloud binding, got %#v", item.CloudBinding)
	}
	if item.Documents == nil {
		t.Fatalf("expected documents overview")
	}
	if item.Documents.Total != 1 || item.Documents.Summary.TotalDocumentCount != 1 {
		t.Fatalf("expected one document, got total=%d summary=%d", item.Documents.Total, item.Documents.Summary.TotalDocumentCount)
	}
	if len(item.Documents.Items) != 1 || item.Documents.Items[0].Name != "a.txt" {
		t.Fatalf("expected first document a.txt, got %#v", item.Documents.Items)
	}
}

func TestBuildSourceDocumentsSummaryWithCoreKeepsSnapshotUpdateCounts(t *testing.T) {
	t.Parallel()

	refs := []store.SourceDocumentCoreRef{
		{
			DocumentID:       1,
			ParseStatus:      "QUEUED",
			DesiredVersionID: "v2",
			CurrentVersionID: "",
			TaskID:           10,
			TaskAction:       "CREATE",
			TargetVersionID:  "v2",
			CoreTaskID:       "core-task-1",
		},
	}
	states := map[string]coreclient.TaskState{
		"core-task-1": {TaskID: "core-task-1", TaskState: "SUCCEEDED"},
	}

	summary := buildSourceDocumentsSummaryWithCore(refs, states, 0)
	if summary.NewCount != 1 || summary.PendingPullCount != 1 {
		t.Fatalf("expected snapshot update counts to be preserved, got new=%d pending=%d", summary.NewCount, summary.PendingPullCount)
	}
	if summary.ParsedDocumentCount != 1 {
		t.Fatalf("expected parsed_document_count=1, got %d", summary.ParsedDocumentCount)
	}
}

func TestBuildSourceDocumentsSummaryWithCoreIgnoresStaleFailure(t *testing.T) {
	t.Parallel()

	refs := []store.SourceDocumentCoreRef{
		{
			DocumentID:       1,
			ParseStatus:      "PENDING",
			DesiredVersionID: "v2",
			CurrentVersionID: "v1",
			TaskID:           10,
			TaskAction:       "REPARSE",
			TargetVersionID:  "v1",
			CoreTaskID:       "core-task-old",
		},
	}
	states := map[string]coreclient.TaskState{
		"core-task-old": {TaskID: "core-task-old", TaskState: "FAILED"},
	}

	summary := buildSourceDocumentsSummaryWithCore(refs, states, 0)
	if summary.ModifiedCount != 1 || summary.PendingPullCount != 1 {
		t.Fatalf("expected modified document to remain pending, got modified=%d pending=%d", summary.ModifiedCount, summary.PendingPullCount)
	}
	if summary.ParsedDocumentCount != 1 {
		t.Fatalf("expected stale failure not to hide current parsed version, got parsed_document_count=%d", summary.ParsedDocumentCount)
	}
}
