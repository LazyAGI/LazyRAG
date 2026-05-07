package skill

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/mux"
	"gorm.io/gorm"

	"lazyrag/core/common/orm"
	"lazyrag/core/evolution"
	"lazyrag/core/store"
)

type generateSkillAPITestResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    struct {
		DraftStatus        string `json:"draft_status"`
		DraftSourceVersion int64  `json:"draft_source_version"`
		DraftPath          string `json:"draft_path"`
		Outdated           bool   `json:"outdated"`
	} `json:"data"`
}

type draftPreviewAPITestResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    struct {
		SkillID            string `json:"skill_id"`
		DraftStatus        string `json:"draft_status"`
		DraftSourceVersion int64  `json:"draft_source_version"`
		CurrentContent     string `json:"current_content"`
		DraftContent       string `json:"draft_content"`
		Diff               string `json:"diff"`
		Outdated           bool   `json:"outdated"`
	} `json:"data"`
}

type listSkillsAPITestResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    struct {
		Items []struct {
			SkillID                     string `json:"skill_id"`
			HasPendingReviewSuggestions bool   `json:"has_pending_review_suggestions"`
			SuggestionStatus            string `json:"suggestion_status"`
			Children                    []struct {
				SkillID                     string `json:"skill_id"`
				HasPendingReviewSuggestions bool   `json:"has_pending_review_suggestions"`
				SuggestionStatus            string `json:"suggestion_status"`
			} `json:"children"`
		} `json:"items"`
		Page     int `json:"page"`
		PageSize int `json:"page_size"`
		Total    int `json:"total"`
	} `json:"data"`
}

type getSkillDetailAPITestResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    struct {
		SkillID                     string `json:"skill_id"`
		HasPendingReviewSuggestions bool   `json:"has_pending_review_suggestions"`
		SuggestionStatus            string `json:"suggestion_status"`
		Children                    []any  `json:"children"`
	} `json:"data"`
}

func newSkillTestDB(t *testing.T) *orm.DB {
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

func TestInternalCreateCreatesSkillDirectly(t *testing.T) {
	db := newSkillTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	now := time.Now()
	conversation := orm.Conversation{
		ID:        "conv-create",
		ChannelID: "default",
		BaseModel: orm.BaseModel{
			CreateUserID:   "u1",
			CreateUserName: "User 1",
			CreatedAt:      now,
			UpdatedAt:      now,
		},
	}
	if err := db.Create(&conversation).Error; err != nil {
		t.Fatalf("create conversation: %v", err)
	}

	content := "---\nname: release-check\ndescription: Release checklist\n---\n# Release Checklist\n\n1. Run tests.\n2. Verify rollback plan.\n"
	body, err := json.Marshal(map[string]string{
		"session_id": "conv-create_1",
		"category":   "coding",
		"skill_name": "release-check",
		"content":    content,
	})
	if err != nil {
		t.Fatalf("marshal body: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/skill/create", strings.NewReader(string(body)))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	Create(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	var resp getSkillDetailAPITestResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Code != 0 {
		t.Fatalf("expected code 0, got %d message=%s", resp.Code, resp.Message)
	}
	if strings.TrimSpace(resp.Data.SkillID) == "" {
		t.Fatalf("expected created skill_id in response")
	}

	var suggestionCount int64
	if err := db.Model(&orm.ResourceSuggestion{}).Count(&suggestionCount).Error; err != nil {
		t.Fatalf("count suggestions: %v", err)
	}
	if suggestionCount != 0 {
		t.Fatalf("expected no resource suggestions, got %d", suggestionCount)
	}

	var row orm.SkillResource
	relativePath := evolution.ParentSkillRelativePath("coding", "release-check")
	if err := db.Where("owner_user_id = ? AND relative_path = ?", "u1", relativePath).Take(&row).Error; err != nil {
		t.Fatalf("query created skill: %v", err)
	}
	if row.ID != resp.Data.SkillID {
		t.Fatalf("expected response skill_id %q to match row id %q", resp.Data.SkillID, row.ID)
	}
	if row.Description != "Release checklist" {
		t.Fatalf("expected description %q, got %q", "Release checklist", row.Description)
	}

	if row.Content != content {
		t.Fatalf("expected DB content %q, got %q", content, row.Content)
	}
	if row.ContentSize != int64(len([]byte(content))) {
		t.Fatalf("expected content_size %d, got %d", len([]byte(content)), row.ContentSize)
	}
}

func TestInternalRemoveDeletesSkillDirectly(t *testing.T) {
	db := newSkillTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	now := time.Now()
	conversation := orm.Conversation{
		ID:        "conv-remove",
		ChannelID: "default",
		BaseModel: orm.BaseModel{
			CreateUserID:   "u1",
			CreateUserName: "User 1",
			CreatedAt:      now,
			UpdatedAt:      now,
		},
	}
	if err := db.Create(&conversation).Error; err != nil {
		t.Fatalf("create conversation: %v", err)
	}

	createReq := createSkillRequest{
		Name:        "release-check",
		Description: "Release checklist",
		Category:    "coding",
		Content:     "# Release Checklist\n\n1. Run tests.\n2. Verify rollback plan.\n",
	}
	if err := createParentSkill(context.Background(), db.DB, "u1", "User 1", createReq); err != nil {
		t.Fatalf("create parent skill: %v", err)
	}

	var row orm.SkillResource
	relativePath := evolution.ParentSkillRelativePath("coding", "release-check")
	if err := db.Where("owner_user_id = ? AND relative_path = ?", "u1", relativePath).Take(&row).Error; err != nil {
		t.Fatalf("query created skill: %v", err)
	}
	snapshot := orm.ResourceSessionSnapshot{
		ID:              "snapshot-remove",
		SessionID:       "conv-remove_1",
		UserID:          "u1",
		ResourceType:    evolution.ResourceTypeSkill,
		ResourceKey:     relativePath,
		Category:        "coding",
		ParentSkillName: "release-check",
		SkillName:       "release-check",
		FileExt:         "md",
		RelativePath:    relativePath,
		SnapshotHash:    row.ContentHash,
		CreatedAt:       now,
	}
	if err := db.Create(&snapshot).Error; err != nil {
		t.Fatalf("create snapshot: %v", err)
	}

	body, err := json.Marshal(map[string]string{
		"session_id": "conv-remove_1",
		"category":   "coding",
		"skill_name": "release-check",
	})
	if err != nil {
		t.Fatalf("marshal body: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/skill/remove", strings.NewReader(string(body)))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()

	Remove(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	var resp struct {
		Code int `json:"code"`
		Data struct {
			Deleted bool `json:"deleted"`
		} `json:"data"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Code != 0 || !resp.Data.Deleted {
		t.Fatalf("expected deleted response, got %+v", resp)
	}

	var skillCount int64
	if err := db.Model(&orm.SkillResource{}).Where("id = ?", row.ID).Count(&skillCount).Error; err != nil {
		t.Fatalf("count skills: %v", err)
	}
	if skillCount != 0 {
		t.Fatalf("expected skill to be deleted, got %d rows", skillCount)
	}

	var suggestionCount int64
	if err := db.Model(&orm.ResourceSuggestion{}).Count(&suggestionCount).Error; err != nil {
		t.Fatalf("count suggestions: %v", err)
	}
	if suggestionCount != 0 {
		t.Fatalf("expected no resource suggestions, got %d", suggestionCount)
	}

}

func TestGenerateReturnsOutdatedWhenApprovedSuggestionSnapshotIsStale(t *testing.T) {
	db := newSkillTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/chat/skill/generate" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"data": map[string]any{
				"content": "---\nname: git-workflow\ndescription: git workflow\n---\nupdated body",
			},
		})
	})
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Skipf("listener unavailable in current test environment: %v", err)
	}
	algoServer := &http.Server{Handler: handler}
	go func() {
		_ = algoServer.Serve(listener)
	}()
	defer func() {
		_ = algoServer.Shutdown(context.Background())
	}()
	t.Setenv("LAZYRAG_CHAT_SERVICE_URL", fmt.Sprintf("http://%s", listener.Addr().String()))

	relativePath := evolution.ParentSkillRelativePath("coding", "git-workflow")
	currentContent := "---\nname: git-workflow\ndescription: git workflow\n---\ncurrent body"

	now := time.Now()
	skillRow := orm.SkillResource{
		ID:              "skill-1",
		OwnerUserID:     "u1",
		OwnerUserName:   "User 1",
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "git-workflow",
		NodeType:        evolution.SkillNodeTypeParent,
		FileExt:         "md",
		RelativePath:    relativePath,
		Content:         currentContent,
		ContentSize:     int64(len([]byte(currentContent))),
		MimeType:        "text/markdown; charset=utf-8",
		ContentHash:     evolution.HashContent(currentContent),
		Version:         1,
		DraftContent:    "old draft body",
		DraftStatus:     "pending_confirm",
		IsEnabled:       true,
		UpdateStatus:    evolution.UpdateStatusUpToDate,
		CreateUserID:    "u1",
		CreateUserName:  "User 1",
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	if err := db.Create(&skillRow).Error; err != nil {
		t.Fatalf("create skill: %v", err)
	}

	suggestion := orm.ResourceSuggestion{
		ID:              "suggestion-1",
		UserID:          "u1",
		ResourceType:    evolution.ResourceTypeSkill,
		ResourceKey:     relativePath,
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "git-workflow",
		FileExt:         "md",
		RelativePath:    relativePath,
		Action:          evolution.SuggestionActionModify,
		SessionID:       "session-1",
		SnapshotHash:    evolution.HashContent("older body"),
		Title:           "update workflow",
		Content:         "update skill body",
		Status:          evolution.SuggestionStatusAccepted,
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	if err := db.Create(&suggestion).Error; err != nil {
		t.Fatalf("create suggestion: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/core/skills/skill-1:generate", strings.NewReader(`{"suggestion_ids":["suggestion-1"],"user_instruct":"请生成新版"}`))
	req = mux.SetURLVars(req, map[string]string{"skill_id": "skill-1"})
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	Generate(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	var resp generateSkillAPITestResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Code != 0 {
		t.Fatalf("expected code 0, got %d message=%s", resp.Code, resp.Message)
	}
	if resp.Data.DraftStatus != "pending_confirm" {
		t.Fatalf("expected pending_confirm draft status, got %q", resp.Data.DraftStatus)
	}
	if !resp.Data.Outdated {
		t.Fatalf("expected outdated=true")
	}
	var updatedSkill orm.SkillResource
	if err := db.Where("id = ?", "skill-1").Take(&updatedSkill).Error; err != nil {
		t.Fatalf("query updated skill: %v", err)
	}
	if !strings.Contains(updatedSkill.DraftContent, "updated body") {
		t.Fatalf("expected draft_content to be overwritten, got %q", updatedSkill.DraftContent)
	}
}

func TestGenerateAllowsUserInstructWithoutSuggestions(t *testing.T) {
	db := newSkillTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	var algoBody map[string]any
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/chat/skill/generate" {
			http.NotFound(w, r)
			return
		}
		if err := json.NewDecoder(r.Body).Decode(&algoBody); err != nil {
			t.Fatalf("decode algorithm request: %v", err)
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"data": map[string]any{
				"content": "---\nname: git-workflow\ndescription: git workflow\n---\nupdated body",
			},
		})
	})
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Skipf("listener unavailable in current test environment: %v", err)
	}
	algoServer := &http.Server{Handler: handler}
	go func() { _ = algoServer.Serve(listener) }()
	defer func() { _ = algoServer.Shutdown(context.Background()) }()
	t.Setenv("LAZYRAG_CHAT_SERVICE_URL", fmt.Sprintf("http://%s", listener.Addr().String()))

	relativePath := evolution.ParentSkillRelativePath("coding", "git-workflow")
	currentContent := "---\nname: git-workflow\ndescription: git workflow\n---\ncurrent body"
	now := time.Now()
	skillRow := orm.SkillResource{
		ID:             "skill-1",
		OwnerUserID:    "u1",
		OwnerUserName:  "User 1",
		Category:       "coding",
		SkillName:      "git-workflow",
		NodeType:       evolution.SkillNodeTypeParent,
		Description:    "git workflow",
		FileExt:        "md",
		RelativePath:   relativePath,
		Content:        currentContent,
		ContentSize:    int64(len([]byte(currentContent))),
		MimeType:       "text/markdown; charset=utf-8",
		ContentHash:    evolution.HashContent(currentContent),
		Version:        1,
		IsEnabled:      true,
		UpdateStatus:   evolution.UpdateStatusUpToDate,
		CreateUserID:   "u1",
		CreateUserName: "User 1",
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	if err := db.Create(&skillRow).Error; err != nil {
		t.Fatalf("create skill: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/core/skills/skill-1:generate", strings.NewReader(`{"suggestion_ids":[],"user_instruct":"只按用户意见生成"}`))
	req = mux.SetURLVars(req, map[string]string{"skill_id": "skill-1"})
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	Generate(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	if algoBody["user_instruct"] != "只按用户意见生成" {
		t.Fatalf("unexpected user_instruct sent to algorithm: %#v", algoBody["user_instruct"])
	}
	if _, ok := algoBody["category"]; ok {
		t.Fatalf("category should not be sent to algorithm: %#v", algoBody["category"])
	}
	if _, ok := algoBody["skill_name"]; ok {
		t.Fatalf("skill_name should not be sent to algorithm: %#v", algoBody["skill_name"])
	}
	suggestions, ok := algoBody["suggestions"].([]any)
	if !ok || len(suggestions) != 0 {
		t.Fatalf("expected empty suggestions array, got %#v", algoBody["suggestions"])
	}
}

func TestGenerateAllowsGeneratedDescriptionChange(t *testing.T) {
	db := newSkillTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/chat/skill/generate" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"data": map[string]any{
				"content": "---\nname: git-workflow\ndescription: expanded git workflow\n---\nupdated body",
			},
		})
	})
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Skipf("listener unavailable in current test environment: %v", err)
	}
	algoServer := &http.Server{Handler: handler}
	go func() { _ = algoServer.Serve(listener) }()
	defer func() { _ = algoServer.Shutdown(context.Background()) }()
	t.Setenv("LAZYRAG_CHAT_SERVICE_URL", fmt.Sprintf("http://%s", listener.Addr().String()))

	relativePath := evolution.ParentSkillRelativePath("coding", "git-workflow")
	currentContent := "---\nname: git-workflow\ndescription: git workflow\n---\ncurrent body"
	now := time.Now()
	skillRow := orm.SkillResource{
		ID:             "skill-1",
		OwnerUserID:    "u1",
		OwnerUserName:  "User 1",
		Category:       "coding",
		SkillName:      "git-workflow",
		NodeType:       evolution.SkillNodeTypeParent,
		Description:    "git workflow",
		FileExt:        "md",
		RelativePath:   relativePath,
		Content:        currentContent,
		ContentSize:    int64(len([]byte(currentContent))),
		MimeType:       "text/markdown; charset=utf-8",
		ContentHash:    evolution.HashContent(currentContent),
		Version:        1,
		IsEnabled:      true,
		UpdateStatus:   evolution.UpdateStatusUpToDate,
		CreateUserID:   "u1",
		CreateUserName: "User 1",
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	if err := db.Create(&skillRow).Error; err != nil {
		t.Fatalf("create skill: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/core/skills/skill-1:generate", strings.NewReader(`{"user_instruct":"扩展技能适用范围"}`))
	req = mux.SetURLVars(req, map[string]string{"skill_id": "skill-1"})
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	Generate(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	var updatedSkill orm.SkillResource
	if err := db.Where("id = ?", "skill-1").Take(&updatedSkill).Error; err != nil {
		t.Fatalf("query updated skill: %v", err)
	}
	if !strings.Contains(updatedSkill.DraftContent, "description: expanded git workflow") {
		t.Fatalf("expected generated description in draft_content, got %q", updatedSkill.DraftContent)
	}
	if updatedSkill.Description != "git workflow" {
		t.Fatalf("generate should not persist description before confirm, got %q", updatedSkill.Description)
	}
}

func TestConfirmPersistsDraftFrontmatterDescription(t *testing.T) {
	db := newSkillTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	relativePath := evolution.ParentSkillRelativePath("coding", "git-workflow")
	currentContent := "---\nname: git-workflow\ndescription: git workflow\n---\ncurrent body"
	draftContent := "---\nname: git-workflow\ndescription: expanded git workflow\n---\nupdated body"
	now := time.Now()
	skillRow := orm.SkillResource{
		ID:                 "skill-1",
		OwnerUserID:        "u1",
		OwnerUserName:      "User 1",
		Category:           "coding",
		ParentSkillName:    "git-workflow",
		SkillName:          "git-workflow",
		NodeType:           evolution.SkillNodeTypeParent,
		Description:        "git workflow",
		FileExt:            "md",
		RelativePath:       relativePath,
		Content:            currentContent,
		ContentSize:        int64(len([]byte(currentContent))),
		MimeType:           "text/markdown; charset=utf-8",
		ContentHash:        evolution.HashContent(currentContent),
		Version:            2,
		DraftContent:       draftContent,
		DraftSourceVersion: 2,
		DraftStatus:        "pending_confirm",
		IsEnabled:          true,
		UpdateStatus:       "pending_confirm",
		CreateUserID:       "u1",
		CreateUserName:     "User 1",
		CreatedAt:          now,
		UpdatedAt:          now,
	}
	if err := db.Create(&skillRow).Error; err != nil {
		t.Fatalf("create skill: %v", err)
	}

	req := httptest.NewRequest(http.MethodPost, "/api/core/skills/skill-1:confirm", nil)
	req = mux.SetURLVars(req, map[string]string{"skill_id": "skill-1"})
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	Confirm(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}
	var updatedSkill orm.SkillResource
	if err := db.Where("id = ?", "skill-1").Take(&updatedSkill).Error; err != nil {
		t.Fatalf("query updated skill: %v", err)
	}
	if updatedSkill.Description != "expanded git workflow" {
		t.Fatalf("expected confirmed description to persist, got %q", updatedSkill.Description)
	}
	if updatedSkill.Content != draftContent {
		t.Fatalf("expected content to be confirmed, got %q", updatedSkill.Content)
	}
	if updatedSkill.DraftStatus != "" {
		t.Fatalf("expected draft status to be cleared, got %q", updatedSkill.DraftStatus)
	}
}

func TestDraftPreviewReturnsCurrentDraftAndDiff(t *testing.T) {
	db := newSkillTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	relativePath := evolution.ParentSkillRelativePath("coding", "git-workflow")
	currentContent := "---\nname: git-workflow\ndescription: git workflow\n---\ncurrent body\n"
	draftContent := "---\nname: git-workflow\ndescription: git workflow\n---\nupdated body\n"

	now := time.Now()
	skillRow := orm.SkillResource{
		ID:                 "skill-1",
		OwnerUserID:        "u1",
		OwnerUserName:      "User 1",
		Category:           "coding",
		ParentSkillName:    "git-workflow",
		SkillName:          "git-workflow",
		NodeType:           evolution.SkillNodeTypeParent,
		FileExt:            "md",
		RelativePath:       relativePath,
		Content:            currentContent,
		ContentSize:        int64(len([]byte(currentContent))),
		MimeType:           "text/markdown; charset=utf-8",
		ContentHash:        evolution.HashContent(currentContent),
		Version:            2,
		DraftContent:       draftContent,
		DraftSourceVersion: 2,
		DraftStatus:        "pending_confirm",
		IsEnabled:          true,
		UpdateStatus:       "pending_confirm",
		CreateUserID:       "u1",
		CreateUserName:     "User 1",
		CreatedAt:          now,
		UpdatedAt:          now,
	}

	suggestion := orm.ResourceSuggestion{
		ID:              "suggestion-1",
		UserID:          "u1",
		ResourceType:    evolution.ResourceTypeSkill,
		ResourceKey:     relativePath,
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "git-workflow",
		FileExt:         "md",
		RelativePath:    relativePath,
		Action:          evolution.SuggestionActionModify,
		SessionID:       "session-1",
		SnapshotHash:    evolution.HashContent("older body"),
		Title:           "update workflow",
		Content:         "update skill body",
		Status:          evolution.SuggestionStatusAccepted,
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	skillRow.Ext = evolution.WithDraftSuggestionIDs(nil, []string{suggestion.ID})

	if err := db.Create(&skillRow).Error; err != nil {
		t.Fatalf("create skill: %v", err)
	}
	if err := db.Create(&suggestion).Error; err != nil {
		t.Fatalf("create suggestion: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/api/core/skills/skill-1:draft-preview", nil)
	req = mux.SetURLVars(req, map[string]string{"skill_id": "skill-1"})
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	DraftPreview(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	var resp draftPreviewAPITestResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Code != 0 {
		t.Fatalf("expected code 0, got %d message=%s", resp.Code, resp.Message)
	}
	if resp.Data.SkillID != "skill-1" {
		t.Fatalf("expected skill_id skill-1, got %q", resp.Data.SkillID)
	}
	if resp.Data.DraftStatus != "pending_confirm" {
		t.Fatalf("expected pending_confirm, got %q", resp.Data.DraftStatus)
	}
	if resp.Data.DraftSourceVersion != 2 {
		t.Fatalf("expected draft_source_version 2, got %d", resp.Data.DraftSourceVersion)
	}
	if resp.Data.CurrentContent != currentContent {
		t.Fatalf("unexpected current content: %q", resp.Data.CurrentContent)
	}
	if resp.Data.DraftContent != draftContent {
		t.Fatalf("unexpected draft content: %q", resp.Data.DraftContent)
	}
	if !strings.Contains(resp.Data.Diff, "-current body") {
		t.Fatalf("expected diff to contain removed current line, got %q", resp.Data.Diff)
	}
	if !strings.Contains(resp.Data.Diff, "+updated body") {
		t.Fatalf("expected diff to contain added draft line, got %q", resp.Data.Diff)
	}
	if !resp.Data.Outdated {
		t.Fatalf("expected outdated=true")
	}
}

func TestListMarksSkillsWithPendingReviewSuggestions(t *testing.T) {
	db := newSkillTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	now := time.Now()
	parentWithPending := orm.SkillResource{
		ID:              "skill-parent-pending",
		OwnerUserID:     "u1",
		OwnerUserName:   "User 1",
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "git-workflow",
		NodeType:        evolution.SkillNodeTypeParent,
		FileExt:         "md",
		RelativePath:    evolution.ParentSkillRelativePath("coding", "git-workflow"),
		ContentHash:     evolution.HashContent("content-1"),
		Version:         1,
		IsEnabled:       true,
		UpdateStatus:    evolution.UpdateStatusUpToDate,
		CreateUserID:    "u1",
		CreateUserName:  "User 1",
		CreatedAt:       now,
		UpdatedAt:       now.Add(2 * time.Second),
	}
	childWithPending := orm.SkillResource{
		ID:              "skill-child-pending",
		OwnerUserID:     "u1",
		OwnerUserName:   "User 1",
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "rules",
		NodeType:        evolution.SkillNodeTypeChild,
		FileExt:         "md",
		RelativePath:    "coding/git-workflow/rules.md",
		ContentHash:     evolution.HashContent("child-content"),
		Version:         1,
		IsEnabled:       true,
		UpdateStatus:    evolution.UpdateStatusUpToDate,
		CreateUserID:    "u1",
		CreateUserName:  "User 1",
		CreatedAt:       now.Add(500 * time.Millisecond),
		UpdatedAt:       now.Add(2 * time.Second),
	}
	parentAcceptedOnly := orm.SkillResource{
		ID:              "skill-parent-approved",
		OwnerUserID:     "u1",
		OwnerUserName:   "User 1",
		Category:        "coding",
		ParentSkillName: "release-check",
		SkillName:       "release-check",
		NodeType:        evolution.SkillNodeTypeParent,
		FileExt:         "md",
		RelativePath:    evolution.ParentSkillRelativePath("coding", "release-check"),
		ContentHash:     evolution.HashContent("content-2"),
		Version:         1,
		IsEnabled:       true,
		UpdateStatus:    evolution.UpdateStatusUpToDate,
		CreateUserID:    "u1",
		CreateUserName:  "User 1",
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	if err := db.Create(&parentWithPending).Error; err != nil {
		t.Fatalf("create pending parent: %v", err)
	}
	if err := db.Create(&childWithPending).Error; err != nil {
		t.Fatalf("create pending child: %v", err)
	}
	if err := db.Create(&parentAcceptedOnly).Error; err != nil {
		t.Fatalf("create accepted-only parent: %v", err)
	}

	suggestions := []orm.ResourceSuggestion{
		{
			ID:              "suggestion-pending",
			UserID:          "u1",
			ResourceType:    evolution.ResourceTypeSkill,
			ResourceKey:     parentWithPending.RelativePath,
			Category:        "coding",
			ParentSkillName: "git-workflow",
			SkillName:       "git-workflow",
			FileExt:         "md",
			RelativePath:    parentWithPending.RelativePath,
			Action:          evolution.SuggestionActionModify,
			SessionID:       "session-pending",
			Title:           "pending suggestion",
			Content:         "please review this change",
			Status:          evolution.SuggestionStatusPendingReview,
			CreatedAt:       now,
			UpdatedAt:       now,
		},
		{
			ID:              "suggestion-accepted",
			UserID:          "u1",
			ResourceType:    evolution.ResourceTypeSkill,
			ResourceKey:     parentAcceptedOnly.RelativePath,
			Category:        "coding",
			ParentSkillName: "release-check",
			SkillName:       "release-check",
			FileExt:         "md",
			RelativePath:    parentAcceptedOnly.RelativePath,
			Action:          evolution.SuggestionActionModify,
			SessionID:       "session-accepted",
			Title:           "accepted suggestion",
			Content:         "already reviewed",
			Status:          evolution.SuggestionStatusAccepted,
			CreatedAt:       now,
			UpdatedAt:       now,
		},
	}
	if err := db.Create(&suggestions).Error; err != nil {
		t.Fatalf("create suggestions: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/api/core/skills?page=1&page_size=20", nil)
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	List(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	var resp listSkillsAPITestResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Code != 0 {
		t.Fatalf("expected code 0, got %d message=%s", resp.Code, resp.Message)
	}
	if resp.Data.Total != 2 {
		t.Fatalf("expected total 2, got %d", resp.Data.Total)
	}

	itemsByID := make(map[string]struct {
		hasPending       bool
		suggestionStatus string
		children         map[string]struct {
			hasPending       bool
			suggestionStatus string
		}
	}, len(resp.Data.Items))
	for _, item := range resp.Data.Items {
		childMap := make(map[string]struct {
			hasPending       bool
			suggestionStatus string
		}, len(item.Children))
		for _, child := range item.Children {
			childMap[child.SkillID] = struct {
				hasPending       bool
				suggestionStatus string
			}{
				hasPending:       child.HasPendingReviewSuggestions,
				suggestionStatus: child.SuggestionStatus,
			}
		}
		itemsByID[item.SkillID] = struct {
			hasPending       bool
			suggestionStatus string
			children         map[string]struct {
				hasPending       bool
				suggestionStatus string
			}
		}{
			hasPending:       item.HasPendingReviewSuggestions,
			suggestionStatus: item.SuggestionStatus,
			children:         childMap,
		}
	}

	if !itemsByID[parentWithPending.ID].hasPending {
		t.Fatalf("expected parent with pending suggestion to be marked")
	}
	if itemsByID[parentWithPending.ID].suggestionStatus != evolution.SuggestionStatusPendingReview {
		t.Fatalf("expected parent suggestion_status pending_review, got %q", itemsByID[parentWithPending.ID].suggestionStatus)
	}
	if !itemsByID[parentWithPending.ID].children[childWithPending.ID].hasPending {
		t.Fatalf("expected child to inherit pending suggestion mark")
	}
	if itemsByID[parentWithPending.ID].children[childWithPending.ID].suggestionStatus != evolution.SuggestionStatusPendingReview {
		t.Fatalf("expected child suggestion_status pending_review, got %q", itemsByID[parentWithPending.ID].children[childWithPending.ID].suggestionStatus)
	}
	if !itemsByID[parentAcceptedOnly.ID].hasPending {
		t.Fatalf("expected accepted-only parent to be marked as having active suggestion")
	}
	if itemsByID[parentAcceptedOnly.ID].suggestionStatus != evolution.SuggestionStatusAccepted {
		t.Fatalf("expected accepted-only parent suggestion_status accepted, got %q", itemsByID[parentAcceptedOnly.ID].suggestionStatus)
	}
}

func TestListMarksSkillsWithLegacyPendingSuggestionsWithoutResourceKey(t *testing.T) {
	db := newSkillTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	now := time.Now()
	parent := orm.SkillResource{
		ID:              "skill-parent-legacy",
		OwnerUserID:     "u1",
		OwnerUserName:   "User 1",
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "git-workflow",
		NodeType:        evolution.SkillNodeTypeParent,
		FileExt:         "md",
		RelativePath:    evolution.ParentSkillRelativePath("coding", "git-workflow"),
		ContentHash:     evolution.HashContent("content-1"),
		Version:         1,
		IsEnabled:       true,
		UpdateStatus:    evolution.UpdateStatusUpToDate,
		CreateUserID:    "u1",
		CreateUserName:  "User 1",
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	child := orm.SkillResource{
		ID:              "skill-child-legacy",
		OwnerUserID:     "u1",
		OwnerUserName:   "User 1",
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "rules",
		NodeType:        evolution.SkillNodeTypeChild,
		FileExt:         "md",
		RelativePath:    "coding/git-workflow/rules.md",
		ContentHash:     evolution.HashContent("child-content"),
		Version:         1,
		IsEnabled:       true,
		UpdateStatus:    evolution.UpdateStatusUpToDate,
		CreateUserID:    "u1",
		CreateUserName:  "User 1",
		CreatedAt:       now.Add(500 * time.Millisecond),
		UpdatedAt:       now,
	}
	if err := db.Create(&parent).Error; err != nil {
		t.Fatalf("create parent: %v", err)
	}
	if err := db.Create(&child).Error; err != nil {
		t.Fatalf("create child: %v", err)
	}

	legacySuggestion := orm.ResourceSuggestion{
		ID:              "suggestion-legacy-pending",
		UserID:          "u1",
		ResourceType:    evolution.ResourceTypeSkill,
		ResourceKey:     "",
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "git-workflow",
		FileExt:         "md",
		RelativePath:    "",
		Action:          evolution.SuggestionActionModify,
		SessionID:       "session-legacy-pending",
		Title:           "legacy pending suggestion",
		Content:         "legacy change",
		Status:          evolution.SuggestionStatusPendingReview,
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	if err := db.Create(&legacySuggestion).Error; err != nil {
		t.Fatalf("create legacy suggestion: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/api/core/skills?page=1&page_size=20", nil)
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	List(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	var resp listSkillsAPITestResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Code != 0 {
		t.Fatalf("expected code 0, got %d message=%s", resp.Code, resp.Message)
	}
	if len(resp.Data.Items) != 1 {
		t.Fatalf("expected 1 item, got %d", len(resp.Data.Items))
	}
	item := resp.Data.Items[0]
	if !item.HasPendingReviewSuggestions {
		t.Fatalf("expected parent to be marked by legacy suggestion")
	}
	if item.SuggestionStatus != evolution.SuggestionStatusPendingReview {
		t.Fatalf("expected parent suggestion_status pending_review, got %q", item.SuggestionStatus)
	}
	if len(item.Children) != 1 {
		t.Fatalf("expected 1 child, got %d", len(item.Children))
	}
	if !item.Children[0].HasPendingReviewSuggestions {
		t.Fatalf("expected child to inherit legacy pending suggestion mark")
	}
	if item.Children[0].SuggestionStatus != evolution.SuggestionStatusPendingReview {
		t.Fatalf("expected child suggestion_status pending_review, got %q", item.Children[0].SuggestionStatus)
	}
}

func TestGetChildDetailInheritsPendingReviewSuggestionsFromParent(t *testing.T) {
	db := newSkillTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	parentRelativePath := evolution.ParentSkillRelativePath("coding", "git-workflow")
	childRelativePath := "coding/git-workflow/rules.md"
	parentContent := "---\nname: git-workflow\ndescription: git workflow\n---\nparent body"
	childContent := "child body"

	now := time.Now()
	parent := orm.SkillResource{
		ID:              "skill-parent",
		OwnerUserID:     "u1",
		OwnerUserName:   "User 1",
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "git-workflow",
		NodeType:        evolution.SkillNodeTypeParent,
		FileExt:         "md",
		RelativePath:    parentRelativePath,
		Content:         parentContent,
		ContentSize:     int64(len([]byte(parentContent))),
		MimeType:        "text/markdown; charset=utf-8",
		ContentHash:     evolution.HashContent(parentContent),
		Version:         1,
		IsEnabled:       true,
		UpdateStatus:    evolution.UpdateStatusUpToDate,
		CreateUserID:    "u1",
		CreateUserName:  "User 1",
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	child := orm.SkillResource{
		ID:              "skill-child",
		OwnerUserID:     "u1",
		OwnerUserName:   "User 1",
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "rules",
		NodeType:        evolution.SkillNodeTypeChild,
		FileExt:         "md",
		RelativePath:    childRelativePath,
		Content:         childContent,
		ContentSize:     int64(len([]byte(childContent))),
		MimeType:        "text/markdown; charset=utf-8",
		ContentHash:     evolution.HashContent(childContent),
		Version:         1,
		IsEnabled:       true,
		UpdateStatus:    evolution.UpdateStatusUpToDate,
		CreateUserID:    "u1",
		CreateUserName:  "User 1",
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	suggestion := orm.ResourceSuggestion{
		ID:              "suggestion-pending-child-detail",
		UserID:          "u1",
		ResourceType:    evolution.ResourceTypeSkill,
		ResourceKey:     parentRelativePath,
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "git-workflow",
		FileExt:         "md",
		RelativePath:    parentRelativePath,
		Action:          evolution.SuggestionActionModify,
		SessionID:       "session-child-detail",
		Title:           "pending suggestion",
		Content:         "please review",
		Status:          evolution.SuggestionStatusPendingReview,
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	if err := db.Create(&parent).Error; err != nil {
		t.Fatalf("create parent: %v", err)
	}
	if err := db.Create(&child).Error; err != nil {
		t.Fatalf("create child: %v", err)
	}
	if err := db.Create(&suggestion).Error; err != nil {
		t.Fatalf("create suggestion: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/api/core/skills/skill-child", nil)
	req = mux.SetURLVars(req, map[string]string{"skill_id": child.ID})
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	Get(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	var resp getSkillDetailAPITestResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.Code != 0 {
		t.Fatalf("expected code 0, got %d message=%s", resp.Code, resp.Message)
	}
	if resp.Data.SkillID != child.ID {
		t.Fatalf("expected child skill id %q, got %q", child.ID, resp.Data.SkillID)
	}
	if !resp.Data.HasPendingReviewSuggestions {
		t.Fatalf("expected child detail to inherit pending review suggestion flag")
	}
	if resp.Data.SuggestionStatus != evolution.SuggestionStatusPendingReview {
		t.Fatalf("expected child detail suggestion_status pending_review, got %q", resp.Data.SuggestionStatus)
	}
	if len(resp.Data.Children) != 0 {
		t.Fatalf("expected child detail to have no children, got %d", len(resp.Data.Children))
	}
}

func TestCreateParentSkillBuildsFrontmatterFromBodyOnlyContent(t *testing.T) {
	db := newSkillTestDB(t)

	req := createSkillRequest{
		Name:        "git-workflow",
		Description: "Git workflow for postman test",
		Category:    "coding",
		Content:     "# Git Workflow\n\nKeep commit history clean and easy to review.",
		IsLocked:    true,
	}
	if err := createParentSkill(context.Background(), db.DB, "u1", "User 1", req); err != nil {
		t.Fatalf("create parent skill: %v", err)
	}

	var row orm.SkillResource
	if err := db.Where("owner_user_id = ? AND node_type = ?", "u1", evolution.SkillNodeTypeParent).Take(&row).Error; err != nil {
		t.Fatalf("query parent skill: %v", err)
	}

	expectedContent := "---\nname: git-workflow\ndescription: Git workflow for postman test\n---\n# Git Workflow\n\nKeep commit history clean and easy to review."
	if row.SkillName != "git-workflow" {
		t.Fatalf("expected skill name git-workflow, got %q", row.SkillName)
	}
	if row.Description != "Git workflow for postman test" {
		t.Fatalf("expected description to be persisted, got %q", row.Description)
	}
	if row.RelativePath != evolution.ParentSkillRelativePath("coding", "git-workflow") {
		t.Fatalf("unexpected relative path: %q", row.RelativePath)
	}
	if row.ContentHash != evolution.HashContent(expectedContent) {
		t.Fatalf("expected content hash to use rebuilt content")
	}

	if row.Content != expectedContent {
		t.Fatalf("unexpected DB content: %q", row.Content)
	}
}

func TestUpdateParentSkillRebuildsContentFromBodyOnlyPayload(t *testing.T) {
	db := newSkillTestDB(t)

	createReq := createSkillRequest{
		Name:        "git-workflow",
		Description: "Git workflow for postman test",
		Category:    "coding",
		Content:     "# Git Workflow\n\nKeep commit history clean and easy to review.",
	}
	if err := createParentSkill(context.Background(), db.DB, "u1", "User 1", createReq); err != nil {
		t.Fatalf("create parent skill: %v", err)
	}

	var row orm.SkillResource
	if err := db.Where("owner_user_id = ? AND node_type = ?", "u1", evolution.SkillNodeTypeParent).Take(&row).Error; err != nil {
		t.Fatalf("query parent skill: %v", err)
	}

	updateReq := updateSkillRequest{
		Description: stringPtr("Updated git workflow"),
		Content:     stringPtr("# Git Workflow\n\nUse small, reviewable commits."),
	}
	if err := updateSkill(context.Background(), db.DB, "u1", "User 1", row.ID, updateReq); err != nil {
		t.Fatalf("update parent skill: %v", err)
	}

	var updated orm.SkillResource
	if err := db.Where("id = ?", row.ID).Take(&updated).Error; err != nil {
		t.Fatalf("query updated parent skill: %v", err)
	}

	expectedContent := "---\nname: git-workflow\ndescription: Updated git workflow\n---\n# Git Workflow\n\nUse small, reviewable commits."
	if updated.SkillName != "git-workflow" {
		t.Fatalf("expected skill name to stay git-workflow, got %q", updated.SkillName)
	}
	if updated.Description != "Updated git workflow" {
		t.Fatalf("expected updated description, got %q", updated.Description)
	}
	if updated.Content != expectedContent {
		t.Fatalf("unexpected updated DB content: %q", updated.Content)
	}
}

func TestUpdateParentSkillRenameMovesChildrenAndRebuildsFrontmatter(t *testing.T) {
	db := newSkillTestDB(t)

	createReq := createSkillRequest{
		Name:        "git-workflow",
		Description: "Git workflow for postman test",
		Category:    "coding",
		Content:     "# Git Workflow\n\nKeep commit history clean and easy to review.",
		Children: []childSkillInput{
			{
				Name:     "rules",
				Content:  "1. Create a feature branch.\n2. Rebase before merging.",
				FileExt:  "md",
				IsLocked: true,
			},
		},
	}
	if err := createParentSkill(context.Background(), db.DB, "u1", "User 1", createReq); err != nil {
		t.Fatalf("create parent skill with child: %v", err)
	}

	var parent orm.SkillResource
	if err := db.Where("owner_user_id = ? AND node_type = ?", "u1", evolution.SkillNodeTypeParent).Take(&parent).Error; err != nil {
		t.Fatalf("query parent skill: %v", err)
	}
	var child orm.SkillResource
	if err := db.Where("owner_user_id = ? AND node_type = ?", "u1", evolution.SkillNodeTypeChild).Take(&child).Error; err != nil {
		t.Fatalf("query child skill: %v", err)
	}
	updateReq := updateSkillRequest{
		Name:        stringPtr("git-workflow-renamed"),
		Description: stringPtr("Renamed git workflow"),
	}
	if err := updateSkill(context.Background(), db.DB, "u1", "User 1", parent.ID, updateReq); err != nil {
		t.Fatalf("rename parent skill: %v", err)
	}

	var updatedParent orm.SkillResource
	if err := db.Where("id = ?", parent.ID).Take(&updatedParent).Error; err != nil {
		t.Fatalf("query renamed parent skill: %v", err)
	}
	var updatedChild orm.SkillResource
	if err := db.Where("id = ?", child.ID).Take(&updatedChild).Error; err != nil {
		t.Fatalf("query renamed child skill: %v", err)
	}

	expectedParentContent := "---\nname: git-workflow-renamed\ndescription: Renamed git workflow\n---\n# Git Workflow\n\nKeep commit history clean and easy to review."
	if updatedParent.Content != expectedParentContent {
		t.Fatalf("unexpected renamed parent content: %q", updatedParent.Content)
	}
	if updatedParent.SkillName != "git-workflow-renamed" {
		t.Fatalf("expected parent skill to be renamed, got %q", updatedParent.SkillName)
	}
	if updatedParent.RelativePath != evolution.ParentSkillRelativePath("coding", "git-workflow-renamed") {
		t.Fatalf("unexpected renamed parent relative path: %q", updatedParent.RelativePath)
	}

	expectedChildRelativePath := filepath.ToSlash(filepath.Join("coding", "git-workflow-renamed", "rules.md"))
	if updatedChild.ParentSkillName != "git-workflow-renamed" {
		t.Fatalf("expected child parent skill name to update, got %q", updatedChild.ParentSkillName)
	}
	if updatedChild.RelativePath != expectedChildRelativePath {
		t.Fatalf("unexpected child relative path: %q", updatedChild.RelativePath)
	}
}

func TestDeleteChildSkillRemovesRecordOnly(t *testing.T) {
	db := newSkillTestDB(t)

	createReq := createSkillRequest{
		Name:        "git-workflow",
		Description: "Git workflow for postman test",
		Category:    "coding",
		Content:     "# Git Workflow\n\nKeep commit history clean and easy to review.",
		Children: []childSkillInput{
			{
				Name:    "rules",
				Content: "1. Create a feature branch.",
				FileExt: "md",
			},
		},
	}
	if err := createParentSkill(context.Background(), db.DB, "u1", "User 1", createReq); err != nil {
		t.Fatalf("create parent skill with child: %v", err)
	}

	var parent orm.SkillResource
	if err := db.Where("owner_user_id = ? AND node_type = ?", "u1", evolution.SkillNodeTypeParent).Take(&parent).Error; err != nil {
		t.Fatalf("query parent skill: %v", err)
	}
	var child orm.SkillResource
	if err := db.Where("owner_user_id = ? AND node_type = ?", "u1", evolution.SkillNodeTypeChild).Take(&child).Error; err != nil {
		t.Fatalf("query child skill: %v", err)
	}

	if err := deleteSkill(context.Background(), db.DB, "u1", child.ID); err != nil {
		t.Fatalf("delete child skill: %v", err)
	}

	if err := db.Where("id = ?", child.ID).Take(&orm.SkillResource{}).Error; !errors.Is(err, gorm.ErrRecordNotFound) {
		t.Fatalf("expected child record to be deleted, got err=%v", err)
	}
	if err := db.Where("id = ?", parent.ID).Take(&orm.SkillResource{}).Error; err != nil {
		t.Fatalf("expected parent record to remain, got err=%v", err)
	}
}

func TestDeleteParentSkillRemovesChildrenRecords(t *testing.T) {
	db := newSkillTestDB(t)

	createReq := createSkillRequest{
		Name:        "git-workflow",
		Description: "Git workflow for postman test",
		Category:    "coding",
		Content:     "# Git Workflow\n\nKeep commit history clean and easy to review.",
		Children: []childSkillInput{
			{
				Name:    "rules",
				Content: "1. Create a feature branch.",
				FileExt: "md",
			},
			{
				Name:    "checklist",
				Content: "- Rebase before merging.",
				FileExt: "md",
			},
		},
	}
	if err := createParentSkill(context.Background(), db.DB, "u1", "User 1", createReq); err != nil {
		t.Fatalf("create parent skill with children: %v", err)
	}

	var parent orm.SkillResource
	if err := db.Where("owner_user_id = ? AND node_type = ?", "u1", evolution.SkillNodeTypeParent).Take(&parent).Error; err != nil {
		t.Fatalf("query parent skill: %v", err)
	}
	var children []orm.SkillResource
	if err := db.Where("owner_user_id = ? AND node_type = ?", "u1", evolution.SkillNodeTypeChild).Find(&children).Error; err != nil {
		t.Fatalf("query child skills: %v", err)
	}
	if err := deleteSkill(context.Background(), db.DB, "u1", parent.ID); err != nil {
		t.Fatalf("delete parent skill: %v", err)
	}

	if err := db.Where("id = ?", parent.ID).Take(&orm.SkillResource{}).Error; !errors.Is(err, gorm.ErrRecordNotFound) {
		t.Fatalf("expected parent record to be deleted, got err=%v", err)
	}
	for _, child := range children {
		if err := db.Where("id = ?", child.ID).Take(&orm.SkillResource{}).Error; !errors.Is(err, gorm.ErrRecordNotFound) {
			t.Fatalf("expected child record %s to be deleted, got err=%v", child.ID, err)
		}
	}
}

func stringPtr(value string) *string {
	return &value
}
