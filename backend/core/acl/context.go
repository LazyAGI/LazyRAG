package acl

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/gorilla/mux"
)

// CurrentUserID textRequesttextUser id（textAuthorizationtextSet）。
// text X-User-Id text，text。
func CurrentUserID(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("X-User-Id"))
}

// PathKbID text kb_id，text
func PathKbID(r *http.Request) string {
	vars := mux.Vars(r)
	return vars["kb_id"]
}

// PathACLID text acl_id
func PathACLID(r *http.Request) int64 {
	vars := mux.Vars(r)
	s := vars["acl_id"]
	if s == "" {
		return 0
	}
	id, _ := strconv.ParseInt(s, 10, 64)
	return id
}

// PathGroupID text group_id。
func PathGroupID(r *http.Request) string {
	vars := mux.Vars(r)
	return strings.TrimSpace(vars["group_id"])
}

// PathUserID text user_id。
func PathUserID(r *http.Request) string {
	vars := mux.Vars(r)
	return strings.TrimSpace(vars["user_id"])
}
