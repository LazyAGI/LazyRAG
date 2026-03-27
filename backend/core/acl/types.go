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
	GranteeGroup  = "group"
	GranteeTenant = "tenant" // 兼容旧值，等同 group
)

// 通用权限动作（兼容旧逻辑与通用鉴权调用）。
const (
	PermNone   = "none"
	PermRead   = "read"
	PermWrite  = "write"
	PermUpload = "upload"
)

// 具体权限种类。
const (
	PermissionKBRead      = "KB_READ"
	PermissionKBWrite     = "KB_WRITE"
	PermissionKBCreateDoc = "KB_CREATE_DOC"
	PermissionKBDeleteDoc = "KB_DELETE_DOC"
	PermissionKBDelete    = "KB_DELETE"

	PermissionDatasetRead   = "DATASET_READ"
	PermissionDatasetWrite  = "DATASET_WRITE"
	PermissionDatasetUpload = "DATASET_UPLOAD"
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
	GranteeType  string     `json:"grantee_type"`  // user / group
	TargetID     string     `json:"target_id"`     // user_id 或 group_id
	Permission   string     `json:"permission"`    // KB_READ / DATASET_WRITE / ...
	CreatedBy    string     `json:"created_by"`
	CreatedAt    time.Time  `json:"created_at"`
	ExpiresAt    *time.Time `json:"expires_at,omitempty"`
}

// ACLListItem 列表接口返回项（API 中 grantee_id 即库中 target_id）。
type ACLListItem struct {
	ID          int64     `json:"id"`
	GranteeType string    `json:"grantee_type"`
	GranteeID   string    `json:"grantee_id"`
	Permission  string    `json:"permission"`
	CreatedAt   time.Time `json:"created_at"`
}

// KBInfo 知识库最小元数据，用于列表与归属校验。
type KBInfo struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	OwnerID    string `json:"owner_id"`
	Visibility string `json:"visibility"`
}

// --- API 请求/响应 DTO ---

// AddACLRequest 对应 POST /api/kb/{kb_id}/acl 请求体
type AddACLRequest struct {
	GranteeType string     `json:"grantee_type"` // user / group（兼容 tenant）
	GranteeID   string     `json:"grantee_id"`
	Permission  string     `json:"permission"`   // 兼容 read/write，也支持 KB_READ / DATASET_WRITE / ...
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
	GranteeID   string `json:"grantee_id"`
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
	Permissions []string `json:"permissions"`
	Source      string   `json:"source"` // public / protected / owner / acl
}

// PermissionBatchItem 对应 POST /api/kb/permission/batch 单项
type PermissionBatchItem struct {
	KbID        string   `json:"kb_id"`
	Permissions []string `json:"permissions"`
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
	ID          string   `json:"id"`
	Name        string   `json:"name"`
	Visibility  string   `json:"visibility"`
	Permissions []string `json:"permissions"`
}

type GroupInfo struct {
	ID        string `json:"id"`
	Name      string `json:"name"`
	UserCount int64  `json:"user_count,omitempty"`
}

type GroupMember struct {
	UserID string `json:"user_id"`
}

type CreateGroupRequest struct {
	ID   string `json:"id,omitempty"`
	Name string `json:"name,omitempty"`
}

type AddGroupUserRequest struct {
	UserID string `json:"user_id"`
}

type ListGroupsResponse struct {
	Groups []GroupInfo `json:"groups"`
}

type ListGroupUsersResponse struct {
	Users []GroupMember `json:"users"`
}

// --- Authorization page DTOs ---

// AuthorizationSubjectGrant describes one grantee (user/group) and all permissions granted on a KB.
type AuthorizationSubjectGrant struct {
	GranteeType string   `json:"grantee_type"` // user / group
	GranteeID   string   `json:"grantee_id"`
	Permissions []string `json:"permissions"`
}

// GetKBAuthorizationResponse is used by the authorization page to render current grants.
type GetKBAuthorizationResponse struct {
	KbID   string                      `json:"kb_id"`
	Grants []AuthorizationSubjectGrant `json:"grants"`
}

// SetKBAuthorizationRequest replaces ACL grants of a KB with the submitted grants.
type SetKBAuthorizationRequest struct {
	Grants []AuthorizationSubjectGrant `json:"grants"`
}

// GrantPrincipal represents a selectable user/group in authorization UI.
type GrantPrincipal struct {
	GranteeType string `json:"grantee_type"` // user / group
	GranteeID   string `json:"grantee_id"`
	Name        string `json:"name,omitempty"`
}

type ListGrantPrincipalsResponse struct {
	Users  []GrantPrincipal `json:"users"`
	Groups []GrantPrincipal `json:"groups"`
}
