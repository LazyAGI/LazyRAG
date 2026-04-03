package common

import (
	"net/http"
	"strings"

	"github.com/gorilla/mux"
)

// PathVar text。
// text /resources/{id}:action text gorilla/mux text，text "id:action"，
// text ":action" text，text ID。
func PathVar(r *http.Request, name string) string {
	if r == nil {
		return ""
	}
	raw := strings.TrimSpace(mux.Vars(r)[name])
	if raw == "" {
		return ""
	}
	if idx := strings.LastIndex(raw, ":"); idx > 0 {
		suffix := raw[idx+1:]
		if isActionSuffix(suffix) {
			return raw[:idx]
		}
	}
	return raw
}

func isActionSuffix(s string) bool {
	if s == "" {
		return false
	}
	for _, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') {
			continue
		}
		return false
	}
	return true
}
