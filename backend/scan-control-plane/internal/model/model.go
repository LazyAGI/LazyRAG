package model

import "time"

type SourceStatus string

const (
	SourceStatusEnabled  SourceStatus = "ENABLED"
	SourceStatusDisabled SourceStatus = "DISABLED"
	SourceStatusDegraded SourceStatus = "DEGRADED"
	SourceStatusError    SourceStatus = "ERROR"
)

type OriginType string

const (
	OriginTypeLocalFS   OriginType = "LOCAL_FS"
	OriginTypeCloudSync OriginType = "CLOUD_SYNC"
)

type TriggerPolicy string

const (
	TriggerPolicyIdleWindow TriggerPolicy = "IDLE_WINDOW"
	TriggerPolicyImmediate  TriggerPolicy = "IMMEDIATE"
)

type ParseTaskAction string

const (
	ParseTaskActionCreate  ParseTaskAction = "CREATE"
	ParseTaskActionReparse ParseTaskAction = "REPARSE"
	ParseTaskActionDelete  ParseTaskAction = "DELETE"
)

type CommandType string

const (
	CommandStartSource    CommandType = "start_source"
	CommandStopSource     CommandType = "stop_source"
	CommandReloadSource   CommandType = "reload_source"
	CommandScanSource     CommandType = "scan_source"
	CommandStageFile      CommandType = "stage_file"
	CommandSnapshotSource CommandType = "snapshot_source"
)

type Source struct {
	ID                    string       `json:"id"`
	TenantID              string       `json:"tenant_id"`
	Name                  string       `json:"name"`
	SourceType            string       `json:"source_type"`
	RootPath              string       `json:"root_path"`
	Status                SourceStatus `json:"status"`
	WatchEnabled          bool         `json:"watch_enabled"`
	IdleWindowSeconds     int64        `json:"idle_window_seconds"`
	ReconcileSeconds      int64        `json:"reconcile_seconds"`
	ReconcileSchedule     string       `json:"reconcile_schedule,omitempty"`
	AgentID               string       `json:"agent_id"`
	DatasetID             string       `json:"dataset_id,omitempty"`
	DefaultOriginType     string       `json:"default_origin_type"`
	DefaultOriginPlatform string       `json:"default_origin_platform"`
	DefaultTriggerPolicy  string       `json:"default_trigger_policy"`
	CreatedAt             time.Time    `json:"created_at"`
	UpdatedAt             time.Time    `json:"updated_at"`
}

type CreateSourceRequest struct {
	TenantID              string `json:"tenant_id"`
	Name                  string `json:"name"`
	RootPath              string `json:"root_path"`
	AgentID               string `json:"agent_id"`
	DatasetID             string `json:"dataset_id,omitempty"`
	WatchEnabled          bool   `json:"watch_enabled,omitempty"`
	IdleWindowSeconds     int64  `json:"idle_window_seconds,omitempty"`
	ReconcileSeconds      int64  `json:"reconcile_seconds,omitempty"`
	ReconcileSchedule     string `json:"reconcile_schedule,omitempty"`
	DefaultOriginType     string `json:"default_origin_type,omitempty"`
	DefaultOriginPlatform string `json:"default_origin_platform,omitempty"`
	DefaultTriggerPolicy  string `json:"default_trigger_policy,omitempty"`
}

type UpdateSourceRequest struct {
	Name                  string `json:"name"`
	RootPath              string `json:"root_path"`
	DatasetID             string `json:"dataset_id,omitempty"`
	IdleWindowSeconds     int64  `json:"idle_window_seconds,omitempty"`
	ReconcileSeconds      int64  `json:"reconcile_seconds,omitempty"`
	ReconcileSchedule     string `json:"reconcile_schedule,omitempty"`
	DefaultOriginType     string `json:"default_origin_type,omitempty"`
	DefaultOriginPlatform string `json:"default_origin_platform,omitempty"`
	DefaultTriggerPolicy  string `json:"default_trigger_policy,omitempty"`
}

type Command struct {
	ID        int64       `json:"id"`
	AgentID   string      `json:"agent_id"`
	Type      CommandType `json:"type"`
	Payload   string      `json:"payload"`
	Status    string      `json:"status"`
	CreatedAt time.Time   `json:"created_at"`
}

type RegisterAgentRequest struct {
	AgentID    string `json:"agent_id"`
	TenantID   string `json:"tenant_id"`
	Hostname   string `json:"hostname"`
	Version    string `json:"version"`
	ListenAddr string `json:"listen_addr,omitempty"`
}

type HeartbeatPayload struct {
	AgentID          string    `json:"agent_id"`
	TenantID         string    `json:"tenant_id"`
	Hostname         string    `json:"hostname"`
	Version          string    `json:"version"`
	Status           string    `json:"status"`
	LastHeartbeatAt  time.Time `json:"last_heartbeat_at"`
	SourceCount      int       `json:"source_count"`
	ActiveWatchCount int       `json:"active_watch_count"`
	ActiveTaskCount  int       `json:"active_task_count"`
	ListenAddr       string    `json:"listen_addr,omitempty"`
}

type PullCommandsRequest struct {
	AgentID  string `json:"agent_id"`
	TenantID string `json:"tenant_id"`
}

type PullCommandsResponse struct {
	Commands []PulledCommand `json:"commands"`
}

type PulledCommand struct {
	ID                int64       `json:"id"`
	Type              CommandType `json:"type"`
	TenantID          string      `json:"tenant_id,omitempty"`
	SourceID          string      `json:"source_id,omitempty"`
	RootPath          string      `json:"root_path,omitempty"`
	Mode              string      `json:"mode,omitempty"`
	Reason            string      `json:"reason,omitempty"`
	SkipInitialScan   bool        `json:"skip_initial_scan,omitempty"`
	ReconcileSeconds  int64       `json:"reconcile_seconds,omitempty"`
	ReconcileSchedule string      `json:"reconcile_schedule,omitempty"`
	DocumentID        string      `json:"document_id,omitempty"`
	VersionID         string      `json:"version_id,omitempty"`
	SrcPath           string      `json:"src_path,omitempty"`
}

type AckCommandRequest struct {
	AgentID    string `json:"agent_id"`
	CommandID  int64  `json:"command_id"`
	Success    bool   `json:"success"`
	Error      string `json:"error,omitempty"`
	ResultJSON string `json:"result_json,omitempty"`
}

type ReportSnapshotRequest struct {
	AgentID     string    `json:"agent_id"`
	SourceID    string    `json:"source_id"`
	SnapshotRef string    `json:"snapshot_ref"`
	FileCount   int64     `json:"file_count"`
	TakenAt     time.Time `json:"taken_at"`
}

type FileEvent struct {
	SourceID       string    `json:"source_id"`
	TenantID       string    `json:"tenant_id"`
	EventType      string    `json:"event_type"`
	Path           string    `json:"path"`
	IsDir          bool      `json:"is_dir"`
	OccurredAt     time.Time `json:"occurred_at"`
	OriginType     string    `json:"origin_type,omitempty"`
	OriginPlatform string    `json:"origin_platform,omitempty"`
	OriginRef      string    `json:"origin_ref,omitempty"`
	TriggerPolicy  string    `json:"trigger_policy,omitempty"`
}

type ReportEventsRequest struct {
	AgentID string      `json:"agent_id"`
	Events  []FileEvent `json:"events"`
}

type ScanRecord struct {
	SourceID       string    `json:"source_id"`
	Path           string    `json:"path"`
	IsDir          bool      `json:"is_dir"`
	Size           int64     `json:"size"`
	ModTime        time.Time `json:"mod_time"`
	Checksum       string    `json:"checksum,omitempty"`
	OriginType     string    `json:"origin_type,omitempty"`
	OriginPlatform string    `json:"origin_platform,omitempty"`
	OriginRef      string    `json:"origin_ref,omitempty"`
	TriggerPolicy  string    `json:"trigger_policy,omitempty"`
}

type ReportScanResultsRequest struct {
	AgentID  string       `json:"agent_id"`
	SourceID string       `json:"source_id"`
	Mode     string       `json:"mode"`
	Records  []ScanRecord `json:"records"`
}

type ErrorResponse struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type SourcePayload struct {
	SourceID          string `json:"source_id"`
	TenantID          string `json:"tenant_id"`
	RootPath          string `json:"root_path"`
	Reason            string `json:"reason,omitempty"`
	SkipInitialScan   bool   `json:"skip_initial_scan,omitempty"`
	ReconcileSeconds  int64  `json:"reconcile_seconds,omitempty"`
	ReconcileSchedule string `json:"reconcile_schedule,omitempty"`
}

type GenerateTasksRequest struct {
	Mode           string   `json:"mode"`
	Paths          []string `json:"paths"`
	TriggerPolicy  string   `json:"trigger_policy,omitempty"`
	UpdatedOnly    bool     `json:"updated_only,omitempty"`
	SelectionToken string   `json:"selection_token,omitempty"`
}

type GenerateTasksResponse struct {
	RequestedCount         int    `json:"requested_count"`
	AcceptedCount          int    `json:"accepted_count"`
	MergedPendingCount     int    `json:"merged_pending_count"`
	SkippedCount           int    `json:"skipped_count"`
	IgnoredUnchangedCount  int    `json:"ignored_unchanged_count,omitempty"`
	BaselineSnapshotQueued bool   `json:"baseline_snapshot_queued"`
	ManualPullJobID        string `json:"manual_pull_job_id,omitempty"`
}

type EnableWatchRequest struct {
	ReconcileSeconds  int64  `json:"reconcile_seconds,omitempty"`
	ReconcileSchedule string `json:"reconcile_schedule,omitempty"`
}

type WatchToggleResponse struct {
	Accepted               bool `json:"accepted"`
	SkipInitialScan        bool `json:"skip_initial_scan,omitempty"`
	BaselineSnapshotQueued bool `json:"baseline_snapshot_queued,omitempty"`
}

type ExpediteTasksRequest struct {
	Paths []string `json:"paths"`
}

type ExpediteTasksResponse struct {
	UpdatedExistingTaskCount int `json:"updated_existing_task_count"`
	CreatedTaskCount         int `json:"created_task_count"`
	SkippedCount             int `json:"skipped_count"`
}

type ListParseTasksRequest struct {
	TenantID string `json:"tenant_id"`
	SourceID string `json:"source_id,omitempty"`
	Status   string `json:"status,omitempty"`
	Keyword  string `json:"keyword,omitempty"`
	Page     int    `json:"page,omitempty"`
	PageSize int    `json:"page_size,omitempty"`
}

type ParseTaskListItem struct {
	TaskID                  int64      `json:"task_id"`
	TenantID                string     `json:"tenant_id"`
	SourceID                string     `json:"source_id"`
	SourceName              string     `json:"source_name"`
	DocumentID              int64      `json:"document_id"`
	SourceObjectID          string     `json:"source_object_id"`
	TaskAction              string     `json:"task_action,omitempty"`
	TargetVersionID         string     `json:"target_version_id"`
	Status                  string     `json:"status"`
	RetryCount              int        `json:"retry_count"`
	MaxRetryCount           int        `json:"max_retry_count"`
	OriginType              string     `json:"origin_type"`
	OriginPlatform          string     `json:"origin_platform"`
	TriggerPolicy           string     `json:"trigger_policy"`
	NextRunAt               time.Time  `json:"next_run_at"`
	StartedAt               *time.Time `json:"started_at"`
	FinishedAt              *time.Time `json:"finished_at"`
	LastError               string     `json:"last_error"`
	CreatedAt               time.Time  `json:"created_at"`
	UpdatedAt               time.Time  `json:"updated_at"`
	AgentID                 string     `json:"agent_id,omitempty"`
	AgentListenAddr         string     `json:"agent_listen_addr,omitempty"`
	CoreDatasetID           string     `json:"core_dataset_id,omitempty"`
	CoreDocumentID          string     `json:"core_document_id,omitempty"`
	CoreTaskID              string     `json:"core_task_id,omitempty"`
	ScanOrchestrationStatus string     `json:"scan_orchestration_status,omitempty"`
	SubmitErrorMessage      string     `json:"submit_error_message,omitempty"`
	SubmitAt                *time.Time `json:"submit_at,omitempty"`
}

type ListParseTasksResponse struct {
	Items    []ParseTaskListItem `json:"items"`
	Total    int64               `json:"total"`
	Page     int                 `json:"page"`
	PageSize int                 `json:"page_size"`
}

type ParseTaskDetailResponse struct {
	ParseTaskListItem
	DesiredVersionID    string `json:"desired_version_id,omitempty"`
	CurrentVersionID    string `json:"current_version_id,omitempty"`
	DocumentParseStatus string `json:"document_parse_status,omitempty"`
}

type ParseTaskStatsResponse struct {
	Counts map[string]int64 `json:"counts"`
}

type ListSourceDocumentsRequest struct {
	TenantID   string `json:"tenant_id"`
	Keyword    string `json:"keyword,omitempty"`
	UpdateType string `json:"update_type,omitempty"`
	ParseState string `json:"parse_state,omitempty"`
	Page       int    `json:"page,omitempty"`
	PageSize   int    `json:"page_size,omitempty"`
}

type SourceDocumentsSource struct {
	ID                      string     `json:"id"`
	Name                    string     `json:"name"`
	RootPath                string     `json:"root_path"`
	WatchEnabled            bool       `json:"watch_enabled"`
	AgentID                 string     `json:"agent_id"`
	AgentOnline             bool       `json:"agent_online"`
	UpdateTrackingSupported bool       `json:"update_tracking_supported"`
	LastSyncedAt            *time.Time `json:"last_synced_at,omitempty"`
}

type SourceDocumentsSummary struct {
	ParsedDocumentCount int64 `json:"parsed_document_count"`
	StorageBytes        int64 `json:"storage_bytes"`
	TotalDocumentCount  int64 `json:"total_document_count"`
	NewCount            int64 `json:"new_count"`
	ModifiedCount       int64 `json:"modified_count"`
	DeletedCount        int64 `json:"deleted_count"`
	PendingPullCount    int64 `json:"pending_pull_count"`
}

type SourceDocumentItem struct {
	DocumentID              int64      `json:"document_id"`
	Name                    string     `json:"name"`
	Path                    string     `json:"path"`
	Directory               string     `json:"directory"`
	Tags                    []string   `json:"tags,omitempty"`
	HasUpdate               *bool      `json:"has_update,omitempty"`
	UpdateType              string     `json:"update_type,omitempty"`
	UpdateDesc              string     `json:"update_desc,omitempty"`
	ParseState              string     `json:"parse_state"`
	FileType                string     `json:"file_type,omitempty"`
	SizeBytes               int64      `json:"size_bytes"`
	LastSyncedAt            *time.Time `json:"last_synced_at,omitempty"`
	CoreDatasetID           string     `json:"core_dataset_id,omitempty"`
	CoreTaskID              string     `json:"core_task_id,omitempty"`
	CoreTaskState           string     `json:"core_task_state,omitempty"`
	ScanOrchestrationStatus string     `json:"scan_orchestration_status,omitempty"`
}

type SourceDocumentsResponse struct {
	Source   SourceDocumentsSource  `json:"source"`
	Summary  SourceDocumentsSummary `json:"summary"`
	Items    []SourceDocumentItem   `json:"items"`
	Total    int64                  `json:"total"`
	Page     int                    `json:"page"`
	PageSize int                    `json:"page_size"`
}

type TreeFileStat struct {
	Path     string
	IsDir    bool
	Size     int64
	ModTime  *time.Time
	Checksum string
}

type Agent struct {
	AgentID           string    `json:"agent_id"`
	TenantID          string    `json:"tenant_id"`
	Hostname          string    `json:"hostname"`
	Version           string    `json:"version"`
	Status            string    `json:"status"`
	ListenAddr        string    `json:"listen_addr"`
	LastHeartbeatAt   time.Time `json:"last_heartbeat_at"`
	ActiveSourceCount int       `json:"active_source_count"`
	ActiveWatchCount  int       `json:"active_watch_count"`
	ActiveTaskCount   int       `json:"active_task_count"`
	UpdatedAt         time.Time `json:"updated_at"`
}

type AgentPathRequest struct {
	AgentID string `json:"agent_id"`
	Path    string `json:"path"`
}

type AgentPathTreeRequest struct {
	AgentID      string `json:"agent_id"`
	SourceID     string `json:"source_id,omitempty"`
	Path         string `json:"path"`
	MaxDepth     int    `json:"max_depth,omitempty"`
	IncludeFiles bool   `json:"include_files,omitempty"`
	ChangesOnly  bool   `json:"changes_only,omitempty"`
}

type AgentPathValidateResponse struct {
	Path     string `json:"path"`
	Exists   bool   `json:"exists"`
	Readable bool   `json:"readable"`
	IsDir    bool   `json:"is_dir"`
	Allowed  bool   `json:"allowed"`
	Reason   string `json:"reason"`
}

type TreeNode struct {
	Title           string     `json:"title"`
	Key             string     `json:"key"`
	IsDir           bool       `json:"is_dir"`
	HasUpdate       *bool      `json:"has_update,omitempty"`
	UpdateType      string     `json:"update_type,omitempty"`
	UpdateDesc      string     `json:"update_desc,omitempty"`
	Selectable      *bool      `json:"selectable,omitempty"`
	ExternalFileID  string     `json:"external_file_id,omitempty"`
	ParseQueueState string     `json:"parse_queue_state,omitempty"`
	StatusSource    string     `json:"status_source,omitempty"`
	Children        []TreeNode `json:"children,omitempty"`
}

type AgentPathTreeResponse struct {
	Items          []TreeNode `json:"items"`
	SelectionToken string     `json:"selection_token,omitempty"`
}

type ListManualPullJobsRequest struct {
	SourceID string `json:"source_id"`
	Page     int    `json:"page,omitempty"`
	PageSize int    `json:"page_size,omitempty"`
	Status   string `json:"status,omitempty"`
}

type ManualPullJob struct {
	JobID                 string     `json:"job_id"`
	TenantID              string     `json:"tenant_id"`
	SourceID              string     `json:"source_id"`
	Status                string     `json:"status"`
	Mode                  string     `json:"mode"`
	TriggerPolicy         string     `json:"trigger_policy,omitempty"`
	SelectionToken        string     `json:"selection_token,omitempty"`
	UpdatedOnly           bool       `json:"updated_only"`
	RequestedCount        int        `json:"requested_count"`
	AcceptedCount         int        `json:"accepted_count"`
	SkippedCount          int        `json:"skipped_count"`
	IgnoredUnchangedCount int        `json:"ignored_unchanged_count,omitempty"`
	ErrorMessage          string     `json:"error_message,omitempty"`
	CreatedAt             time.Time  `json:"created_at"`
	UpdatedAt             time.Time  `json:"updated_at"`
	FinishedAt            *time.Time `json:"finished_at,omitempty"`
}

type ListManualPullJobsResponse struct {
	Items    []ManualPullJob `json:"items"`
	Total    int64           `json:"total"`
	Page     int             `json:"page"`
	PageSize int             `json:"page_size"`
}

type BrowseRequest struct {
	Path string `json:"path"`
}

type BrowseEntry struct {
	Name  string `json:"name"`
	Path  string `json:"path"`
	IsDir bool   `json:"is_dir"`
}

type BrowseResponse struct {
	Path    string        `json:"path"`
	Entries []BrowseEntry `json:"entries"`
}

type KnowledgeBaseAlgo struct {
	AlgoID      string `json:"algo_id"`
	Description string `json:"description,omitempty"`
	DisplayName string `json:"display_name,omitempty"`
}

type CreateKnowledgeBaseRequest struct {
	Name string            `json:"name"`
	Algo KnowledgeBaseAlgo `json:"algo"`
}

type CreateKnowledgeBaseResponse struct {
	DatasetID string `json:"dataset_id"`
	Name      string `json:"name"`
}
