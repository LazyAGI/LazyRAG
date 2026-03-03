package orm

import "time"

// VisibilityModel stores visibility level for a resource (e.g. kb).
type VisibilityModel struct {
	ID         int64  `gorm:"primaryKey;autoIncrement"`
	ResourceID string `gorm:"column:resource_id;type:varchar(255);index"`
	Level      string `gorm:"column:level;type:varchar(32)"`
}

func (VisibilityModel) TableName() string { return "acl_visibility" }

// ACLModel stores ACL entries for resources.
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

// KBModel stores KB metadata.
type KBModel struct {
	ID         string `gorm:"primaryKey;column:id;type:varchar(64)"`
	Name       string `gorm:"column:name;type:varchar(255)"`
	OwnerID    int64  `gorm:"column:owner_id"`
	Visibility string `gorm:"column:visibility;type:varchar(32)"`
}

func (KBModel) TableName() string { return "acl_kbs" }

// UserGroupModel stores user -> group/tenant mapping for ACL.
type UserGroupModel struct {
	UserID  int64 `gorm:"primaryKey;column:user_id"`
	GroupID int64 `gorm:"primaryKey;column:group_id"`
}

func (UserGroupModel) TableName() string { return "acl_user_groups" }
