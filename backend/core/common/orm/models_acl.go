package orm

import "time"

// VisibilityModel 资源（如 kb）可见级别。
type VisibilityModel struct {
	ID         int64  `gorm:"primaryKey;autoIncrement"`
	ResourceID string `gorm:"column:resource_id;type:varchar(255);index"`
	Level      string `gorm:"column:level;type:varchar(32)"`
}

func (VisibilityModel) TableName() string { return "acl_visibility" }

// ACLModel ACL 行记录。
type ACLModel struct {
	ID           int64      `gorm:"primaryKey;autoIncrement"`
	ResourceType string     `gorm:"column:resource_type;type:varchar(32);index:idx_acl_resource,priority:1"`
	ResourceID   string     `gorm:"column:resource_id;type:varchar(255);index:idx_acl_resource,priority:2"`
	GranteeType  string     `gorm:"column:grantee_type;type:varchar(32)"`
	TargetID     int64      `gorm:"column:target_id"`
	Permission   string     `gorm:"column:permission;type:varchar(32)"`
	CreatedBy    int64      `gorm:"column:created_by"`
	CreatedAt    time.Time  `gorm:"column:created_at"`
	ExpiresAt    *time.Time `gorm:"column:expires_at"`
}

func (ACLModel) TableName() string { return "acl_rows" }

// KBModel 知识库元数据。
type KBModel struct {
	ID         string `gorm:"primaryKey;column:id;type:varchar(64)"`
	Name       string `gorm:"column:name;type:varchar(255)"`
	OwnerID    int64  `gorm:"column:owner_id"`
	Visibility string `gorm:"column:visibility;type:varchar(32)"`
}

func (KBModel) TableName() string { return "acl_kbs" }

// UserGroupModel 用户与组/租户映射。
type UserGroupModel struct {
	UserID  int64 `gorm:"primaryKey;column:user_id"`
	GroupID int64 `gorm:"primaryKey;column:group_id"`
}

func (UserGroupModel) TableName() string { return "acl_user_groups" }
