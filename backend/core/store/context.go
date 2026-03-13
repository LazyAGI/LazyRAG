package store

import (
	"net/http"

	"lazyrag/core/common"
)

// UserID 从请求头 X-User-Id 读取当前用户 ID，与 neutrino 等行为一致。
func UserID(r *http.Request) string {
	return common.UserID(r)
}

// UserName 从请求头 X-User-Name 读取当前用户名。
func UserName(r *http.Request) string {
	return common.UserName(r)
}
