package acl

import "time"

// 知识库可见级别（读权限）。
const (
	VisibilityPublic    = "public"    // 所有人可读
	VisibilityProtected = "protected" // 仅 ACL/所有者可读
	VisibilityPrivate   = "private"   // 仅所有者与 ACL
)

// ACL 授权对象类型。
const (
	GranteeUser   = "user"
	GranteeTenant = "tenant"
)

// 权限级别。
const (
	PermNone  = "none"
	PermRead  = "read"
	PermWrite = "write"
)

// 权限来源（用于审计）。
const (
	SourceOwner     = "owner"
	SourcePublic    = "public"
	SourceProtected = "protected"
	SourceACL       = "acl"
)

// ACL 资源类型。
const (
	ResourceTypeKB = "kb" // 知识库
	ResourceTypeDB = "db" // 数据库
)

// VisibilityRow 与可见性表对应：id、resource_id(kb_id)、level（缺省为 private）。
type VisibilityRow struct {
	ID         int64  `json:"id"`
	ResourceID string `json:"resource_id"` // kb 资源为 kb_id
	Level      string `json:"level"`       // public / protected / private
}

// ACLRow 与 ACL 表对应，适用于 kb 与 db 资源。
type ACLRow struct {
	ID           int64      `json:"id"`
	ResourceType string     `json:"resource_type"` // kb / db
	ResourceID   string     `json:"resource_id"`   // kb_id 或 db_id
	GranteeType  string     `json:"grantee_type"`  // user / tenant
	TargetID     int64      `json:"target_id"`     // user_id 或 tenant_id
	Permission   string     `json:"permission"`    // read / write
	CreatedBy    int64      `json:"created_by"`
	CreatedAt    time.Time  `json:"created_at"`
	ExpiresAt    *time.Time `json:"expires_at,omitempty"`
}

// ACLListItem 列表接口返回项（API 中 grantee_id 即库中 target_id）。
type ACLListItem struct {
	ID          int64     `json:"id"`
	GranteeType string    `json:"grantee_type"`
	GranteeID   int64     `json:"grantee_id"`
	Permission  string    `json:"permission"`
	CreatedAt   time.Time `json:"created_at"`
}

// KBInfo 知识库最小元数据，用于列表与归属校验。
type KBInfo struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	OwnerID    int64  `json:"owner_id"`
	Visibility string `json:"visibility"`
}

// --- API 请求/响应 DTO ---

// AddACLRequest 对应 POST /api/kb/{kb_id}/acl 请求体
type AddACLRequest struct {
	GranteeType string     `json:"grantee_type"` // user / tenant
	GranteeID   int64      `json:"grantee_id"`
	Permission  string     `json:"permission"` // read / write
	ExpiresAt   *time.Time `json:"expires_at,omitempty"`
}

// UpdateACLRequest 对应 PUT /api/kb/{kb_id}/acl/{acl_id} 请求体
type UpdateACLRequest struct {
	Permission string     `json:"permission"`
	ExpiresAt  *time.Time `json:"expires_at,omitempty"`
}

// BatchAddACLRequest 对应 POST /api/kb/{kb_id}/acl/batch 请求体
type BatchAddACLRequest struct {
	Items []BatchAddACLItem `json:"items"`
}

type BatchAddACLItem struct {
	GranteeType string `json:"grantee_type"`
	GranteeID   int64  `json:"grantee_id"`
	Permission  string `json:"permission"`
}

// PermissionBatchRequest 对应 POST /api/kb/permission/batch 请求体
type PermissionBatchRequest struct {
	KbIDs []string `json:"kb_ids"`
}

// APIResponse 接口统一响应外壳：{ code, message, data }
type APIResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    any    `json:"data,omitempty"`
}

// PermissionResult 对应 GET /api/kb/{kb_id}/permission
type PermissionResult struct {
	Permission string `json:"permission"` // none / read / write
	Source     string `json:"source"`     // public / protected / owner / acl
}

// PermissionBatchItem 对应 POST /api/kb/permission/batch 单项
type PermissionBatchItem struct {
	KbID       string `json:"kb_id"`
	Permission string `json:"permission"`
}

// CanResult 对应 GET /api/kb/{kb_id}/can
type CanResult struct {
	Allowed bool `json:"allowed"`
}

// KBListResult 对应 GET /api/kb/list
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
