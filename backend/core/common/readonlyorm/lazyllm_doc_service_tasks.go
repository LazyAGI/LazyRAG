package readonlyorm

import "time"

// LazyLLMDocServiceTaskRow maps to schema-B table: lazyllm_doc_service_tasks.
// algo_id was removed from this table in the node-group refactor (wzh/doc_sig).
type LazyLLMDocServiceTaskRow struct {
	ID         int        `gorm:"column:id;primaryKey;autoIncrement"`
	TaskID     string     `gorm:"column:task_id;type:varchar(128);not null"`
	TaskType   string     `gorm:"column:task_type;type:varchar(128);not null"`
	DocID      string     `gorm:"column:doc_id;type:varchar(128);not null"`
	KbID       string     `gorm:"column:kb_id;type:varchar(255);not null"`
	Status     string     `gorm:"column:status;type:varchar(64);not null"`
	Message    *string    `gorm:"column:message;type:text"`
	ErrorCode  *string    `gorm:"column:error_code;type:varchar(64)"`
	ErrorMsg   *string    `gorm:"column:error_msg;type:text"`
	CreatedAt  time.Time  `gorm:"column:created_at;not null"`
	UpdatedAt  time.Time  `gorm:"column:updated_at;not null"`
	StartedAt  *time.Time `gorm:"column:started_at"`
	FinishedAt *time.Time `gorm:"column:finished_at"`
}

func (LazyLLMDocServiceTaskRow) TableName() string {
	return Table(LazyLLMSchema(), "lazyllm_doc_service_tasks")
}
