package evolution

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"lazyrag/core/common/orm"
)

func newTestDB(t *testing.T) *orm.DB {
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

func TestBuildChatResourceContextCreatesPerUserResourcesAndSnapshots(t *testing.T) {
	db := newTestDB(t)

	tmpDir := t.TempDir()
	if err := os.Setenv("LAZYRAG_SKILL_VOLUME_ROOT", tmpDir); err != nil {
		t.Fatalf("set env: %v", err)
	}
	t.Cleanup(func() { _ = os.Unsetenv("LAZYRAG_SKILL_VOLUME_ROOT") })

	relativePath := ParentSkillRelativePath("coding", "git-workflow")
	storagePath := filepath.Join(tmpDir, "skills", "u1", filepath.FromSlash(relativePath))
	if err := os.MkdirAll(filepath.Dir(storagePath), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	content := "---\nname: git-workflow\ndescription: git workflow\n---\nbody"
	if err := os.WriteFile(storagePath, []byte(content), 0o644); err != nil {
		t.Fatalf("write skill file: %v", err)
	}

	now := time.Now()
	skill := orm.SkillResource{
		ID:              "skill-1",
		OwnerUserID:     "u1",
		OwnerUserName:   "User 1",
		Category:        "coding",
		ParentSkillName: "git-workflow",
		SkillName:       "git-workflow",
		NodeType:        SkillNodeTypeParent,
		FileExt:         "md",
		RelativePath:    relativePath,
		StoragePath:     storagePath,
		ContentHash:     HashContent(content),
		IsEnabled:       true,
		UpdateStatus:    UpdateStatusUpToDate,
		CreateUserID:    "u1",
		CreateUserName:  "User 1",
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	if err := db.Create(&skill).Error; err != nil {
		t.Fatalf("create skill: %v", err)
	}

	ctx, err := BuildChatResourceContext(context.Background(), db.DB, "u1", "User 1", "session-1")
	if err != nil {
		t.Fatalf("build chat resource context: %v", err)
	}
	if len(ctx.AvailableTools) != 1 || ctx.AvailableTools[0] != "all" {
		t.Fatalf("unexpected available_tools: %#v", ctx.AvailableTools)
	}
	if len(ctx.AvailableSkills) != 1 || ctx.AvailableSkills[0] != "coding/git-workflow" {
		t.Fatalf("unexpected available_skills: %#v", ctx.AvailableSkills)
	}
	expectedSkillFSURL := filepath.ToSlash(filepath.Join(tmpDir, "skills", "u1"))
	if ctx.SkillFSURL != expectedSkillFSURL {
		t.Fatalf("unexpected skill_fs_url: %q", ctx.SkillFSURL)
	}
	if ctx.Memory != "" || ctx.UserPreference != "" {
		t.Fatalf("expected empty user-scoped content, got memory=%q preference=%q", ctx.Memory, ctx.UserPreference)
	}
	if !ctx.UsePersonalization {
		t.Fatalf("expected personalization enabled by default")
	}

	secondCtx, err := BuildChatResourceContext(context.Background(), db.DB, "u2", "User 2", "session-2")
	if err != nil {
		t.Fatalf("build second chat resource context: %v", err)
	}
	if secondCtx.Memory != "" || secondCtx.UserPreference != "" {
		t.Fatalf("expected empty second user-scoped content, got memory=%q preference=%q", secondCtx.Memory, secondCtx.UserPreference)
	}
	if !secondCtx.UsePersonalization {
		t.Fatalf("expected second user personalization enabled by default")
	}

	var memoryCount int64
	if err := db.Model(&orm.SystemMemory{}).Count(&memoryCount).Error; err != nil {
		t.Fatalf("count system_memories: %v", err)
	}
	if memoryCount != 2 {
		t.Fatalf("expected 2 system memory rows, got %d", memoryCount)
	}

	var preferenceCount int64
	if err := db.Model(&orm.SystemUserPreference{}).Count(&preferenceCount).Error; err != nil {
		t.Fatalf("count system_user_preferences: %v", err)
	}
	if preferenceCount != 2 {
		t.Fatalf("expected 2 system user preference rows, got %d", preferenceCount)
	}

	var snapshotCount int64
	if err := db.Model(&orm.ResourceSessionSnapshot{}).Where("session_id = ?", "session-1").Count(&snapshotCount).Error; err != nil {
		t.Fatalf("count snapshots: %v", err)
	}
	if snapshotCount != 3 {
		t.Fatalf("expected 3 snapshots, got %d", snapshotCount)
	}

	var memories []orm.SystemMemory
	if err := db.Order("user_id ASC").Find(&memories).Error; err != nil {
		t.Fatalf("list system_memories: %v", err)
	}
	if len(memories) != 2 || memories[0].UserID != "u1" || memories[1].UserID != "u2" {
		t.Fatalf("expected per-user memory rows for u1/u2, got %#v", memories)
	}

	var prefs []orm.SystemUserPreference
	if err := db.Order("user_id ASC").Find(&prefs).Error; err != nil {
		t.Fatalf("list system_user_preferences: %v", err)
	}
	if len(prefs) != 2 || prefs[0].UserID != "u1" || prefs[1].UserID != "u2" {
		t.Fatalf("expected per-user preference rows for u1/u2, got %#v", prefs)
	}
}

func TestSkillVolumeRootFallsBackToUploadRoot(t *testing.T) {
	t.Setenv("LAZYRAG_SKILL_VOLUME_ROOT", "")
	t.Setenv("LAZYRAG_UPLOAD_ROOT", "/var/lib/lazyrag/uploads")

	got := filepath.ToSlash(SkillVolumeRoot())
	want := "/var/lib/lazyrag/uploads/skill-volume"
	if got != want {
		t.Fatalf("unexpected skill volume root: got %q want %q", got, want)
	}

	gotFSURL := filepath.ToSlash(SkillFSURL("u1001"))
	wantFSURL := "/var/lib/lazyrag/uploads/skill-volume/skills/u1001"
	if gotFSURL != wantFSURL {
		t.Fatalf("unexpected skill fs url: got %q want %q", gotFSURL, wantFSURL)
	}
}

func TestResolveRequestUserIgnoresFallbackAndUsesSessionSnapshot(t *testing.T) {
	db := newTestDB(t)

	now := time.Now()
	snapshot := orm.ResourceSessionSnapshot{
		ID:           "snapshot-1",
		SessionID:    "session-1",
		UserID:       "session-user",
		ResourceType: ResourceTypeMemory,
		ResourceKey:  SystemResourceKey(ResourceTypeMemory),
		SnapshotHash: HashContent(""),
		CreatedAt:    now,
	}
	if err := db.Create(&snapshot).Error; err != nil {
		t.Fatalf("create snapshot: %v", err)
	}

	userID, userName, err := ResolveRequestUser(context.Background(), db.DB, "session-1", "header-user", "Header User")
	if err != nil {
		t.Fatalf("resolve request user: %v", err)
	}
	if userID != "session-user" {
		t.Fatalf("expected session user, got %q", userID)
	}
	if userName != "" {
		t.Fatalf("expected empty user name when conversation is absent, got %q", userName)
	}
}

func TestLoadApprovedSuggestionsFiltersByUser(t *testing.T) {
	db := newTestDB(t)

	now := time.Now()
	rows := []orm.ResourceSuggestion{
		{
			ID:           "s-u1",
			UserID:       "u1",
			ResourceType: ResourceTypeSkill,
			ResourceKey:  ParentSkillRelativePath("coding", "git-workflow"),
			Action:       SuggestionActionModify,
			SessionID:    "session-u1",
			Title:        "u1 accepted",
			Content:      "update skill for u1",
			Status:       SuggestionStatusAccepted,
			CreatedAt:    now,
			UpdatedAt:    now,
		},
		{
			ID:           "s-u2",
			UserID:       "u2",
			ResourceType: ResourceTypeSkill,
			ResourceKey:  ParentSkillRelativePath("coding", "git-workflow"),
			Action:       SuggestionActionModify,
			SessionID:    "session-u2",
			Title:        "u2 accepted",
			Content:      "update skill for u2",
			Status:       SuggestionStatusAccepted,
			CreatedAt:    now.Add(time.Second),
			UpdatedAt:    now.Add(time.Second),
		},
	}
	if err := db.Create(&rows).Error; err != nil {
		t.Fatalf("create suggestions: %v", err)
	}

	got, err := LoadApprovedSuggestions(context.Background(), db.DB, "u1", ResourceTypeSkill, ParentSkillRelativePath("coding", "git-workflow"), nil)
	if err != nil {
		t.Fatalf("load accepted suggestions: %v", err)
	}
	if len(got) != 1 || got[0].ID != "s-u1" {
		t.Fatalf("expected only u1 suggestion, got %#v", got)
	}
}

func TestResolveRequestUserFallsBackToConversationOwner(t *testing.T) {
	db := newTestDB(t)

	now := time.Now()
	conversation := orm.Conversation{
		ID:          "conv-2",
		DisplayName: "Conversation 2",
		BaseModel: orm.BaseModel{
			CreateUserID:   "conversation-user",
			CreateUserName: "Conversation User",
			CreatedAt:      now,
			UpdatedAt:      now,
		},
	}
	if err := db.Create(&conversation).Error; err != nil {
		t.Fatalf("create conversation: %v", err)
	}

	userID, userName, err := ResolveRequestUser(context.Background(), db.DB, "conv-2_1710000000000", "header-user", "Header User")
	if err != nil {
		t.Fatalf("resolve request user: %v", err)
	}
	if userID != "conversation-user" {
		t.Fatalf("expected conversation owner, got %q", userID)
	}
	if userName != "Conversation User" {
		t.Fatalf("expected conversation owner name, got %q", userName)
	}
}
