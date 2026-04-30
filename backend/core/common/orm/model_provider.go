package orm

import "time"

// DefaultModelProvider is the built-in catalog of AI model providers (name, description, default base URL).
type DefaultModelProvider struct {
	ID          string     `gorm:"column:id;type:varchar(64);primaryKey"`
	Name        string     `gorm:"column:name;type:varchar(255);not null;uniqueIndex:uk_default_model_providers_name"`
	Description string     `gorm:"column:description;type:text;not null"`
	BaseURL     string     `gorm:"column:base_url;type:varchar(1024);not null;default:''"`
	CreatedAt   time.Time  `gorm:"column:created_at;not null"`
	UpdatedAt   time.Time  `gorm:"column:updated_at;not null"`
	DeletedAt   *time.Time `gorm:"column:deleted_at"`
}

func (DefaultModelProvider) TableName() string { return "default_model_providers" }

// UserModelProvider is a per-user copy of catalog providers (seeded from DefaultModelProvider).
// DefaultModelProviderID is the DefaultModelProvider.ID the row was copied from.
type UserModelProvider struct {
	ID                     string `gorm:"column:id;type:varchar(64);primaryKey"`
	DefaultModelProviderID string `gorm:"column:default_model_provider_id;type:varchar(64);not null"`
	Name                   string `gorm:"column:name;type:varchar(255);not null"`
	Description            string `gorm:"column:description;type:text;not null"`
	BaseURL                string `gorm:"column:base_url;type:varchar(1024);not null;default:''"`
	BaseModel
}

func (UserModelProvider) TableName() string { return "user_model_providers" }
