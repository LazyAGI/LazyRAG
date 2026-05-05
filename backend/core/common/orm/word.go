package orm

import "time"

// Role of a word in the vocabulary, matching the UI term or alias concepts.
const (
	WordKindTerm  = "term"  // term
	WordKindAlias = "alias" // alias
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

// WordGroupConflict stores ambiguous synonym assignment cases for later manual resolution.
type WordGroupConflict struct {
	ID           string     `gorm:"column:id;type:varchar(64);primaryKey"`
	Reason       string     `gorm:"column:reason;type:text;not null;default:''"`
	Word         string     `gorm:"column:word;type:text;not null;default:''"`
	Description  string     `gorm:"column:description;type:text;not null;default:''"`
	GroupIDs     string     `gorm:"column:group_ids;type:text;not null;default:'[]'"` // JSON-serialized []string
	CreateUserID string     `gorm:"column:create_user_id;type:varchar(255);not null;index:idx_word_group_conflict_user_updated,priority:1"`
	MessageIDs   string     `gorm:"column:message_ids;type:text;not null;default:'[]'"` // JSON-serialized []string
	CreatedAt    time.Time  `gorm:"column:created_at;not null"`
	UpdatedAt    time.Time  `gorm:"column:updated_at;not null;index:idx_word_group_conflict_user_updated,priority:2,sort:desc"`
	DeletedAt    *time.Time `gorm:"column:deleted_at"`
}

func (WordGroupConflict) TableName() string { return "word_group_conflicts" }
