package common

import (
	"net/http/httptest"
	"testing"

	"github.com/gorilla/mux"
)

func TestPathVarStripsHyphenatedActionSuffix(t *testing.T) {
	req := httptest.NewRequest("GET", "/skills/skill-1:draft-preview", nil)
	req = mux.SetURLVars(req, map[string]string{"skill_id": "skill-1:draft-preview"})

	if got := PathVar(req, "skill_id"); got != "skill-1" {
		t.Fatalf("expected skill_id %q, got %q", "skill-1", got)
	}
}
