package store

import "time"

type sourceEntity struct {
	ID                    string     `gorm:"column:id;type:text;primaryKey"`
	TenantID              string     `gorm:"column:tenant_id;type:text;not null;index:idx_sources_tenant;uniqueIndex:uk_sources_tenant_agent_root,priority:1"`
	Name                  string     `gorm:"column:name;type:text;not null"`
	SourceType            string     `gorm:"column:source_type;type:text;not null"`
	RootPath              string     `gorm:"column:root_path;type:text;not null;uniqueIndex:uk_sources_tenant_agent_root,priority:3"`
	Status                string     `gorm:"column:status;type:text;not null"`
	WatchEnabled          bool       `gorm:"column:watch_enabled;not null;default:false"`
	WatchUpdatedAt        *time.Time `gorm:"column:watch_updated_at"`
	IdleWindowSeconds     int64      `gorm:"column:idle_window_seconds;not null"`
	ReconcileSeconds      int64      `gorm:"column:reconcile_seconds;not null"`
	ReconcileSchedule     string     `gorm:"column:reconcile_schedule;type:text"`
	AgentID               string     `gorm:"column:agent_id;type:text;not null;uniqueIndex:uk_sources_tenant_agent_root,priority:2"`
	DatasetID             string     `gorm:"column:dataset_id;type:text"`
	DefaultOriginType     string     `gorm:"column:default_origin_type;type:text;not null;default:LOCAL_FS"`
	DefaultOriginPlatform string     `gorm:"column:default_origin_platform;type:text;not null;default:LOCAL"`
	DefaultTriggerPolicy  string     `gorm:"column:default_trigger_policy;type:text;not null;default:IDLE_WINDOW"`
	CreatedAt             time.Time  `gorm:"column:created_at;not null"`
	UpdatedAt             time.Time  `gorm:"column:updated_at;not null"`
}

func (sourceEntity) TableName() string { return "sources" }

type cloudSourceBindingEntity struct {
	SourceID              string    `gorm:"column:source_id;type:text;primaryKey"`
	TenantID              string    `gorm:"column:tenant_id;type:text;not null;index:idx_cloud_bindings_tenant_status,priority:1"`
	Provider              string    `gorm:"column:provider;type:text;not null;index:idx_cloud_bindings_provider_status,priority:1"`
	Enabled               bool      `gorm:"column:enabled;not null;default:true"`
	Status                string    `gorm:"column:status;type:text;not null;index:idx_cloud_bindings_tenant_status,priority:2;index:idx_cloud_bindings_provider_status,priority:2"`
	AuthConnectionID      string    `gorm:"column:auth_connection_id;type:text;not null"`
	TargetType            string    `gorm:"column:target_type;type:text"`
	TargetRef             string    `gorm:"column:target_ref;type:text"`
	ScheduleExpr          string    `gorm:"column:schedule_expr;type:text;not null"`
	ScheduleTZ            string    `gorm:"column:schedule_tz;type:text;not null"`
	ReconcileAfterSync    bool      `gorm:"column:reconcile_after_sync;not null;default:true"`
	ReconcileDelayMinutes int       `gorm:"column:reconcile_delay_minutes;not null;default:10"`
	IncludePatternsJSON   string    `gorm:"column:include_patterns_json;type:text"`
	ExcludePatternsJSON   string    `gorm:"column:exclude_patterns_json;type:text"`
	MaxObjectSizeBytes    int64     `gorm:"column:max_object_size_bytes;not null;default:0"`
	ProviderOptionsJSON   string    `gorm:"column:provider_options_json;type:text"`
	LastError             string    `gorm:"column:last_error;type:text"`
	CreatedAt             time.Time `gorm:"column:created_at;not null"`
	UpdatedAt             time.Time `gorm:"column:updated_at;not null"`
}

func (cloudSourceBindingEntity) TableName() string { return "cloud_source_bindings" }

type cloudSyncCheckpointEntity struct {
	SourceID      string     `gorm:"column:source_id;type:text;primaryKey"`
	Provider      string     `gorm:"column:provider;type:text;not null"`
	NextSyncAt    *time.Time `gorm:"column:next_sync_at;index:idx_cloud_sync_checkpoints_next_sync_at"`
	LastSyncAt    *time.Time `gorm:"column:last_sync_at"`
	LastSuccessAt *time.Time `gorm:"column:last_success_at"`
	LastRunID     string     `gorm:"column:last_run_id;type:text"`
	RemoteCursor  string     `gorm:"column:remote_cursor;type:text"`
	LockOwner     string     `gorm:"column:lock_owner;type:text"`
	LockUntil     *time.Time `gorm:"column:lock_until;index:idx_cloud_sync_checkpoints_lock_until"`
	UpdatedAt     time.Time  `gorm:"column:updated_at;not null"`
}

func (cloudSyncCheckpointEntity) TableName() string { return "cloud_sync_checkpoints" }

type cloudObjectIndexEntity struct {
	ID                 int64      `gorm:"column:id;primaryKey;autoIncrement"`
	SourceID           string     `gorm:"column:source_id;type:text;not null;index:idx_cloud_object_source;uniqueIndex:uk_cloud_object,priority:1"`
	Provider           string     `gorm:"column:provider;type:text;not null;index:idx_cloud_object_provider"`
	ExternalObjectID   string     `gorm:"column:external_object_id;type:text;not null;uniqueIndex:uk_cloud_object,priority:2"`
	ExternalParentID   string     `gorm:"column:external_parent_id;type:text"`
	ExternalPath       string     `gorm:"column:external_path;type:text"`
	ExternalName       string     `gorm:"column:external_name;type:text"`
	ExternalKind       string     `gorm:"column:external_kind;type:text"`
	ExternalVersion    string     `gorm:"column:external_version;type:text"`
	ExternalModifiedAt *time.Time `gorm:"column:external_modified_at"`
	LocalRelPath       string     `gorm:"column:local_rel_path;type:text"`
	LocalAbsPath       string     `gorm:"column:local_abs_path;type:text"`
	Checksum           string     `gorm:"column:checksum;type:text"`
	SizeBytes          int64      `gorm:"column:size_bytes;not null;default:0"`
	IsDeleted          bool       `gorm:"column:is_deleted;not null;default:false"`
	LastSyncedAt       *time.Time `gorm:"column:last_synced_at"`
	ProviderMetaJSON   string     `gorm:"column:provider_meta_json;type:text"`
	CreatedAt          time.Time  `gorm:"column:created_at;not null"`
	UpdatedAt          time.Time  `gorm:"column:updated_at;not null"`
}

func (cloudObjectIndexEntity) TableName() string { return "cloud_object_index" }

type cloudSyncRunEntity struct {
	RunID        string     `gorm:"column:run_id;type:text;primaryKey"`
	SourceID     string     `gorm:"column:source_id;type:text;not null;index:idx_cloud_sync_runs_source_started,priority:1"`
	TenantID     string     `gorm:"column:tenant_id;type:text;not null;index:idx_cloud_sync_runs_tenant,priority:1"`
	Provider     string     `gorm:"column:provider;type:text;not null;index:idx_cloud_sync_runs_provider,priority:1"`
	TriggerType  string     `gorm:"column:trigger_type;type:text;not null"`
	Status       string     `gorm:"column:status;type:text;not null;index:idx_cloud_sync_runs_status"`
	StartedAt    *time.Time `gorm:"column:started_at;index:idx_cloud_sync_runs_source_started,priority:2"`
	FinishedAt   *time.Time `gorm:"column:finished_at"`
	RemoteTotal  int        `gorm:"column:remote_total;not null;default:0"`
	CreatedCount int        `gorm:"column:created_count;not null;default:0"`
	UpdatedCount int        `gorm:"column:updated_count;not null;default:0"`
	DeletedCount int        `gorm:"column:deleted_count;not null;default:0"`
	SkippedCount int        `gorm:"column:skipped_count;not null;default:0"`
	FailedCount  int        `gorm:"column:failed_count;not null;default:0"`
	ErrorCode    string     `gorm:"column:error_code;type:text"`
	ErrorMessage string     `gorm:"column:error_message;type:text"`
	CreatedAt    time.Time  `gorm:"column:created_at;not null"`
	UpdatedAt    time.Time  `gorm:"column:updated_at;not null"`
}

func (cloudSyncRunEntity) TableName() string { return "cloud_sync_runs" }

type agentEntity struct {
	AgentID           string    `gorm:"column:agent_id;type:text;primaryKey"`
	TenantID          string    `gorm:"column:tenant_id;type:text;not null"`
	Hostname          string    `gorm:"column:hostname;type:text;not null"`
	Version           string    `gorm:"column:version;type:text;not null"`
	Status            string    `gorm:"column:status;type:text;not null"`
	ListenAddr        string    `gorm:"column:listen_addr;type:text;not null"`
	LastHeartbeatAt   time.Time `gorm:"column:last_heartbeat_at;not null"`
	ActiveSourceCount int       `gorm:"column:active_source_count;not null;default:0"`
	ActiveWatchCount  int       `gorm:"column:active_watch_count;not null;default:0"`
	ActiveTaskCount   int       `gorm:"column:active_task_count;not null;default:0"`
	UpdatedAt         time.Time `gorm:"column:updated_at;not null"`
}

func (agentEntity) TableName() string { return "agents" }

type agentCommandEntity struct {
	ID           int64      `gorm:"column:id;primaryKey;autoIncrement"`
	AgentID      string     `gorm:"column:agent_id;type:text;not null;index:idx_agent_commands_pending,priority:1"`
	Type         string     `gorm:"column:type;type:text;not null"`
	Payload      string     `gorm:"column:payload;type:text;not null"`
	Status       string     `gorm:"column:status;type:text;not null;index:idx_agent_commands_pending,priority:2"`
	AttemptCount int        `gorm:"column:attempt_count;not null;default:0"`
	NextRetryAt  *time.Time `gorm:"column:next_retry_at;index:idx_agent_commands_pending,priority:3"`
	AckedAt      *time.Time `gorm:"column:acked_at"`
	LastError    string     `gorm:"column:last_error;type:text"`
	ResultJSON   string     `gorm:"column:result_json;type:text"`
	CreatedAt    time.Time  `gorm:"column:created_at;not null"`
	DispatchedAt *time.Time `gorm:"column:dispatched_at"`
}

func (agentCommandEntity) TableName() string { return "agent_commands" }

type documentEntity struct {
	ID               int64      `gorm:"column:id;primaryKey;autoIncrement"`
	TenantID         string     `gorm:"column:tenant_id;type:text;not null;uniqueIndex:uk_documents_scope,priority:1"`
	SourceID         string     `gorm:"column:source_id;type:text;not null;uniqueIndex:uk_documents_scope,priority:2"`
	SourceObjectID   string     `gorm:"column:source_object_id;type:text;not null;uniqueIndex:uk_documents_scope,priority:3"`
	CoreDocumentID   string     `gorm:"column:core_document_id;type:text;index:idx_documents_core_document"`
	CurrentVersionID string     `gorm:"column:current_version_id;type:text"`
	DesiredVersionID string     `gorm:"column:desired_version_id;type:text"`
	LastModifiedAt   *time.Time `gorm:"column:last_modified_at"`
	NextParseAt      *time.Time `gorm:"column:next_parse_at;index:idx_documents_next_parse"`
	ParseStatus      string     `gorm:"column:parse_status;type:text;not null"`
	OriginType       string     `gorm:"column:origin_type;type:text;not null;default:LOCAL_FS"`
	OriginPlatform   string     `gorm:"column:origin_platform;type:text;not null;default:LOCAL"`
	OriginRef        string     `gorm:"column:origin_ref;type:text"`
	TriggerPolicy    string     `gorm:"column:trigger_policy;type:text;not null;default:IDLE_WINDOW"`
	UpdatedAt        time.Time  `gorm:"column:updated_at;not null"`
}

func (documentEntity) TableName() string { return "documents" }

type parseTaskEntity struct {
	ID                      int64      `gorm:"column:id;primaryKey;autoIncrement"`
	TenantID                string     `gorm:"column:tenant_id;type:text;not null;index:idx_parse_tasks_tenant_status_updated,priority:1"`
	DocumentID              int64      `gorm:"column:document_id;not null;index:idx_parse_tasks_document"`
	TaskAction              string     `gorm:"column:task_action;type:text;not null;default:CREATE"`
	TargetVersionID         string     `gorm:"column:target_version_id;type:text;not null"`
	OriginType              string     `gorm:"column:origin_type;type:text;not null;default:LOCAL_FS"`
	OriginPlatform          string     `gorm:"column:origin_platform;type:text;not null;default:LOCAL"`
	TriggerPolicy           string     `gorm:"column:trigger_policy;type:text;not null;default:IDLE_WINDOW"`
	Status                  string     `gorm:"column:status;type:text;not null;index:idx_parse_tasks_tenant_status_updated,priority:2"`
	CoreDatasetID           string     `gorm:"column:core_dataset_id;type:text"`
	CoreDocumentID          string     `gorm:"column:core_document_id;type:text;index:idx_parse_tasks_core_document"`
	CoreTaskID              string     `gorm:"column:core_task_id;type:text;index:idx_parse_tasks_core_task"`
	ScanOrchestrationStatus string     `gorm:"column:scan_orchestration_status;type:text;index:idx_parse_tasks_orchestration_status"`
	SubmitErrorMessage      string     `gorm:"column:submit_error_message;type:text"`
	SubmitAt                *time.Time `gorm:"column:submit_at"`
	IdempotencyKey          string     `gorm:"column:idempotency_key;type:text;index:idx_parse_tasks_idempotency"`
	SelectionToken          string     `gorm:"column:selection_token;type:text"`
	NextRunAt               time.Time  `gorm:"column:next_run_at;not null"`
	RetryCount              int        `gorm:"column:retry_count;not null;default:0"`
	MaxRetryCount           int        `gorm:"column:max_retry_count;not null;default:8"`
	LeaseOwner              string     `gorm:"column:lease_owner;type:text;index:idx_parse_tasks_lease"`
	LeaseUntil              *time.Time `gorm:"column:lease_until;index:idx_parse_tasks_lease"`
	StartedAt               *time.Time `gorm:"column:started_at"`
	FinishedAt              *time.Time `gorm:"column:finished_at"`
	LastError               string     `gorm:"column:last_error;type:text"`
	CreatedAt               time.Time  `gorm:"column:created_at;not null"`
	UpdatedAt               time.Time  `gorm:"column:updated_at;not null;index:idx_parse_tasks_tenant_status_updated,priority:3"`
}

func (parseTaskEntity) TableName() string { return "parse_tasks" }

type parseTaskDeadLetterEntity struct {
	ID              int64     `gorm:"column:id;primaryKey;autoIncrement"`
	TaskID          int64     `gorm:"column:task_id;not null;index:idx_parse_task_dead_letters_task"`
	TenantID        string    `gorm:"column:tenant_id;type:text;not null"`
	DocumentID      int64     `gorm:"column:document_id;not null"`
	TargetVersionID string    `gorm:"column:target_version_id;type:text;not null"`
	RetryCount      int       `gorm:"column:retry_count;not null"`
	OriginType      string    `gorm:"column:origin_type;type:text;not null"`
	OriginPlatform  string    `gorm:"column:origin_platform;type:text;not null"`
	TriggerPolicy   string    `gorm:"column:trigger_policy;type:text;not null"`
	LastError       string    `gorm:"column:last_error;type:text;not null"`
	FailedAt        time.Time `gorm:"column:failed_at;not null;index:idx_parse_task_dead_letters_failed_at"`
	CreatedAt       time.Time `gorm:"column:created_at;not null"`
}

func (parseTaskDeadLetterEntity) TableName() string { return "parse_task_dead_letters" }

type reconcileSnapshotEntity struct {
	SourceID    string    `gorm:"column:source_id;type:text;primaryKey"`
	SnapshotRef string    `gorm:"column:snapshot_ref;type:text;not null"`
	FileCount   int64     `gorm:"column:file_count;not null;default:0"`
	TakenAt     time.Time `gorm:"column:taken_at;not null"`
	UpdatedAt   time.Time `gorm:"column:updated_at;not null"`
}

func (reconcileSnapshotEntity) TableName() string { return "reconcile_snapshots" }

type sourceBaselineSnapshotEntity struct {
	SourceID    string    `gorm:"column:source_id;type:text;primaryKey"`
	SnapshotRef string    `gorm:"column:snapshot_ref;type:text;not null"`
	FileCount   int64     `gorm:"column:file_count;not null;default:0"`
	TakenAt     time.Time `gorm:"column:taken_at;not null"`
	Reason      string    `gorm:"column:reason;type:text;not null"`
	UpdatedAt   time.Time `gorm:"column:updated_at;not null"`
}

func (sourceBaselineSnapshotEntity) TableName() string { return "source_baseline_snapshots" }

type sourceFileSnapshotEntity struct {
	SnapshotID     string     `gorm:"column:snapshot_id;type:text;primaryKey"`
	SourceID       string     `gorm:"column:source_id;type:text;not null;index:idx_source_file_snapshots_source_created,priority:1"`
	TenantID       string     `gorm:"column:tenant_id;type:text;not null;index:idx_source_file_snapshots_tenant_created,priority:1"`
	SnapshotType   string     `gorm:"column:snapshot_type;type:text;not null"`
	BaseSnapshotID string     `gorm:"column:base_snapshot_id;type:text"`
	SelectionToken string     `gorm:"column:selection_token;type:text;index:idx_source_file_snapshots_selection_token,unique"`
	ExpiresAt      *time.Time `gorm:"column:expires_at;index:idx_source_file_snapshots_expires_at"`
	ConsumedAt     *time.Time `gorm:"column:consumed_at"`
	FileCount      int64      `gorm:"column:file_count;not null;default:0"`
	CreatedAt      time.Time  `gorm:"column:created_at;not null;index:idx_source_file_snapshots_source_created,priority:2;index:idx_source_file_snapshots_tenant_created,priority:2"`
}

func (sourceFileSnapshotEntity) TableName() string { return "source_file_snapshots" }

type sourceFileSnapshotItemEntity struct {
	ID             int64      `gorm:"column:id;primaryKey;autoIncrement"`
	SnapshotID     string     `gorm:"column:snapshot_id;type:text;not null;index:idx_source_file_snapshot_items_snapshot,priority:1;uniqueIndex:uk_source_snapshot_item_path,priority:1"`
	Path           string     `gorm:"column:path;type:text;not null;index:idx_source_file_snapshot_items_path;uniqueIndex:uk_source_snapshot_item_path,priority:2"`
	IsDir          bool       `gorm:"column:is_dir;not null;default:false"`
	SizeBytes      int64      `gorm:"column:size_bytes;not null;default:0"`
	ModTime        *time.Time `gorm:"column:mod_time"`
	Checksum       string     `gorm:"column:checksum;type:text"`
	ExternalFileID string     `gorm:"column:external_file_id;type:text"`
}

func (sourceFileSnapshotItemEntity) TableName() string { return "source_file_snapshot_items" }

type sourceSnapshotRelationEntity struct {
	SourceID                string    `gorm:"column:source_id;type:text;primaryKey"`
	LastPreviewSnapshotID   string    `gorm:"column:last_preview_snapshot_id;type:text"`
	LastCommittedSnapshotID string    `gorm:"column:last_committed_snapshot_id;type:text"`
	UpdatedAt               time.Time `gorm:"column:updated_at;not null"`
}

func (sourceSnapshotRelationEntity) TableName() string { return "source_snapshot_relations" }

type manualPullJobEntity struct {
	JobID                 string     `gorm:"column:job_id;type:text;primaryKey"`
	TenantID              string     `gorm:"column:tenant_id;type:text;not null;index:idx_manual_pull_jobs_source_created,priority:1"`
	SourceID              string     `gorm:"column:source_id;type:text;not null;index:idx_manual_pull_jobs_source_created,priority:2"`
	Status                string     `gorm:"column:status;type:text;not null;index:idx_manual_pull_jobs_source_status,priority:1"`
	Mode                  string     `gorm:"column:mode;type:text;not null"`
	TriggerPolicy         string     `gorm:"column:trigger_policy;type:text"`
	SelectionToken        string     `gorm:"column:selection_token;type:text"`
	UpdatedOnly           bool       `gorm:"column:updated_only;not null;default:false"`
	RequestedCount        int        `gorm:"column:requested_count;not null;default:0"`
	AcceptedCount         int        `gorm:"column:accepted_count;not null;default:0"`
	SkippedCount          int        `gorm:"column:skipped_count;not null;default:0"`
	IgnoredUnchangedCount int        `gorm:"column:ignored_unchanged_count;not null;default:0"`
	ErrorMessage          string     `gorm:"column:error_message;type:text"`
	CreatedAt             time.Time  `gorm:"column:created_at;not null;index:idx_manual_pull_jobs_source_created,priority:3"`
	UpdatedAt             time.Time  `gorm:"column:updated_at;not null"`
	FinishedAt            *time.Time `gorm:"column:finished_at"`
}

func (manualPullJobEntity) TableName() string { return "manual_pull_jobs" }
