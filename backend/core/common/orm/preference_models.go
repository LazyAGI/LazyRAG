package orm

import (
	"encoding/json"
	"time"
)

type SystemUserPreference struct {
	ID                 string          `gorm:"column:id;type:varchar(36);primaryKey"`
	UserID             string          `gorm:"column:user_id;type:varchar(255);not null;default:'';uniqueIndex:uk_system_user_preferences_user_id"`
	Content            string          `gorm:"column:content;type:text;not null;default:''"`
	ContentHash        string          `gorm:"column:content_hash;type:varchar(64);not null;default:''"`
	Version            int64           `gorm:"column:version;not null;default:1"`
	DraftContent       string          `gorm:"column:draft_content;type:text"`
	DraftSourceVersion int64           `gorm:"column:draft_source_version;not null;default:0"`
	DraftStatus        string          `gorm:"column:draft_status;type:varchar(32);not null;default:''"`
	DraftUpdatedAt     *time.Time      `gorm:"column:draft_updated_at"`
	Ext                json.RawMessage `gorm:"column:ext;type:json"`
	UpdatedBy          string          `gorm:"column:updated_by;type:varchar(255);not null;default:''"`
	UpdatedByName      string          `gorm:"column:updated_by_name;type:varchar(255);not null;default:''"`
	CreatedAt          time.Time       `gorm:"column:created_at;not null"`
	UpdatedAt          time.Time       `gorm:"column:updated_at;not null"`
}

func (SystemUserPreference) TableName() string { return "system_user_preferences" }
