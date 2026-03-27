package common

import (
	"net/http"
	"strings"

	"github.com/gorilla/mux"
)

// PathVar 返回清洗后的路径变量值。
// 对于形如 /resources/{id}:action 的 gorilla/mux 路由，最后一个变量会被解析成 "id:action"，
// 这里统一剥离末尾的 ":action" 后缀，避免把动作名误当成资源 ID。
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
