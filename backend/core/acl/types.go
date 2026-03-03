package acl

import "time"

// Visibility level for a knowledge base (read visibility).
const (
	VisibilityPublic    = "public"    // anyone can read
	VisibilityProtected = "protected" // only ACL/owner can read
	VisibilityPrivate   = "private"   // only owner and ACL
)

// GranteeType for ACL target.
const (
	GranteeUser   = "user"
	GranteeTenant = "tenant"
)

// Permission level.
const (
	PermNone  = "none"
	PermRead  = "read"
	PermWrite = "write"
)

// Permission source for audit.
const (
	SourceOwner     = "owner"
	SourcePublic    = "public"
	SourceProtected = "protected"
	SourceACL       = "acl"
)

// ResourceType for ACL.
const (
	ResourceTypeKB = "kb" // knowledge base
	ResourceTypeDB = "db" // database
)

// VisibilityRow matches visibility table: id, kb_id, level (default private if missing).
type VisibilityRow struct {
	ID         int64  `json:"id"`
	ResourceID string `json:"resource_id"` // kb_id for kb resources
	Level      string `json:"level"`       // public / protected / private
}

// ACLRow matches ACL table. Generic for kb and db resources.
type ACLRow struct {
	ID           int64      `json:"id"`
	ResourceType string     `json:"resource_type"` // kb / db
	ResourceID   string     `json:"resource_id"`   // kb_id or db_id
	GranteeType  string     `json:"grantee_type"`  // user / tenant
	TargetID     int64      `json:"target_id"`     // user_id or tenant_id
	Permission   string     `json:"permission"`    // read / write
	CreatedBy    int64      `json:"created_by"`
	CreatedAt    time.Time  `json:"created_at"`
	ExpiresAt    *time.Time `json:"expires_at,omitempty"`
}

// ACLListItem for list response (grantee_id in API = target_id in DB).
type ACLListItem struct {
	ID          int64     `json:"id"`
	GranteeType string    `json:"grantee_type"`
	GranteeID   int64     `json:"grantee_id"`
	Permission  string    `json:"permission"`
	CreatedAt   time.Time `json:"created_at"`
}

// KBInfo minimal KB metadata for list and owner check.
type KBInfo struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	OwnerID    int64  `json:"owner_id"`
	Visibility string `json:"visibility"`
}

// --- API request/response DTOs ---

// AddACLRequest body for POST /api/kb/{kb_id}/acl
type AddACLRequest struct {
	GranteeType string     `json:"grantee_type"` // user / tenant
	GranteeID   int64      `json:"grantee_id"`
	Permission  string     `json:"permission"` // read / write
	ExpiresAt   *time.Time `json:"expires_at,omitempty"`
}

// UpdateACLRequest body for PUT /api/kb/{kb_id}/acl/{acl_id}
type UpdateACLRequest struct {
	Permission string     `json:"permission"`
	ExpiresAt  *time.Time `json:"expires_at,omitempty"`
}

// BatchAddACLRequest body for POST /api/kb/{kb_id}/acl/batch
type BatchAddACLRequest struct {
	Items []BatchAddACLItem `json:"items"`
}

type BatchAddACLItem struct {
	GranteeType string `json:"grantee_type"`
	GranteeID   int64  `json:"grantee_id"`
	Permission  string `json:"permission"`
}

// PermissionBatchRequest body for POST /api/kb/permission/batch
type PermissionBatchRequest struct {
	KbIDs []string `json:"kb_ids"`
}

// API response envelope: { code, message, data }
type APIResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    any    `json:"data,omitempty"`
}

// PermissionResult for GET /api/kb/{kb_id}/permission
type PermissionResult struct {
	Permission string `json:"permission"` // none / read / write
	Source     string `json:"source"`     // public / protected / owner / acl
}

// PermissionBatchItem for POST /api/kb/permission/batch
type PermissionBatchItem struct {
	KbID       string `json:"kb_id"`
	Permission string `json:"permission"`
}

// CanResult for GET /api/kb/{kb_id}/can
type CanResult struct {
	Allowed bool `json:"allowed"`
}

// KBListResult for GET /api/kb/list
type KBListResult struct {
	Total int64       `json:"total"`
	List  []KBListRow `json:"list"`
}

type KBListRow struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	Visibility string `json:"visibility"`
	Permission string `json:"permission"`
}
