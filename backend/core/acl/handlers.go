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
	return s == GranteeUser || s == GranteeGroup || s == GranteeTenant
}

func validPermissionForResource(resourceType, permission string) bool {
	return normalizePermission(resourceType, permission) != ""
}

// ListACL text GET /api/kb/{kb_id}/acl
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

// AddACL text POST /api/kb/{kb_id}/acl
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
		replyErr(w, "grantee_type must be user or group", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(body.GranteeID) == "" {
		replyErr(w, "grantee_id required", http.StatusBadRequest)
		return
	}
	if !validPermissionForResource(ResourceTypeKB, body.Permission) {
		replyErr(w, "invalid permission for kb resource", http.StatusBadRequest)
		return
	}
	createdBy := CurrentUserID(r)
	aclID := GetStore().AddACL(ResourceTypeKB, kbID, body.GranteeType, body.GranteeID, body.Permission, createdBy, body.ExpiresAt)
	if aclID == 0 {
		replyErr(w, "add acl failed", http.StatusInternalServerError)
		return
	}
	replyOK(w, map[string]any{"acl_id": aclID})
}

// UpdateACL text PUT /api/kb/{kb_id}/acl/{acl_id}
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
	if !validPermissionForResource(ResourceTypeKB, body.Permission) {
		replyErr(w, "invalid permission for kb resource", http.StatusBadRequest)
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

// DeleteACL text DELETE /api/kb/{kb_id}/acl/{acl_id}
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
	if !GetStore().DeleteACL(aclID) {
		replyErr(w, "delete failed", http.StatusInternalServerError)
		return
	}
	replyOK(w, nil)
}

// BatchAddACL text POST /api/kb/{kb_id}/acl/batch
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
	invalidCount := 0
	failedCount := 0
	for _, item := range body.Items {
		if !validGranteeType(item.GranteeType) || strings.TrimSpace(item.GranteeID) == "" || !validPermissionForResource(ResourceTypeKB, item.Permission) {
			invalidCount++
			continue
		}
		if aclID := GetStore().AddACL(ResourceTypeKB, kbID, item.GranteeType, item.GranteeID, item.Permission, createdBy, nil); aclID == 0 {
			failedCount++
			continue
		}
		count++
	}
	if count == 0 {
		status := http.StatusBadRequest
		message := "no valid acl items provided"
		if failedCount > 0 && invalidCount == 0 {
			status = http.StatusInternalServerError
			message = "failed to add acl items"
		}
		replyErr(w, message, status)
		return
	}
	replyOK(w, map[string]any{"count": count, "invalid_count": invalidCount, "failed_count": failedCount})
}

// GetPermission text GET /api/kb/{kb_id}/permission
func GetPermission(w http.ResponseWriter, r *http.Request) {
	kbID := PathKbID(r)
	if kbID == "" {
		replyErr(w, "invalid kb_id", http.StatusBadRequest)
		return
	}
	userID := CurrentUserID(r)
	permissions, source := PermissionsFor(ResourceTypeKB, kbID, userID)
	replyOK(w, PermissionResult{Permissions: permissions, Source: source})
}

// PermissionBatch text POST /api/kb/permission/batch
func PermissionBatch(w http.ResponseWriter, r *http.Request) {
	var body PermissionBatchRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		replyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	userID := CurrentUserID(r)
	list := make([]PermissionBatchItem, 0, len(body.KbIDs))
	for _, kbID := range body.KbIDs {
		permissions, _ := PermissionsFor(ResourceTypeKB, kbID, userID)
		list = append(list, PermissionBatchItem{KbID: kbID, Permissions: permissions})
	}
	replyOK(w, list)
}

// CanHandler text GET /api/kb/{kb_id}/can?action=create_doc|delete_doc|delete_kb
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

// ListKB text GET /api/kb/list?permission=read|write&keyword=&page=&page_size=
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
		permissions, _ := PermissionsFor(ResourceTypeKB, kbID, userID)
		if len(permissions) == 0 {
			continue
		}
		if permissionFilter != "" && !Can(userID, ResourceTypeKB, kbID, permissionFilter) {
			continue
		}
		if keyword != "" && !strings.Contains(strings.ToLower(kb.Name), strings.ToLower(keyword)) {
			continue
		}
		vis := st.GetVisibility(kbID)
		list = append(list, KBListRow{ID: kbID, Name: kb.Name, Visibility: vis, Permissions: permissions})
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

// GetKBAuthorization returns current ACL grants grouped by subject for authorization page.
// GET /api/kb/{kb_id}/authorization
func GetKBAuthorization(w http.ResponseWriter, r *http.Request) {
	kbID := PathKbID(r)
	if kbID == "" {
		replyErr(w, "invalid kb_id", http.StatusBadRequest)
		return
	}
	grants := GetStore().ListKBAuthorization(kbID)
	replyOK(w, GetKBAuthorizationResponse{
		KbID:   kbID,
		Grants: grants,
	})
}

// SetKBAuthorization replaces ACL grants of the KB in one shot.
// POST /api/kb/{kb_id}/authorization
func SetKBAuthorization(w http.ResponseWriter, r *http.Request) {
	kbID := PathKbID(r)
	if kbID == "" {
		replyErr(w, "invalid kb_id", http.StatusBadRequest)
		return
	}
	var body SetKBAuthorizationRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		replyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	normalized := make([]AuthorizationSubjectGrant, 0, len(body.Grants))
	for _, g := range body.Grants {
		gt := canonicalGranteeType(strings.TrimSpace(g.GranteeType))
		if gt != GranteeUser && gt != GranteeGroup {
			continue
		}
		if strings.TrimSpace(g.GranteeID) == "" {
			continue
		}
		permSeen := map[string]struct{}{}
		perms := make([]string, 0, len(g.Permissions))
		for _, p := range g.Permissions {
			np := normalizePermission(ResourceTypeKB, p)
			if np == "" || np == PermNone {
				continue
			}
			if _, ok := permSeen[np]; ok {
				continue
			}
			permSeen[np] = struct{}{}
			perms = append(perms, np)
		}
		if len(perms) == 0 {
			continue
		}
		normalized = append(normalized, AuthorizationSubjectGrant{
			GranteeType: gt,
			GranteeID:   g.GranteeID,
			Permissions: perms,
		})
	}
	inserted, err := GetStore().ReplaceACLForKB(kbID, normalized, CurrentUserID(r))
	if err != nil {
		replyErr(w, "save authorization failed", http.StatusInternalServerError)
		return
	}
	replyOK(w, map[string]any{
		"kb_id":         kbID,
		"subject_count": len(normalized),
		"acl_rows":      inserted,
	})
}

// ListGrantPrincipals returns selectable users/groups for authorization page.
// GET /api/kb/grant-principals
func ListGrantPrincipals(w http.ResponseWriter, r *http.Request) {
	st := GetStore()
	groups := st.ListGroups()
	groupOut := make([]GrantPrincipal, 0, len(groups))
	for _, g := range groups {
		groupOut = append(groupOut, GrantPrincipal{
			GranteeType: GranteeGroup,
			GranteeID:   g.ID,
			Name:        g.Name,
		})
	}

	userIDs := st.ListKnownUserIDs()
	userOut := make([]GrantPrincipal, 0, len(userIDs))
	for _, uid := range userIDs {
		userOut = append(userOut, GrantPrincipal{
			GranteeType: GranteeUser,
			GranteeID:   uid,
		})
	}

	replyOK(w, ListGrantPrincipalsResponse{
		Users:  userOut,
		Groups: groupOut,
	})
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
