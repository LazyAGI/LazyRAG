package chat

import "testing"

func TestBuildChatRequestBodyUsesDatasetListFilters(t *testing.T) {
	body := buildChatRequestBody("conv-1", "hello", nil, map[string]any{
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
	})

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
	body := buildChatRequestBody("conv-1", "hello", nil, map[string]any{
		"filters": existing,
		"conversation": map[string]any{
			"search_config": map[string]any{
				"dataset_list": []any{map[string]any{"id": "ds_1"}},
			},
		},
	})

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
