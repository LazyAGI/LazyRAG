package orm

import "time"

// BaseModel 表通用字段：创建人、时间与软删，与 neutrino ent CommonMixin 对齐。
// 需要 create_user_id / create_user_name / created_at / updated_at / deleted_at 的表可内嵌此结构体。
type BaseModel struct {
	CreateUserID   string     `gorm:"column:create_user_id;type:varchar(255);not null"`
	CreateUserName string     `gorm:"column:create_user_name;type:varchar(255);not null"`
	CreatedAt      time.Time  `gorm:"column:created_at;not null"`
	UpdatedAt      time.Time  `gorm:"column:updated_at;not null"`
	DeletedAt      *time.Time `gorm:"column:deleted_at"`
}

// TimeMixin 仅含 create_time / update_time，与 neutrino ent BaseMixin 对齐。
// 用于 chat_histories 等仅需时间戳的表。
type TimeMixin struct {
	CreateTime time.Time `gorm:"column:create_time;not null"`
	UpdateTime time.Time `gorm:"column:update_time;not null"`
}
