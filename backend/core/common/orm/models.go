// Package orm 的表结构定义统一放在本文件。
// 仅此一套迁移：执行命令生成 migrations/*.sql，启动时 migrate.RunUp() 应用。新增 Model 时在此定义并在 all_models.go 中追加，便于 dbmigrate migrate 生成 DDL。

package orm

import (
	"encoding/json"
	"time"
)

// ----- ACL 相关 -----

// VisibilityModel 资源（如 kb）可见级别。
type VisibilityModel struct {
	ID         int64  `gorm:"primaryKey;autoIncrement"`
	ResourceID string `gorm:"column:resource_id;type:varchar(255);index"`
	Level      string `gorm:"column:level;type:varchar(32)"`
}

func (VisibilityModel) TableName() string { return "acl_visibility" }

// ACLModel ACL 行记录。
type ACLModel struct {
	ID           int64      `gorm:"primaryKey;autoIncrement"`
	ResourceType string     `gorm:"column:resource_type;type:varchar(32);index:idx_acl_resource,priority:1"`
	ResourceID   string     `gorm:"column:resource_id;type:varchar(255);index:idx_acl_resource,priority:2"`
	GranteeType  string     `gorm:"column:grantee_type;type:varchar(32)"`
	TargetID     int64      `gorm:"column:target_id"`
	Permission   string     `gorm:"column:permission;type:varchar(32)"`
	CreatedBy    int64      `gorm:"column:created_by"`
	CreatedAt    time.Time  `gorm:"column:created_at"`
	ExpiresAt    *time.Time `gorm:"column:expires_at"`
}

func (ACLModel) TableName() string { return "acl_rows" }

// KBModel 知识库元数据。
type KBModel struct {
	ID         string `gorm:"primaryKey;column:id;type:varchar(64)"`
	Name       string `gorm:"column:name;type:varchar(255)"`
	OwnerID    int64  `gorm:"column:owner_id"`
	Visibility string `gorm:"column:visibility;type:varchar(32)"`
}

func (KBModel) TableName() string { return "acl_kbs" }

// UserGroupModel 用户与组/租户映射。
type UserGroupModel struct {
	UserID  int64 `gorm:"primaryKey;column:user_id"`
	GroupID int64 `gorm:"primaryKey;column:group_id"`
}

func (UserGroupModel) TableName() string { return "acl_user_groups" }

// ----- Chat / Prompt 相关 -----

// Prompt 表，对应 neutrino 的 prompts。
type Prompt struct {
	ID      string `gorm:"column:id;type:varchar(64);primaryKey"`
	Name    string `gorm:"column:name;type:varchar(255);uniqueIndex;not null"`
	Content string `gorm:"column:content;type:text;not null"`

	BaseModel
}

func (Prompt) TableName() string { return "prompts" }

// DefaultPrompt 表，对应 neutrino 的 default_prompts。
type DefaultPrompt struct {
	ID         int    `gorm:"column:id;primaryKey;autoIncrement"`
	PromptID   string `gorm:"column:prompt_id;type:varchar(64);not null"`
	PromptName string `gorm:"column:prompt_name;type:varchar(255);not null"`

	BaseModel
}

func (DefaultPrompt) TableName() string { return "default_prompts" }

// MultiAnswersSwitch 表，对应 neutrino 的 multi_answers_switches。
type MultiAnswersSwitch struct {
	ID     int32 `gorm:"column:id;primaryKey;autoIncrement"`
	Status int32 `gorm:"column:status;not null;default:0"`

	BaseModel
}

func (MultiAnswersSwitch) TableName() string { return "multi_answers_switches" }

// Conversation 表，对应 neutrino 的 conversations；channel_id 使用默认值。
type Conversation struct {
	ID            string          `gorm:"column:id;type:varchar(36);primaryKey"`
	DisplayName   string          `gorm:"column:display_name;type:varchar(255)"`
	ChannelID     string          `gorm:"column:channel_id;type:varchar(36);not null;default:default"`
	SearchConfig  json.RawMessage `gorm:"column:search_config;type:json"`
	ApplicationID string          `gorm:"column:application_id;type:varchar(64);default:''"`
	Ext           json.RawMessage `gorm:"column:ext;type:json"`
	Model         string          `gorm:"column:model;type:varchar(64);default:''"`
	Models        json.RawMessage `gorm:"column:models;type:json"`
	ChatTimes     int32           `gorm:"column:chat_times;not null;default:0"`

	BaseModel
}

func (Conversation) TableName() string { return "conversations" }

// ChatHistory 表，对应 neutrino 的 chat_histories。
type ChatHistory struct {
	ID              string          `gorm:"column:id;type:varchar(36);primaryKey"`
	Seq             int             `gorm:"column:seq;not null"`
	ConversationID  string          `gorm:"column:conversation_id;type:varchar(36);index;not null"`
	RawContent      string          `gorm:"column:raw_content;type:text"`
	RetrievalResult json.RawMessage `gorm:"column:retrieval_result;type:json"`
	Content         string          `gorm:"column:content;type:text"`
	Result          string          `gorm:"column:result;type:text"`
	FeedBack        int             `gorm:"column:feed_back;default:0"`
	Reason          string          `gorm:"column:reason;type:varchar(255)"`
	ExpectedAnswer  string          `gorm:"column:expected_answer;type:text"`
	Ext             json.RawMessage `gorm:"column:ext;type:json"`
	Version         string          `gorm:"column:version;type:varchar(128);default:2.3"`

	TimeMixin
}

func (ChatHistory) TableName() string { return "chat_histories" }

// MultiAnswersChatHistory 表，对应 neutrino 的 multi_answers_chat_histories。
type MultiAnswersChatHistory struct {
	ID              string          `gorm:"column:id;type:varchar(36);primaryKey"`
	Seq             int             `gorm:"column:seq;not null"`
	ConversationID  string          `gorm:"column:conversation_id;type:varchar(36);index;not null"`
	RawContent      string          `gorm:"column:raw_content;type:text"`
	RetrievalResult json.RawMessage `gorm:"column:retrieval_result;type:json"`
	Content         string          `gorm:"column:content;type:text"`
	Result          string          `gorm:"column:result;type:text"`
	FeedBack        int             `gorm:"column:feed_back;default:0"`
	Reason          string          `gorm:"column:reason;type:varchar(255)"`
	Ext             json.RawMessage `gorm:"column:ext;type:json"`
	Endpoint        string          `gorm:"column:endpoint;type:varchar(512)"`

	TimeMixin
}

func (MultiAnswersChatHistory) TableName() string { return "multi_answers_chat_histories" }
