package orm

import "time"

type UserPersonalizationSetting struct {
	ID            int64     `gorm:"column:id;primaryKey;autoIncrement"`
	UserID        string    `gorm:"column:user_id;type:varchar(255);not null;uniqueIndex:uk_user_personalization_settings_user_id"`
	Enabled       bool      `gorm:"column:enabled;not null;default:true"`
	UpdatedBy     string    `gorm:"column:updated_by;type:varchar(255);not null;default:''"`
	UpdatedByName string    `gorm:"column:updated_by_name;type:varchar(255);not null;default:''"`
	CreatedAt     time.Time `gorm:"column:created_at;not null"`
	UpdatedAt     time.Time `gorm:"column:updated_at;not null"`
}

func (UserPersonalizationSetting) TableName() string { return "user_personalization_settings" }
