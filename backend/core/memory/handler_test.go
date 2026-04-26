package memory

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"lazyrag/core/common/orm"
	"lazyrag/core/evolution"
	"lazyrag/core/store"
)

type upsertMemoryAPITestResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    struct {
		ResourceID     string `json:"resource_id"`
		ResourceType   string `json:"resource_type"`
		Title          string `json:"title"`
		Content        string `json:"content"`
		ContentSummary string `json:"content_summary"`
	} `json:"data"`
}

type draftPreviewMemoryAPITestResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    struct {
		DraftStatus        string `json:"draft_status"`
		DraftSourceVersion int64  `json:"draft_source_version"`
		CurrentContent     string `json:"current_content"`
		DraftContent       string `json:"draft_content"`
		Diff               string `json:"diff"`
	} `json:"data"`
}

type generateMemoryAPITestResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    struct {
		DraftStatus        string   `json:"draft_status"`
		DraftSourceVersion int64    `json:"draft_source_version"`
		DraftContent       string   `json:"draft_content"`
		SuggestionIDs      []string `json:"suggestion_ids"`
	} `json:"data"`
}

func newMemoryTestDB(t *testing.T) *orm.DB {
	t.Helper()

	dbPath := filepath.Join(t.TempDir(), "test.db")
	db, err := orm.Connect(orm.DriverSQLite, dbPath)
	if err != nil {
		t.Fatalf("connect db: %v", err)
	}
	if err := db.AutoMigrate(orm.AllModelsForDDL()...); err != nil {
		t.Fatalf("auto migrate: %v", err)
	}
	return db
}

func TestUpsertCreatesThenUpdatesMemory(t *testing.T) {
	db := newMemoryTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	firstReq := httptest.NewRequest(http.MethodPut, "/api/core/memory", strings.NewReader(`{"content":"第一版记忆内容"}`))
	firstReq.Header.Set("Content-Type", "application/json")
	firstReq.Header.Set("X-User-Id", "u1")
	firstReq.Header.Set("X-User-Name", "User 1")
	firstRec := httptest.NewRecorder()

	Upsert(firstRec, firstReq)

	if firstRec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", firstRec.Code, firstRec.Body.String())
	}

	var firstResp upsertMemoryAPITestResponse
	if err := json.Unmarshal(firstRec.Body.Bytes(), &firstResp); err != nil {
		t.Fatalf("decode first response: %v", err)
	}
	if firstResp.Data.ResourceType != "memory" {
		t.Fatalf("expected memory resource type, got %q", firstResp.Data.ResourceType)
	}
	if firstResp.Data.Content != "第一版记忆内容" {
		t.Fatalf("unexpected first content: %q", firstResp.Data.Content)
	}

	var created orm.SystemMemory
	if err := db.Where("user_id = ?", "u1").Take(&created).Error; err != nil {
		t.Fatalf("query created memory: %v", err)
	}
	if created.Version != 1 {
		t.Fatalf("expected created version 1, got %d", created.Version)
	}

	secondReq := httptest.NewRequest(http.MethodPut, "/api/core/memory", strings.NewReader(`{"content":"第二版记忆内容"}`))
	secondReq.Header.Set("Content-Type", "application/json")
	secondReq.Header.Set("X-User-Id", "u1")
	secondReq.Header.Set("X-User-Name", "User 1")
	secondRec := httptest.NewRecorder()

	Upsert(secondRec, secondReq)

	if secondRec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", secondRec.Code, secondRec.Body.String())
	}

	var updated orm.SystemMemory
	if err := db.Where("user_id = ?", "u1").Take(&updated).Error; err != nil {
		t.Fatalf("query updated memory: %v", err)
	}
	if updated.ID != created.ID {
		t.Fatalf("expected update in place, got new id %q from old %q", updated.ID, created.ID)
	}
	if updated.Content != "第二版记忆内容" {
		t.Fatalf("unexpected updated content: %q", updated.Content)
	}
	if updated.Version != 2 {
		t.Fatalf("expected updated version 2, got %d", updated.Version)
	}
	if updated.UpdatedAt.Before(created.UpdatedAt) {
		t.Fatalf("expected updated_at to move forward")
	}
}

func TestDraftPreviewReturnsCurrentDraftAndDiff(t *testing.T) {
	db := newMemoryTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	now := time.Now()
	row := orm.SystemMemory{
		ID:                 "memory-1",
		UserID:             "u1",
		Content:            "current memory",
		ContentHash:        "hash-current",
		Version:            2,
		DraftContent:       "updated memory",
		DraftSourceVersion: 2,
		DraftStatus:        "pending_confirm",
		UpdatedBy:          "u1",
		UpdatedByName:      "User 1",
		CreatedAt:          now,
		UpdatedAt:          now,
	}
	if err := db.Create(&row).Error; err != nil {
		t.Fatalf("create memory: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/api/core/memory:draft-preview", nil)
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	DraftPreview(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	var resp draftPreviewMemoryAPITestResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Code != 0 {
		t.Fatalf("expected code 0, got %d message=%s", resp.Code, resp.Message)
	}
	if resp.Data.DraftStatus != "pending_confirm" {
		t.Fatalf("expected pending_confirm, got %q", resp.Data.DraftStatus)
	}
	if resp.Data.CurrentContent != "current memory" {
		t.Fatalf("unexpected current content: %q", resp.Data.CurrentContent)
	}
	if resp.Data.DraftContent != "updated memory" {
		t.Fatalf("unexpected draft content: %q", resp.Data.DraftContent)
	}
	if !strings.Contains(resp.Data.Diff, "-current memory") {
		t.Fatalf("expected diff to contain removed current content, got %q", resp.Data.Diff)
	}
	if !strings.Contains(resp.Data.Diff, "+updated memory") {
		t.Fatalf("expected diff to contain added draft content, got %q", resp.Data.Diff)
	}
}

func TestGenerateOverwritesExistingPendingDraft(t *testing.T) {
	db := newMemoryTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/chat/memory/generate" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"data": map[string]any{"content": "new draft content"},
		})
	})
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Skipf("listener unavailable in current test environment: %v", err)
	}
	server := &http.Server{Handler: handler}
	go func() { _ = server.Serve(listener) }()
	defer func() { _ = server.Shutdown(context.Background()) }()
	t.Setenv("LAZYRAG_CHAT_SERVICE_URL", fmt.Sprintf("http://%s", listener.Addr().String()))

	now := time.Now()
	row := orm.SystemMemory{
		ID:                 "memory-1",
		UserID:             "u1",
		Content:            "current memory",
		ContentHash:        evolution.HashContent("current memory"),
		Version:            3,
		DraftContent:       "old draft content",
		DraftSourceVersion: 2,
		DraftStatus:        "pending_confirm",
		Ext:                evolution.WithDraftSuggestionIDs(nil, []string{"old-suggestion"}),
		UpdatedBy:          "u1",
		UpdatedByName:      "User 1",
		CreatedAt:          now,
		UpdatedAt:          now,
	}
	if err := db.Create(&row).Error; err != nil {
		t.Fatalf("create memory: %v", err)
	}
	suggestion := orm.ResourceSuggestion{
		ID:           "suggestion-1",
		UserID:       "u1",
		ResourceType: evolution.ResourceTypeMemory,
		ResourceKey:  evolution.SystemResourceKey(evolution.ResourceTypeMemory),
		Action:       evolution.SuggestionActionModify,
		SessionID:    "session-1",
		Title:        "memory suggestion",
		Content:      "update memory",
		Status:       evolution.SuggestionStatusAccepted,
		CreatedAt:    now,
		UpdatedAt:    now,
	}
	if err := db.Create(&suggestion).Error; err != nil {
		t.Fatalf("create suggestion: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/core/memory:generate", strings.NewReader(`{"suggestion_ids":["suggestion-1"],"user_instruct":"生成新版"}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-User-Id", "u1")
	req.Header.Set("X-User-Name", "User 1")
	rec := httptest.NewRecorder()

	Generate(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	var resp generateMemoryAPITestResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Code != 0 {
		t.Fatalf("expected code 0, got %d message=%s", resp.Code, resp.Message)
	}
	if resp.Data.DraftStatus != "pending_confirm" {
		t.Fatalf("expected pending_confirm, got %q", resp.Data.DraftStatus)
	}
	if resp.Data.DraftContent != "new draft content" {
		t.Fatalf("unexpected draft content: %q", resp.Data.DraftContent)
	}

	var updated orm.SystemMemory
	if err := db.Where("id = ?", row.ID).Take(&updated).Error; err != nil {
		t.Fatalf("query updated memory: %v", err)
	}
	if updated.DraftContent != "new draft content" {
		t.Fatalf("expected draft to be overwritten, got %q", updated.DraftContent)
	}
	if updated.DraftSourceVersion != row.Version {
		t.Fatalf("expected draft source version %d, got %d", row.Version, updated.DraftSourceVersion)
	}
	gotIDs := evolution.DraftSuggestionIDs(updated.Ext)
	if len(gotIDs) != 1 || gotIDs[0] != "suggestion-1" {
		t.Fatalf("expected draft suggestion ids to be replaced, got %#v", gotIDs)
	}
}
