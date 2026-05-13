package orm

import (
	"encoding/json"
	"time"
)

type ResourceSessionSnapshot struct {
	ID              string    `gorm:"column:id;type:varchar(36);primaryKey"`
	SessionID       string    `gorm:"column:session_id;type:varchar(128);not null;uniqueIndex:uk_resource_session_snapshots,priority:1;index:idx_resource_session_snapshots_session_id"`
	UserID          string    `gorm:"column:user_id;type:varchar(255);not null;default:''"`
	ResourceType    string    `gorm:"column:resource_type;type:varchar(32);not null;uniqueIndex:uk_resource_session_snapshots,priority:2"`
	ResourceKey     string    `gorm:"column:resource_key;type:varchar(1024);not null;uniqueIndex:uk_resource_session_snapshots,priority:3"`
	Category        string    `gorm:"column:category;type:varchar(128);not null;default:''"`
	ParentSkillName string    `gorm:"column:parent_skill_name;type:varchar(255);not null;default:''"`
	SkillName       string    `gorm:"column:skill_name;type:varchar(255);not null;default:''"`
	FileExt         string    `gorm:"column:file_ext;type:varchar(32);not null;default:''"`
	RelativePath    string    `gorm:"column:relative_path;type:varchar(1024);not null;default:''"`
	SnapshotHash    string    `gorm:"column:snapshot_hash;type:varchar(64);not null;default:''"`
	CreatedAt       time.Time `gorm:"column:created_at;not null"`
}

func (ResourceSessionSnapshot) TableName() string { return "resource_session_snapshots" }

type ResourceSuggestion struct {
	ID              string          `gorm:"column:id;type:varchar(36);primaryKey"`
	UserID          string          `gorm:"column:user_id;type:varchar(255);not null;default:'';index:idx_resource_suggestions_list,priority:1"`
	ResourceType    string          `gorm:"column:resource_type;type:varchar(32);not null;index:idx_resource_suggestions_list,priority:2"`
	ResourceKey     string          `gorm:"column:resource_key;type:varchar(1024);not null;default:''"`
	Category        string          `gorm:"column:category;type:varchar(128);not null;default:''"`
	ParentSkillName string          `gorm:"column:parent_skill_name;type:varchar(255);not null;default:''"`
	SkillName       string          `gorm:"column:skill_name;type:varchar(255);not null;default:''"`
	FileExt         string          `gorm:"column:file_ext;type:varchar(32);not null;default:''"`
	RelativePath    string          `gorm:"column:relative_path;type:varchar(1024);not null;default:''"`
	Action          string          `gorm:"column:action;type:varchar(32);not null"`
	SessionID       string          `gorm:"column:session_id;type:varchar(128);not null;index:idx_resource_suggestions_session_id"`
	SnapshotHash    string          `gorm:"column:snapshot_hash;type:varchar(64);not null;default:''"`
	Title           string          `gorm:"column:title;type:varchar(255);not null;default:''"`
	Content         string          `gorm:"column:content;type:text"`
	Reason          string          `gorm:"column:reason;type:text"`
	FullContent     string          `gorm:"column:full_content;type:text"`
	Status          string          `gorm:"column:status;type:varchar(32);not null;index:idx_resource_suggestions_list,priority:3"`
	InvalidReason   string          `gorm:"column:invalid_reason;type:text"`
	ReviewerID      string          `gorm:"column:reviewer_id;type:varchar(255);not null;default:''"`
	ReviewerName    string          `gorm:"column:reviewer_name;type:varchar(255);not null;default:''"`
	ReviewedAt      *time.Time      `gorm:"column:reviewed_at"`
	Ext             json.RawMessage `gorm:"column:ext;type:json"`
	CreatedAt       time.Time       `gorm:"column:created_at;not null"`
	UpdatedAt       time.Time       `gorm:"column:updated_at;not null"`
}

func (ResourceSuggestion) TableName() string { return "resource_suggestions" }
