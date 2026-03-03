package acl

import (
	"net/http"
	"strconv"

	"github.com/gorilla/mux"
)

// CurrentUserID returns the current user id from request (e.g. set by auth middleware).
// Reads X-User-Id header; 0 if missing or invalid.
func CurrentUserID(r *http.Request) int64 {
	s := r.Header.Get("X-User-Id")
	if s == "" {
		return 0
	}
	id, _ := strconv.ParseInt(s, 10, 64)
	return id
}

// PathKbID returns kb_id from path. Returns empty string if missing.
func PathKbID(r *http.Request) string {
	vars := mux.Vars(r)
	return vars["kb_id"]
}

// PathACLID returns acl_id from path.
func PathACLID(r *http.Request) int64 {
	vars := mux.Vars(r)
	s := vars["acl_id"]
	if s == "" {
		return 0
	}
	id, _ := strconv.ParseInt(s, 10, 64)
	return id
}
