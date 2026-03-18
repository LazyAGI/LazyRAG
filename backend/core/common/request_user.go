package common

import (
	"net/http"
	"strings"
)

// UserID 从请求头 X-User-Id 读取当前用户 ID。
func UserID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-User-Id"))
}

// UserName 从请求头 X-User-Name 读取当前用户名。
func UserName(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-User-Name"))
}
