package orm

import (
	"encoding/json"
	"time"
)

type SkillResource struct {
	ID                 string          `gorm:"column:id;type:varchar(36);primaryKey"`
	OwnerUserID        string          `gorm:"column:owner_user_id;type:varchar(255);not null;index:idx_skill_resources_owner_node_enabled,priority:1;uniqueIndex:uk_skill_resources_owner_relative_path,priority:1"`
	OwnerUserName      string          `gorm:"column:owner_user_name;type:varchar(255);not null;default:''"`
	Category           string          `gorm:"column:category;type:varchar(128);not null;index:idx_skill_resources_owner_node_enabled,priority:4"`
	ParentSkillName    string          `gorm:"column:parent_skill_name;type:varchar(255);not null;default:''"`
	SkillName          string          `gorm:"column:skill_name;type:varchar(255);not null;default:''"`
	NodeType           string          `gorm:"column:node_type;type:varchar(32);not null;index:idx_skill_resources_owner_node_enabled,priority:2"`
	Description        string          `gorm:"column:description;type:text"`
	Tags               json.RawMessage `gorm:"column:tags;type:json"`
	FileExt            string          `gorm:"column:file_ext;type:varchar(32);not null;default:'md'"`
	RelativePath       string          `gorm:"column:relative_path;type:varchar(1024);not null;uniqueIndex:uk_skill_resources_owner_relative_path,priority:2"`
	StoragePath        string          `gorm:"column:storage_path;type:text;not null;default:''"`
	Content            string          `gorm:"column:content;type:text;not null;default:''"`
	ContentSize        int64           `gorm:"column:content_size;not null;default:0"`
	MimeType           string          `gorm:"column:mime_type;type:varchar(128);not null;default:'text/plain; charset=utf-8'"`
	ContentHash        string          `gorm:"column:content_hash;type:varchar(64);not null;default:''"`
	Version            int64           `gorm:"column:version;not null;default:1"`
	DraftContent       string          `gorm:"column:draft_content;type:text;not null;default:''"`
	DraftSourceVersion int64           `gorm:"column:draft_source_version;not null;default:0"`
	DraftStatus        string          `gorm:"column:draft_status;type:varchar(32);not null;default:''"`
	DraftUpdatedAt     *time.Time      `gorm:"column:draft_updated_at"`
	IsLocked           bool            `gorm:"column:is_locked;not null;default:false"`
	IsEnabled          bool            `gorm:"column:is_enabled;not null;default:true;index:idx_skill_resources_owner_node_enabled,priority:3"`
	UpdateStatus       string          `gorm:"column:update_status;type:varchar(32);not null;default:'up_to_date'"`
	Ext                json.RawMessage `gorm:"column:ext;type:json"`
	CreateUserID       string          `gorm:"column:create_user_id;type:varchar(255);not null"`
	CreateUserName     string          `gorm:"column:create_user_name;type:varchar(255);not null;default:''"`
	CreatedAt          time.Time       `gorm:"column:created_at;not null"`
	UpdatedAt          time.Time       `gorm:"column:updated_at;not null"`
}

func (SkillResource) TableName() string { return "skill_resources" }
