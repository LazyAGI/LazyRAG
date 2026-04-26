package main

import (
	"encoding/json"
	"testing"

	"github.com/gorilla/mux"
)

func TestOpenAPISpecCoversEvolutionSkillMemoryPreferenceOperations(t *testing.T) {
	r := mux.NewRouter()
	registerAllRoutes(r)

	specJSON, err := buildOpenAPISpecFromRouter(r)
	if err != nil {
		t.Fatalf("build openapi spec: %v", err)
	}

	var spec map[string]any
	if err := json.Unmarshal(specJSON, &spec); err != nil {
		t.Fatalf("decode openapi spec: %v", err)
	}

	paths, ok := spec["paths"].(map[string]any)
	if !ok {
		t.Fatalf("paths missing in openapi spec")
	}

	cases := []struct {
		method          string
		path            string
		expectRequest   bool
		expectParams    bool
		expectResponses bool
	}{
		{"get", "/api/core/evolution/suggestions", false, true, true},
		{"get", "/api/core/evolution/suggestions/{id}", false, true, true},
		{"post", "/api/core/evolution/suggestions/{id}:approve", false, true, true},
		{"post", "/api/core/evolution/suggestions/{id}:reject", false, true, true},
		{"post", "/api/core/evolution/suggestions:batchApprove", true, false, true},
		{"post", "/api/core/evolution/suggestions:batchReject", true, false, true},
		{"get", "/api/core/skills", false, true, true},
		{"post", "/api/core/skills", true, false, true},
		{"get", "/api/core/skills/{skill_id}", false, true, true},
		{"patch", "/api/core/skills/{skill_id}", true, true, true},
		{"delete", "/api/core/skills/{skill_id}", false, true, true},
		{"get", "/api/core/skills/{skill_id}:draft-preview", false, true, true},
		{"post", "/api/core/skills/{skill_id}:generate", true, true, true},
		{"post", "/api/core/skills/{skill_id}:confirm", false, true, true},
		{"post", "/api/core/skills/{skill_id}:discard", false, true, true},
		{"post", "/api/core/skills/{skill_id}:share", true, true, true},
		{"get", "/api/core/skill-shares/incoming", false, true, true},
		{"get", "/api/core/skill-shares/outgoing", false, true, true},
		{"get", "/api/core/skill-shares/{share_item_id}", false, true, true},
		{"post", "/api/core/skill-shares/{share_item_id}:accept", false, true, true},
		{"post", "/api/core/skill-shares/{share_item_id}:reject", false, true, true},
		{"post", "/api/core/skill/suggestion", true, false, true},
		{"post", "/api/core/skill/create", true, false, true},
		{"post", "/api/core/skill/remove", true, false, true},
		{"get", "/api/core/personalization-items", false, false, true},
		{"get", "/api/core/personalization-setting", false, false, true},
		{"put", "/api/core/personalization-setting", true, false, true},
		{"put", "/api/core/memory", true, false, true},
		{"get", "/api/core/memory:draft-preview", false, false, true},
		{"post", "/api/core/memory/suggestion", true, false, true},
		{"post", "/api/core/memory:generate", true, false, true},
		{"post", "/api/core/memory:confirm", false, false, true},
		{"post", "/api/core/memory:discard", false, false, true},
		{"put", "/api/core/user-preference", true, false, true},
		{"get", "/api/core/user-preference:draft-preview", false, false, true},
		{"post", "/api/core/user_preference/suggestion", true, false, true},
		{"post", "/api/core/user-preference:generate", true, false, true},
		{"post", "/api/core/user-preference:confirm", false, false, true},
		{"post", "/api/core/user-preference:discard", false, false, true},
	}

	for _, tc := range cases {
		pathItem, ok := paths[tc.path].(map[string]any)
		if !ok {
			t.Fatalf("path missing from openapi spec: %s", tc.path)
		}
		op, ok := pathItem[tc.method].(map[string]any)
		if !ok {
			t.Fatalf("operation missing from openapi spec: %s %s", tc.method, tc.path)
		}

		if tc.expectRequest {
			if _, ok := op["requestBody"].(map[string]any); !ok {
				t.Fatalf("requestBody missing for %s %s", tc.method, tc.path)
			}
		}
		if tc.expectParams {
			params, ok := op["parameters"].([]any)
			if !ok || len(params) == 0 {
				t.Fatalf("parameters missing for %s %s", tc.method, tc.path)
			}
		}
		if tc.expectResponses {
			responses, ok := op["responses"].(map[string]any)
			if !ok {
				t.Fatalf("responses missing for %s %s", tc.method, tc.path)
			}
			resp200, ok := responses["200"].(map[string]any)
			if !ok {
				t.Fatalf("200 response missing for %s %s", tc.method, tc.path)
			}
			content, ok := resp200["content"].(map[string]any)
			if !ok || len(content) == 0 {
				t.Fatalf("response schema missing for %s %s", tc.method, tc.path)
			}
		}
	}
}
