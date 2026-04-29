package chat

import (
	"strconv"
	"strings"
	"testing"

	"lazyrag/core/evolution"
)

func TestBuildChatRequestBodyUsesConversationIDDerivedSessionID(t *testing.T) {
	body := buildChatRequestBody("conv-1", "", "hello", nil, map[string]any{}, nil)
	sessionID, ok := body["session_id"].(string)
	if !ok {
		t.Fatalf("expected session_id string, got %T", body["session_id"])
	}
	if !strings.HasPrefix(sessionID, "conv-1_") {
		t.Fatalf("expected session_id to start with conversation id, got %q", sessionID)
	}
	suffix := strings.TrimPrefix(sessionID, "conv-1_")
	if suffix == "" {
		t.Fatalf("expected timestamp suffix in session_id, got %q", sessionID)
	}
	if _, err := strconv.ParseInt(suffix, 10, 64); err != nil {
		t.Fatalf("expected millisecond timestamp suffix, got %q: %v", suffix, err)
	}
}

func TestBuildChatRequestBodyUsesDatasetListFilters(t *testing.T) {
	body := buildChatRequestBody("conv-1", "", "hello", nil, map[string]any{
		"conversation": map[string]any{
			"search_config": map[string]any{
				"dataset_list": []any{
					map[string]any{"id": "ds_1"},
					map[string]any{"id": "ds_2"},
				},
				"creators": []any{"user_a"},
				"tags":     []any{"tag_a", "tag_b"},
			},
		},
	}, nil)

	filters, ok := body["filters"].(map[string]any)
	if !ok {
		t.Fatalf("expected filters map, got %T", body["filters"])
	}

	kbIDs, ok := filters["kb_id"].([]string)
	if !ok {
		t.Fatalf("expected kb_id []string, got %T", filters["kb_id"])
	}
	if len(kbIDs) != 2 || kbIDs[0] != "ds_1" || kbIDs[1] != "ds_2" {
		t.Fatalf("unexpected kb_id: %#v", kbIDs)
	}

	creators, ok := filters["creator"].([]string)
	if !ok {
		t.Fatalf("expected creator []string, got %T", filters["creator"])
	}
	if len(creators) != 1 || creators[0] != "user_a" {
		t.Fatalf("unexpected creator: %#v", creators)
	}

	tags, ok := filters["tags"].([]string)
	if !ok {
		t.Fatalf("expected tags []string, got %T", filters["tags"])
	}
	if len(tags) != 2 || tags[0] != "tag_a" || tags[1] != "tag_b" {
		t.Fatalf("unexpected tags: %#v", tags)
	}
}

func TestBuildChatRequestBodyKeepsExistingFilters(t *testing.T) {
	existing := map[string]any{"kb_id": []string{"manual"}}
	body := buildChatRequestBody("conv-1", "", "hello", nil, map[string]any{
		"filters": existing,
		"conversation": map[string]any{
			"search_config": map[string]any{
				"dataset_list": []any{map[string]any{"id": "ds_1"}},
			},
		},
	}, nil)

	filters, ok := body["filters"].(map[string]any)
	if !ok {
		t.Fatalf("expected filters map, got %T", body["filters"])
	}

	kbIDs, ok := filters["kb_id"].([]string)
	if !ok {
		t.Fatalf("expected kb_id []string, got %T", filters["kb_id"])
	}
	if len(kbIDs) != 1 || kbIDs[0] != "manual" {
		t.Fatalf("expected existing filters to be preserved, got %#v", kbIDs)
	}
}

func TestBuildChatRequestBodyAddsEvolutionContext(t *testing.T) {
	ctx := &evolution.ChatResourceContext{
		AvailableTools:     []string{"all"},
		AvailableSkills:    []string{"coding/git-workflow"},
		Memory:             "memory-content",
		UserPreference:     "preference-content",
		UsePersonalization: true,
	}
	body := buildChatRequestBody("conv-1", "session-1", "hello", nil, map[string]any{}, ctx)

	if got := body["session_id"]; got != "session-1" {
		t.Fatalf("expected session_id to be preserved, got %#v", got)
	}
	if got, ok := body["available_tools"].([]string); !ok || len(got) != 1 || got[0] != "all" {
		t.Fatalf("unexpected available_tools: %#v", body["available_tools"])
	}
	if got, ok := body["available_skills"].([]string); !ok || len(got) != 1 || got[0] != "coding/git-workflow" {
		t.Fatalf("unexpected available_skills: %#v", body["available_skills"])
	}
	if _, ok := body["skill_fs_url"]; ok {
		t.Fatalf("expected skill_fs_url to be omitted")
	}
	if got := body["memory"]; got != "memory-content" {
		t.Fatalf("unexpected memory: %#v", got)
	}
	if got := body["user_preference"]; got != "preference-content" {
		t.Fatalf("unexpected user_preference: %#v", got)
	}
	if got, ok := body["use_memory"].(bool); !ok || !got {
		t.Fatalf("expected use_memory default true, got %#v", body["use_memory"])
	}
	if got, ok := body["reasoning"].(bool); !ok || !got {
		t.Fatalf("expected reasoning default true, got %#v", body["reasoning"])
	}
}

func TestBuildChatRequestBodySkipsMemoryAndPreferenceWhenPersonalizationDisabled(t *testing.T) {
	ctx := &evolution.ChatResourceContext{
		AvailableTools:     []string{"all"},
		AvailableSkills:    []string{"coding/git-workflow"},
		Memory:             "memory-content",
		UserPreference:     "preference-content",
		UsePersonalization: false,
	}
	body := buildChatRequestBody("conv-1", "session-1", "hello", nil, map[string]any{}, ctx)

	if got, ok := body["use_memory"].(bool); !ok || got {
		t.Fatalf("expected use_memory false, got %#v", body["use_memory"])
	}
	if _, ok := body["memory"]; ok {
		t.Fatalf("expected memory to be omitted when personalization is disabled")
	}
	if _, ok := body["user_preference"]; ok {
		t.Fatalf("expected user_preference to be omitted when personalization is disabled")
	}
}

func TestBuildChatRequestBodyPreservesExplicitReasoningFalse(t *testing.T) {
	body := buildChatRequestBody("conv-1", "", "hello", nil, map[string]any{
		"reasoning": false,
	}, nil)

	if got, ok := body["reasoning"].(bool); !ok || got {
		t.Fatalf("expected reasoning false, got %#v", body["reasoning"])
	}
}

func TestBuildLazyChatRequestMapsAllFields(t *testing.T) {
	req := buildLazyChatRequest(map[string]any{
		"query":      "hello",
		"session_id": "conv-1",
		"history": []any{
			map[string]any{"role": "user", "content": "q1"},
			map[string]any{"role": "assistant", "content": "a1"},
		},
		"filters": map[string]any{
			"kb_id":   []any{"ds_1"},
			"creator": []any{"u1"},
			"tags":    []any{"t1"},
		},
		"files":           []any{"f1", "f2"},
		"reasoning":       false,
		"databases":       []any{map[string]any{"name": "db1"}},
		"enable_thinking": true,
		"available_tools": []any{"all"},
		"available_skills": []any{
			"coding/git-workflow",
		},
		"memory":          "memory-content",
		"user_preference": "preference-content",
		"use_memory":      true,
	})

	if req.Query != "hello" || req.SessionID != "conv-1" {
		t.Fatalf("unexpected base fields: %#v", req)
	}
	if len(req.History) != 2 || req.History[0].Role != "user" || req.History[1].Content != "a1" {
		t.Fatalf("unexpected history: %#v", req.History)
	}
	if req.Filters == nil || len(req.Filters.DatasetIDs) != 1 || req.Filters.DatasetIDs[0] != "ds_1" {
		t.Fatalf("unexpected filters: %#v", req.Filters)
	}
	if len(req.Filters.Creators) != 1 || req.Filters.Creators[0] != "u1" {
		t.Fatalf("unexpected creators: %#v", req.Filters.Creators)
	}
	if len(req.Filters.Tags) != 1 || req.Filters.Tags[0] != "t1" {
		t.Fatalf("unexpected tags: %#v", req.Filters.Tags)
	}
	if len(req.Files) != 2 || req.Files[0] != "f1" || req.Files[1] != "f2" {
		t.Fatalf("unexpected files: %#v", req.Files)
	}
	if len(req.Databases) != 1 {
		t.Fatalf("unexpected databases: %#v", req.Databases)
	}
	if req.Reasoning {
		t.Fatalf("expected reasoning to be false")
	}
	if !req.EnableThinking {
		t.Fatalf("expected enable_thinking to be true")
	}
	if len(req.AvailableTools) != 1 || req.AvailableTools[0] != "all" {
		t.Fatalf("unexpected available_tools: %#v", req.AvailableTools)
	}
	if len(req.AvailableSkills) != 1 || req.AvailableSkills[0] != "coding/git-workflow" {
		t.Fatalf("unexpected available_skills: %#v", req.AvailableSkills)
	}
	if req.Memory != "memory-content" || req.UserPreference != "preference-content" {
		t.Fatalf("unexpected memory context: %+v", req)
	}
	if !req.UseMemory {
		t.Fatalf("expected use_memory to be true")
	}
}

func TestBuildLazyChatRequestDefaultsReasoningTrue(t *testing.T) {
	req := buildLazyChatRequest(map[string]any{
		"query":      "hello",
		"session_id": "conv-1",
	})

	if !req.Reasoning {
		t.Fatalf("expected reasoning default true")
	}
}
