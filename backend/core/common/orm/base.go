package orm

import "time"

// BaseModel
// text create_user_id / create_user_name / created_at / updated_at / deleted_at text。
type BaseModel struct {
	CreateUserID   string     `gorm:"column:create_user_id;type:varchar(255);not null"`
	CreateUserName string     `gorm:"column:create_user_name;type:varchar(255);not null"`
	CreatedAt      time.Time  `gorm:"column:created_at;not null"`
	UpdatedAt      time.Time  `gorm:"column:updated_at;not null"`
	DeletedAt      *time.Time `gorm:"column:deleted_at"`
}

// TimeMixin
// text chat_histories text。
type TimeMixin struct {
	CreateTime time.Time `gorm:"column:create_time;not null"`
	UpdateTime time.Time `gorm:"column:update_time;not null"`
}
