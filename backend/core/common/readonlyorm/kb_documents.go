package readonlyorm

import "time"

// LazyLLMKBDocRow maps to schema-B table: lazyllm_kb_documents
type LazyLLMKBDocRow struct {
	ID        int       `gorm:"column:id;primaryKey;autoIncrement"`
	KbID      string    `gorm:"column:kb_id;type:varchar(255);not null"`
	DocID     string    `gorm:"column:doc_id;type:varchar(128);not null"`
	CreatedAt time.Time `gorm:"column:created_at;not null"`
	UpdatedAt time.Time `gorm:"column:updated_at;not null"`
}

func (LazyLLMKBDocRow) TableName() string { return Table(LazyLLMSchema(), "lazyllm_kb_documents") }
