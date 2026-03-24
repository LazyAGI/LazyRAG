package readonlyorm

import "time"

// LazyLLMDocRow maps to schema-B table: lazyllm_documents
// String column sizes align with typical lazy-llm-server DDL (ids/path vs long text).
type LazyLLMDocRow struct {
	DocID        string    `gorm:"column:doc_id;type:varchar(128);primaryKey"`
	Filename     string    `gorm:"column:filename;type:varchar(512);not null"`
	Path         string    `gorm:"column:path;type:varchar(4096);not null"`
	Meta         *string   `gorm:"column:meta;type:text"`
	UploadStatus string    `gorm:"column:upload_status;type:varchar(64);not null"`
	SourceType   string    `gorm:"column:source_type;type:varchar(64);not null"`
	FileType     *string   `gorm:"column:file_type;type:varchar(64)"`
	ContentHash  *string   `gorm:"column:content_hash;type:varchar(128)"`
	SizeBytes    *int      `gorm:"column:size_bytes"`
	CreatedAt    time.Time `gorm:"column:created_at;not null"`
	UpdatedAt    time.Time `gorm:"column:updated_at;not null"`
}

func (LazyLLMDocRow) TableName() string { return Table(LazyLLMSchema(), "lazyllm_documents") }
