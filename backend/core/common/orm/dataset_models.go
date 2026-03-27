package orm

import (
	"encoding/json"
	"time"
)

// Dataset 对应 neutrino ragservice 的 datasets 表（知识库元数据）。
// 结构尽量与 ragservice DDL 保持对齐，便于 dbmigrate 生成/对比 DDL。
type Dataset struct {
	ID string `gorm:"primaryKey;column:id;type:varchar(255)"`

	// KbID 关联外部服务创建的 kb_id。
	KbID string `gorm:"column:kb_id;type:varchar(255);not null;index:idx_datasets_kb_id"`

	DisplayName string `gorm:"column:display_name;type:varchar(255);not null"`
	Desc        string `gorm:"column:desc;type:longtext;not null"`
	CoverImage  string `gorm:"column:cover_image;type:varchar(255);not null"`

	ResourceUID string `gorm:"column:resource_uid;type:varchar(36);not null;index:idx_resource_uid"`
	BucketName  string `gorm:"column:bucket_name;type:varchar(255);not null"`
	OssPath     string `gorm:"column:oss_path;type:varchar(255);not null"`

	DatasetInfo json.RawMessage `gorm:"column:dataset_info;type:json"`
	DatasetState uint8         `gorm:"column:dataset_state;not null"`

	EmbeddingModel         string `gorm:"column:embedding_model;type:varchar(255);not null"`
	EmbeddingModelProvider string `gorm:"column:embedding_model_provider;type:varchar(255);not null"`

	ShareType uint8 `gorm:"column:share_type;not null"`
	// shared_at / tenant_id / is_demonstrate / type / ext 在历史 DDL 中存在，
	// 这里保持字段齐全以便 DDL 生成完整。
	SharedAt *time.Time `gorm:"column:shared_at"`

	TenantID      string `gorm:"column:tenant_id;type:varchar(36);not null"`
	IsDemonstrate bool   `gorm:"column:is_demonstrate;not null;default:false"`
	Type          uint8  `gorm:"column:type;not null;default:1"`

	Ext json.RawMessage `gorm:"column:ext;type:json"`

	BaseModel
}

func (Dataset) TableName() string { return "datasets" }

// DefaultDataset 对应 neutrino ragservice 的 default_datasets 表（用户默认知识库）。
type DefaultDataset struct {
	ID int64 `gorm:"primaryKey;column:id;autoIncrement"`

	DatasetID   string `gorm:"column:dataset_id;type:varchar(64);not null;uniqueIndex:ukx_create_user_id_dataset_id,priority:2"`
	DatasetName string `gorm:"column:dataset_name;type:varchar(255);not null"`

	BaseModel
}

func (DefaultDataset) TableName() string { return "default_datasets" }

