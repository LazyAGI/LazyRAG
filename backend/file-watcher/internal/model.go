package internal

import "time"

// ─── Agent 状态枚举 ───────────────────────────────────────────────────────────

type AgentStatus string

const (
	AgentStatusRegistering AgentStatus = "REGISTERING"
	AgentStatusOnline      AgentStatus = "ONLINE"
	AgentStatusDegraded    AgentStatus = "DEGRADED"
	AgentStatusOffline     AgentStatus = "OFFLINE"
	AgentStatusUnhealthy   AgentStatus = "UNHEALTHY"
)

// ─── Source 运行时状态枚举 ────────────────────────────────────────────────────

type SourceRuntimeStatus string

const (
	SourceRuntimeStatusStarting        SourceRuntimeStatus = "STARTING"
	SourceRuntimeStatusInitialScanning SourceRuntimeStatus = "INITIAL_SCANNING"
	SourceRuntimeStatusWatching        SourceRuntimeStatus = "WATCHING"
	SourceRuntimeStatusRunning         SourceRuntimeStatus = "RUNNING"
	SourceRuntimeStatusStopped         SourceRuntimeStatus = "STOPPED"
	SourceRuntimeStatusDegraded        SourceRuntimeStatus = "DEGRADED"
	SourceRuntimeStatusError           SourceRuntimeStatus = "ERROR"
)

// ─── 扫描模式枚举 ─────────────────────────────────────────────────────────────

type ScanMode string

const (
	ScanModeFull      ScanMode = "full"
	ScanModeReconcile ScanMode = "reconcile"
)

// ─── 控制面指令类型枚举 ───────────────────────────────────────────────────────

type CommandType string

const (
	CommandReloadSource   CommandType = "reload_source"
	CommandStartSource    CommandType = "start_source"
	CommandStopSource     CommandType = "stop_source"
	CommandScanSource     CommandType = "scan_source"
	CommandStageFile      CommandType = "stage_file"
	CommandSnapshotSource CommandType = "snapshot_source"
)

// ─── 错误码枚举 ───────────────────────────────────────────────────────────────

type ErrorCode string

const (
	ErrInvalidPath      ErrorCode = "INVALID_PATH"
	ErrPathNotAllowed   ErrorCode = "PATH_NOT_ALLOWED"
	ErrPermissionDenied ErrorCode = "PERMISSION_DENIED"
	ErrWatchStartFailed ErrorCode = "WATCH_START_FAILED"
	ErrScanFailed       ErrorCode = "SCAN_FAILED"
	ErrStageFailed      ErrorCode = "STAGE_FAILED"
	ErrControlPlaneDown ErrorCode = "CONTROL_PLANE_DOWN"
)

// ─── 文件事件类型 ─────────────────────────────────────────────────────────────

type FileEventType string

const (
	FileCreated  FileEventType = "created"
	FileModified FileEventType = "modified"
	FileDeleted  FileEventType = "deleted"
	FileRenamed  FileEventType = "renamed"
)

// ─── 核心数据结构 ─────────────────────────────────────────────────────────────

// SourceRuntime 表示 Agent 侧一个正在运行的本地 Source。
type SourceRuntime struct {
	SourceID         string
	TenantID         string
	RootPath         string
	Status           SourceRuntimeStatus
	WatcherEnabled   bool
	WatcherHealthy   bool
	WatcherLastError string
	LastScanAt       time.Time
	LastEventAt      time.Time
	LastReconcileAt  time.Time
	Cancel           func() // context.CancelFunc
}

// FileMeta 文件元数据。
type FileMeta struct {
	Path          string
	CanonicalPath string
	Name          string
	Size          int64
	ModTime       time.Time
	IsDir         bool
	MimeType      string
	Checksum      string
}

// FileEvent 文件变更事件。
type FileEvent struct {
	SourceID   string        `json:"source_id"`
	TenantID   string        `json:"tenant_id"`
	EventType  FileEventType `json:"event_type"`
	Path       string        `json:"path"`
	OldPath    string        `json:"old_path,omitempty"`
	IsDir      bool          `json:"is_dir"`
	OccurredAt time.Time     `json:"occurred_at"`
	TraceID    string        `json:"trace_id,omitempty"`
}

// HeartbeatPayload 心跳上报结构。
type HeartbeatPayload struct {
	AgentID          string         `json:"agent_id"`
	TenantID         string         `json:"tenant_id"`
	Hostname         string         `json:"hostname"`
	Version          string         `json:"version"`
	Status           AgentStatus    `json:"status"`
	LastHeartbeatAt  time.Time      `json:"last_heartbeat_at"`
	SourceCount      int            `json:"source_count"`
	ActiveWatchCount int            `json:"active_watch_count"`
	ActiveTaskCount  int            `json:"active_task_count"`
	ListenAddr       string         `json:"listen_addr,omitempty"`
	LastError        string         `json:"last_error,omitempty"`
	ResourceUsage    map[string]any `json:"resource_usage_json,omitempty"`
}

// ScanRecord 单条扫描记录，用于批量上报。
type ScanRecord struct {
	SourceID string    `json:"source_id"`
	Path     string    `json:"path"`
	IsDir    bool      `json:"is_dir"`
	Size     int64     `json:"size"`
	ModTime  time.Time `json:"mod_time"`
	Checksum string    `json:"checksum,omitempty"`
}

// SnapshotEntry reconcile 快照中的单条记录。
type SnapshotEntry struct {
	Size     int64
	ModTime  time.Time
	IsDir    bool
	Checksum string
}

// Snapshot reconcile 快照。
type Snapshot struct {
	SourceID string
	Files    map[string]SnapshotEntry
	TakenAt  time.Time
}

// StageResult staging 复制结果。
type StageResult struct {
	HostPath      string
	ContainerPath string
	URI           string
	Size          int64
}

// ─── HTTP DTO ─────────────────────────────────────────────────────────────────

type BrowseRequest struct {
	Path string `json:"path"`
}

type BrowseEntry struct {
	Name    string    `json:"name"`
	Path    string    `json:"path"`
	IsDir   bool      `json:"is_dir"`
	Size    int64     `json:"size"`
	ModTime time.Time `json:"mod_time"`
}

type BrowseResponse struct {
	Path    string        `json:"path"`
	Entries []BrowseEntry `json:"entries"`
}

type ValidatePathRequest struct {
	Path string `json:"path"`
}

type ValidatePathResponse struct {
	Path     string `json:"path"`
	Exists   bool   `json:"exists"`
	Readable bool   `json:"readable"`
	IsDir    bool   `json:"is_dir"`
	Allowed  bool   `json:"allowed"`
	Reason   string `json:"reason"`
}

type StartSourceRequest struct {
	SourceID          string `json:"source_id"`
	TenantID          string `json:"tenant_id"`
	RootPath          string `json:"root_path"`
	SkipInitialScan   bool   `json:"skip_initial_scan,omitempty"`
	ReconcileSeconds  int64  `json:"reconcile_seconds,omitempty"`
	ReconcileSchedule string `json:"reconcile_schedule,omitempty"`
}

type StartSourceResponse struct {
	Started bool `json:"started"`
}

type StopSourceRequest struct {
	SourceID string `json:"source_id"`
}

type ScanSourceRequest struct {
	SourceID string   `json:"source_id"`
	Mode     ScanMode `json:"mode"`
}

type AcceptedResponse struct {
	Accepted bool `json:"accepted"`
}

type StatFileRequest struct {
	Path string `json:"path"`
}

type StatFileResponse struct {
	Path     string    `json:"path"`
	Size     int64     `json:"size"`
	ModTime  time.Time `json:"mod_time"`
	IsDir    bool      `json:"is_dir"`
	MimeType string    `json:"mime_type"`
	Checksum string    `json:"checksum,omitempty"`
}

type TreeRequest struct {
	Path         string `json:"path"`
	MaxDepth     int    `json:"max_depth,omitempty"`
	IncludeFiles bool   `json:"include_files,omitempty"`
}

type TreeNode struct {
	Title    string     `json:"title"`
	Key      string     `json:"key"`
	IsDir    bool       `json:"is_dir"`
	Children []TreeNode `json:"children,omitempty"`
}

type TreeResponse struct {
	Items []TreeNode `json:"items"`
}

type ErrorResponse struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

// ─── 控制面客户端 DTO ─────────────────────────────────────────────────────────

type RegisterAgentRequest struct {
	AgentID    string `json:"agent_id"`
	TenantID   string `json:"tenant_id"`
	Hostname   string `json:"hostname"`
	Version    string `json:"version"`
	ListenAddr string `json:"listen_addr,omitempty"`
}

type ReportEventsRequest struct {
	AgentID string      `json:"agent_id"`
	Events  []FileEvent `json:"events"`
}

type ReportScanResultsRequest struct {
	AgentID  string       `json:"agent_id"`
	SourceID string       `json:"source_id"`
	Mode     ScanMode     `json:"mode"`
	Records  []ScanRecord `json:"records"`
}

type PullCommandsRequest struct {
	AgentID  string `json:"agent_id"`
	TenantID string `json:"tenant_id"`
}

type Command struct {
	ID                int64       `json:"id"`
	Type              CommandType `json:"type"`
	TenantID          string      `json:"tenant_id,omitempty"`
	SourceID          string      `json:"source_id,omitempty"`
	RootPath          string      `json:"root_path,omitempty"`
	Mode              ScanMode    `json:"mode,omitempty"`
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

// ─── Staging HTTP DTO ─────────────────────────────────────────────────────────

type StageFileRequest struct {
	SourceID   string `json:"source_id"`
	DocumentID string `json:"document_id"`
	VersionID  string `json:"version_id"`
	SrcPath    string `json:"src_path"`
}

type StageFileResponse struct {
	HostPath      string `json:"host_path"`
	ContainerPath string `json:"container_path"`
	URI           string `json:"uri"`
	Size          int64  `json:"size"`
}

type PullCommandsResponse struct {
	Commands []Command `json:"commands"`
}
