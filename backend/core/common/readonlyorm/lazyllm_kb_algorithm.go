package readonlyorm

import "time"

// LazyLLMKBAlgorithmRow maps to schema-B table: lazyllm_kb_algorithm.
// After the node-group refactor a KB may be bound to multiple algos, so this
// table has a composite unique key (kb_id, algo_id) rather than a unique key
// on kb_id alone.
type LazyLLMKBAlgorithmRow struct {
	ID        int       `gorm:"column:id;primaryKey;autoIncrement"`
	KbID      string    `gorm:"column:kb_id;type:varchar(255);not null"`
	AlgoID    string    `gorm:"column:algo_id;type:varchar(255);not null"`
	CreatedAt time.Time `gorm:"column:created_at;not null"`
	UpdatedAt time.Time `gorm:"column:updated_at;not null"`
}

func (LazyLLMKBAlgorithmRow) TableName() string {
	return Table(LazyLLMSchema(), "lazyllm_kb_algorithm")
}
