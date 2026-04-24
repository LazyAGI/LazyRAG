package orm

// 词条在词表中的角色（与 UI「术语 / 别名」对应）。
const (
	WordKindTerm  = "term"  // 术语
	WordKindAlias = "alias" // 别名
)

// Word stores vocabulary / glossary rows (word, sense group, provenance).
type Word struct {
	ID            string `gorm:"column:id;type:varchar(64);primaryKey"`
	Word          string `gorm:"column:word;type:varchar(512);not null;index:idx_word_column;index:idx_word_group_word_kind,priority:2"`
	WordKind      string `gorm:"column:word_kind;type:varchar(32);not null;default:'term';index:idx_word_group_word_kind,priority:3"` // term | alias
	GroupID       string `gorm:"column:group_id;type:varchar(64);not null;index:idx_word_group_word_kind,priority:1"`
	Description   string `gorm:"column:description;type:varchar(512);not null;default:''"`
	Source        string `gorm:"column:source;type:varchar(32);not null;default:'user'"` // user | ai
	ReferenceInfo string `gorm:"column:reference_info;type:text;not null;default:''"`
	Locked        bool   `gorm:"column:locked;type:boolean;not null;default:false"`

	BaseModel
}

func (Word) TableName() string { return "words" }
