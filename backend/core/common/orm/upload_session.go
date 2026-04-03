package orm

import "encoding/json"

// UploadSession task_id / document_id reference core tasks.id and documents.id (varchar(128));
// dataset_id aligns with datasets.id (varchar(255)); tenant_id with datasets.tenant_id (varchar(36)).
type UploadSession struct {
	ID       int64  `gorm:"column:id;primaryKey;autoIncrement"`
	UploadID string `gorm:"column:upload_id;type:varchar(128);not null;uniqueIndex"`
	TaskID   string `gorm:"column:task_id;type:varchar(128);not null;index"`

	DatasetID  string `gorm:"column:dataset_id;type:varchar(255);not null;index"`
	TenantID   string `gorm:"column:tenant_id;type:varchar(36);not null;index"`
	DocumentID string `gorm:"column:document_id;type:varchar(128);not null;index"`

	UploadState string          `gorm:"column:upload_state;type:varchar(64);not null;default:'';index"`
	Ext         json.RawMessage `gorm:"column:ext;type:json"`

	BaseModel
}

func (UploadSession) TableName() string { return "upload_sessions" }
