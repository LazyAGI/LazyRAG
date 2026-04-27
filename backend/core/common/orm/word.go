package orm

import "time"

// 词条在词表中的角色（与 UI「术语 / 别名」对应）。
const (
	WordKindTerm  = "term"  // 术语
	WordKindAlias = "alias" // 别名
)

// WordBase is the audit column set for words; CreateUserID leads composite indexes (user-scoped).
type WordBase struct {
	CreateUserID   string     `gorm:"column:create_user_id;type:varchar(255);not null;index:idx_word_column,priority:1;index:idx_word_create_user_group_id,priority:1"`
	CreateUserName string     `gorm:"column:create_user_name;type:varchar(255);not null"`
	CreatedAt      time.Time  `gorm:"column:created_at;not null"`
	UpdatedAt      time.Time  `gorm:"column:updated_at;not null"`
	DeletedAt      *time.Time `gorm:"column:deleted_at"`
}

// Word stores vocabulary / glossary rows (word, sense group, provenance).
type Word struct {
	ID            string `gorm:"column:id;type:varchar(64);primaryKey"`
	Word          string `gorm:"column:word;type:varchar(512);not null;index:idx_word_column,priority:2"`
	WordKind      string `gorm:"column:word_kind;type:varchar(32);not null;default:'term'"` // term | alias
	GroupID       string `gorm:"column:group_id;type:varchar(64);not null;index:idx_word_create_user_group_id,priority:2"`
	Description   string `gorm:"column:description;type:varchar(512);not null;default:''"`
	Source        string `gorm:"column:source;type:varchar(32);not null;default:'user'"` // user | ai
	ReferenceInfo string `gorm:"column:reference_info;type:text;not null;default:''"`
	Locked        bool   `gorm:"column:locked;type:boolean;not null;default:false"`

	WordBase
}

func (Word) TableName() string { return "words" }
