package acl

import (
	"net/http"
	"strconv"

	"github.com/gorilla/mux"
)

// CurrentUserID 从请求中读取当前用户 id（如由鉴权中间件设置）
// 读取 X-User-Id 头，缺失或非法时返回 0
func CurrentUserID(r *http.Request) int64 {
	s := r.Header.Get("X-User-Id")
	if s == "" {
		return 0
	}
	id, _ := strconv.ParseInt(s, 10, 64)
	return id
}

// PathKbID 从路径中解析 kb_id，缺失时返回空字符串
func PathKbID(r *http.Request) string {
	vars := mux.Vars(r)
	return vars["kb_id"]
}

// PathACLID 从路径中解析 acl_id
func PathACLID(r *http.Request) int64 {
	vars := mux.Vars(r)
	s := vars["acl_id"]
	if s == "" {
		return 0
	}
	id, _ := strconv.ParseInt(s, 10, 64)
	return id
}
