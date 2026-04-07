package orm

import "encoding/json"

// Task is the Core-maintained diff table for document service tasks (original “jobs/tasks” concept).
// It stores only fields that Core needs to own; the base fields are read from schema-B (lazy_llm_server).
//
// ID is the Core resource id (API task_id / path {task}).
// LazyllmTaskID matches readonlyorm.LazyLLMDocServiceTaskRow.TaskID.
// DocID references documents.id — same varchar(128) as Document.ID.
// KbID / AlgoID / DatasetID align with readonlyorm lazyllm_doc_service_tasks and datasets (varchar(255)).
type Task struct {
	ID            string `gorm:"column:id;type:varchar(128);primaryKey"`
	LazyllmTaskID string `gorm:"column:lazyllm_task_id;type:varchar(128);not null;default:'';index"`

	DocID  string `gorm:"column:doc_id;type:varchar(128);index"`
	KbID   string `gorm:"column:kb_id;type:varchar(255);index"`
	AlgoID string `gorm:"column:algo_id;type:varchar(255);index"`

	DatasetID       string `gorm:"column:dataset_id;type:varchar(255);not null;index"`
	TaskType        string `gorm:"column:task_type;type:varchar(128);not null;default:'';index"`
	DocumentPID     string `gorm:"column:document_pid;type:varchar(255);not null;default:'';index"`
	TargetPID       string `gorm:"column:target_pid;type:varchar(255);not null;default:''"`
	TargetDatasetID string `gorm:"column:target_dataset_id;type:varchar(255);not null;default:'';index"`
	DisplayName     string `gorm:"column:display_name;type:varchar(512);not null;default:''"`

	Ext json.RawMessage `gorm:"column:ext;type:json"`

	BaseModel
}

func (Task) TableName() string { return "tasks" }
