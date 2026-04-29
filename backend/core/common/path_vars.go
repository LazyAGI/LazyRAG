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
	prevHyphen := false
	for i, r := range s {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') {
			prevHyphen = false
			continue
		}
		if r == '-' {
			if i == 0 || i == len(s)-1 || prevHyphen {
				return false
			}
			prevHyphen = true
			continue
		}
		return false
	}
	return !prevHyphen
}
