package acl

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
)

const (
	codeOK    = 0
	codeError = 1
)

func reply(w http.ResponseWriter, code int, message string, data any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(APIResponse{Code: code, Message: message, Data: data})
}

func replyOK(w http.ResponseWriter, data any) {
	reply(w, codeOK, "ok", data)
}

func replyErr(w http.ResponseWriter, message string, statusCode int) {
	w.WriteHeader(statusCode)
	reply(w, codeError, message, nil)
}

func validGranteeType(s string) bool {
	return s == GranteeUser || s == GranteeTenant
}

func validPermission(s string) bool {
	return s == PermRead || s == PermWrite
}

// ListACL 对应 GET /api/kb/{kb_id}/acl
func ListACL(w http.ResponseWriter, r *http.Request) {
	kbID := PathKbID(r)
	if kbID == "" {
		replyErr(w, "invalid kb_id", http.StatusBadRequest)
		return
	}
	granteeType := r.URL.Query().Get("grantee_type")
	list := GetStore().ListACL(ResourceTypeKB, kbID, granteeType)
	replyOK(w, map[string]any{"list": list})
}

// AddACL 对应 POST /api/kb/{kb_id}/acl
func AddACL(w http.ResponseWriter, r *http.Request) {
	kbID := PathKbID(r)
	if kbID == "" {
		replyErr(w, "invalid kb_id", http.StatusBadRequest)
		return
	}
	var body AddACLRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		replyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if !validGranteeType(body.GranteeType) {
		replyErr(w, "grantee_type must be user or tenant", http.StatusBadRequest)
		return
	}
	if !validPermission(body.Permission) {
		replyErr(w, "permission must be read or write", http.StatusBadRequest)
		return
	}
	createdBy := CurrentUserID(r)
	aclID := GetStore().AddACL(ResourceTypeKB, kbID, body.GranteeType, body.GranteeID, body.Permission, createdBy, body.ExpiresAt)
	replyOK(w, map[string]any{"acl_id": aclID})
}

// UpdateACL 对应 PUT /api/kb/{kb_id}/acl/{acl_id}
func UpdateACL(w http.ResponseWriter, r *http.Request) {
	kbID := PathKbID(r)
	aclID := PathACLID(r)
	if kbID == "" || aclID == 0 {
		replyErr(w, "invalid path", http.StatusBadRequest)
		return
	}
	var body UpdateACLRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		replyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if !validPermission(body.Permission) {
		replyErr(w, "permission must be read or write", http.StatusBadRequest)
		return
	}
	_, ok := GetStore().GetACLByID(ResourceTypeKB, kbID, aclID)
	if !ok {
		replyErr(w, "acl not found", http.StatusNotFound)
		return
	}
	if !GetStore().UpdateACL(aclID, body.Permission, body.ExpiresAt) {
		replyErr(w, "update failed", http.StatusInternalServerError)
		return
	}
	replyOK(w, nil)
}

// DeleteACL 对应 DELETE /api/kb/{kb_id}/acl/{acl_id}
func DeleteACL(w http.ResponseWriter, r *http.Request) {
	kbID := PathKbID(r)
	aclID := PathACLID(r)
	if kbID == "" || aclID == 0 {
		replyErr(w, "invalid path", http.StatusBadRequest)
		return
	}
	_, ok := GetStore().GetACLByID(ResourceTypeKB, kbID, aclID)
	if !ok {
		replyErr(w, "acl not found", http.StatusNotFound)
		return
	}
	GetStore().DeleteACL(aclID)
	replyOK(w, nil)
}

// BatchAddACL 对应 POST /api/kb/{kb_id}/acl/batch
func BatchAddACL(w http.ResponseWriter, r *http.Request) {
	kbID := PathKbID(r)
	if kbID == "" {
		replyErr(w, "invalid kb_id", http.StatusBadRequest)
		return
	}
	var body BatchAddACLRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		replyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	createdBy := CurrentUserID(r)
	count := 0
	for _, item := range body.Items {
		if !validGranteeType(item.GranteeType) || !validPermission(item.Permission) {
			continue
		}
		GetStore().AddACL(ResourceTypeKB, kbID, item.GranteeType, item.GranteeID, item.Permission, createdBy, nil)
		count++
	}
	replyOK(w, map[string]any{"count": count})
}

// GetPermission 对应 GET /api/kb/{kb_id}/permission
func GetPermission(w http.ResponseWriter, r *http.Request) {
	kbID := PathKbID(r)
	if kbID == "" {
		replyErr(w, "invalid kb_id", http.StatusBadRequest)
		return
	}
	userID := CurrentUserID(r)
	permission, source := PermissionFor(ResourceTypeKB, kbID, userID)
	replyOK(w, PermissionResult{Permission: permission, Source: source})
}

// PermissionBatch 对应 POST /api/kb/permission/batch
func PermissionBatch(w http.ResponseWriter, r *http.Request) {
	var body PermissionBatchRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		replyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	userID := CurrentUserID(r)
	list := make([]PermissionBatchItem, 0, len(body.KbIDs))
	for _, kbID := range body.KbIDs {
		perm, _ := PermissionFor(ResourceTypeKB, kbID, userID)
		list = append(list, PermissionBatchItem{KbID: kbID, Permission: perm})
	}
	replyOK(w, list)
}

// CanHandler 对应 GET /api/kb/{kb_id}/can?action=create_doc|delete_doc|delete_kb
func CanHandler(w http.ResponseWriter, r *http.Request) {
	kbID := PathKbID(r)
	if kbID == "" {
		replyErr(w, "invalid kb_id", http.StatusBadRequest)
		return
	}
	action := r.URL.Query().Get("action")
	if action == "" {
		replyErr(w, "action required", http.StatusBadRequest)
		return
	}
	userID := CurrentUserID(r)
	allowed := Can(userID, ResourceTypeKB, kbID, action)
	replyOK(w, CanResult{Allowed: allowed})
}

// ListKB 对应 GET /api/kb/list?permission=read|write&keyword=&page=&page_size=
func ListKB(w http.ResponseWriter, r *http.Request) {
	permissionFilter := r.URL.Query().Get("permission") // read or write
	keyword := r.URL.Query().Get("keyword")
	page := parsePositiveInt(r.URL.Query().Get("page"), 1)
	pageSize := parsePositiveInt(r.URL.Query().Get("page_size"), 20)
	if pageSize > 100 {
		pageSize = 100
	}
	userID := CurrentUserID(r)
	st := GetStore()
	allIDs := st.AllKBIDs()
	var list []KBListRow
	for _, kbID := range allIDs {
		kb := st.GetKB(kbID)
		if kb == nil {
			continue
		}
		perm, _ := PermissionFor(ResourceTypeKB, kbID, userID)
		if perm == PermNone {
			continue
		}
		if permissionFilter == PermWrite && perm != PermWrite {
			continue
		}
		if keyword != "" && !strings.Contains(strings.ToLower(kb.Name), strings.ToLower(keyword)) {
			continue
		}
		vis := st.GetVisibility(kbID)
		list = append(list, KBListRow{ID: kbID, Name: kb.Name, Visibility: vis, Permission: perm})
	}
	total := int64(len(list))
	start := (page - 1) * pageSize
	if start < 0 {
		start = 0
	}
	if start >= len(list) {
		list = nil
	} else {
		end := start + pageSize
		if end > len(list) {
			end = len(list)
		}
		list = list[start:end]
	}
	replyOK(w, KBListResult{Total: total, List: list})
}

func parsePositiveInt(s string, defaultVal int) int {
	if s == "" {
		return defaultVal
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 1 {
		return defaultVal
	}
	return n
}
