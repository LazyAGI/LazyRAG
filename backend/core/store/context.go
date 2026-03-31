package store

import (
	"net/http"

	"lazyrag/core/common"
)

// UserID returns request header X-User-Id.
func UserID(r *http.Request) string {
	return common.UserID(r)
}

// UserName textRequesttext X-User-Name textUsertext。
func UserName(r *http.Request) string {
	return common.UserName(r)
}
