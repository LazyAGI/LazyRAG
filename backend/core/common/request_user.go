package common

import (
	"net/http"
	"strings"
)

// UserID textRequesttext X-User-Id textUser ID。
func UserID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-User-Id"))
}

// UserName textRequesttext X-User-Name textUsertext。
func UserName(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-User-Name"))
}
