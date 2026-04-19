package store

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.uber.org/zap"
	"gorm.io/driver/postgres"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
)

type Store struct {
	db                *gorm.DB
	defaultIdleWindow time.Duration
	defaultScheduleTZ string
	log               *zap.Logger
}

type DocumentMutation struct {
	TenantID          string
	SourceID          string
	SourceObjectID    string
	IdleWindowSeconds int64
	EventType         string
	OccurredAt        time.Time
	OriginType        string
	OriginPlatform    string
	OriginRef         string
	TriggerPolicy     string
}

type PendingTask struct {
	TaskID           int64
	TenantID         string
	DocumentID       int64
	TaskAction       string
	TargetVersionID  string
	IdempotencyKey   string
	RetryCount       int
	MaxRetryCount    int
	OriginType       string
	OriginPlatform   string
	TriggerPolicy    string
	SourceID         string
	SourceDatasetID  string
	CoreDocumentID   string
	SourceObjectID   string
	DesiredVersionID string
	AgentID          string
	AgentListenAddr  string
}

type StageCommandPayload struct {
	SourceID   string `json:"source_id"`
	DocumentID string `json:"document_id"`
	VersionID  string `json:"version_id"`
	SrcPath    string `json:"src_path"`
}

type parseTaskFilter struct {
	TenantID string
	SourceID string
	Statuses []string
	Keyword  string
}

type treeDocumentRow struct {
	ID               int64
	SourceObjectID   string
	DesiredVersionID string
	CurrentVersionID string
	ParseStatus      string
}

type parseTaskDocJoin struct {
	DocumentID              int64
	TaskAction              string
	CoreDocumentID          string
	Status                  string
	CoreDatasetID           string
	CoreTaskID              string
	ScanOrchestrationStatus string
}

type SourceDocumentCoreRef struct {
	DocumentID       int64
	ParseStatus      string
	DesiredVersionID string
	CurrentVersionID string
	UpdatedAt        time.Time
	CoreDatasetID    string
	CoreDocumentID   string
	CoreTaskID       string
}

type cloudSyncClaimRow struct {
	SourceID              string
	TenantID              string
	RootPath              string
	Provider              string
	AuthConnectionID      string
	TargetType            string
	TargetRef             string
	ScheduleExpr          string
	ScheduleTZ            string
	ReconcileAfterSync    bool
	ReconcileDelayMinutes int
	IncludePatternsJSON   string
	ExcludePatternsJSON   string
	MaxObjectSizeBytes    int64
	ProviderOptionsJSON   string
	LastRunID             string
}

type CloudSyncClaim struct {
	SourceID              string
	TenantID              string
	RootPath              string
	Provider              string
	AuthConnectionID      string
	TargetType            string
	TargetRef             string
	ScheduleExpr          string
	ScheduleTZ            string
	ReconcileAfterSync    bool
	ReconcileDelayMinutes int
	IncludePatterns       []string
	ExcludePatterns       []string
	MaxObjectSizeBytes    int64
	ProviderOptions       map[string]any
	ExistingRunID         string
}

type CloudObjectIndexRecord struct {
	SourceID           string
	Provider           string
	ExternalObjectID   string
	ExternalParentID   string
	ExternalPath       string
	ExternalName       string
	ExternalKind       string
	ExternalVersion    string
	ExternalModifiedAt *time.Time
	LocalRelPath       string
	LocalAbsPath       string
	Checksum           string
	SizeBytes          int64
	IsDeleted          bool
	LastSyncedAt       *time.Time
	ProviderMeta       map[string]any
}

type CloudSyncRunFinalize struct {
	RunID        string
	Status       string
	FinishedAt   time.Time
	RemoteTotal  int
	CreatedCount int
	UpdatedCount int
	DeletedCount int
	SkippedCount int
	FailedCount  int
	ErrorCode    string
	ErrorMessage string
}

const (
	commandStatusPending    = "PENDING"
	commandStatusDispatched = "DISPATCHED"
	commandStatusAcked      = "ACKED"
	commandStatusFailed     = "FAILED"
	selectionTokenTTL       = 30 * time.Minute
	defaultScheduleTZ       = "Asia/Shanghai"

	taskActionCreate  = "CREATE"
	taskActionReparse = "REPARSE"
	taskActionDelete  = "DELETE"
)

var ErrTreePathInvalid = errors.New("tree path invalid")
var ErrCloudSyncLocked = errors.New("cloud sync source is locked")

func New(driver, dsn string, defaultIdleWindow time.Duration, log *zap.Logger) (*Store, error) {
	driver = strings.ToLower(strings.TrimSpace(driver))
	if driver == "" {
		driver = "postgres"
	}
	dsn = strings.TrimSpace(dsn)

	var dialector gorm.Dialector
	switch driver {
	case "postgres", "postgresql":
		dialector = postgres.Open(dsn)
	case "sqlite":
		sqliteDSN := dsn
		if sqliteDSN != ":memory:" && !strings.HasPrefix(sqliteDSN, "file:") {
			sqliteDSN = fmt.Sprintf("file:%s?_busy_timeout=5000&_journal_mode=WAL", sqliteDSN)
		}
		dialector = sqlite.Open(sqliteDSN)
	default:
		return nil, fmt.Errorf("unsupported database_driver: %s", driver)
	}

	db, err := gorm.Open(dialector, &gorm.Config{})
	if err != nil {
		return nil, fmt.Errorf("open %s via gorm: %w", driver, err)
	}

	s := &Store{
		db:                db,
		defaultIdleWindow: defaultIdleWindow,
		defaultScheduleTZ: defaultScheduleTZ,
		log:               log,
	}
	if err := s.migrate(context.Background()); err != nil {
		return nil, err
	}
	return s, nil
}

func (s *Store) SetDefaultCloudScheduleTZ(tz string) {
	value := strings.TrimSpace(tz)
	if value == "" {
		value = defaultScheduleTZ
	}
	s.defaultScheduleTZ = value
}

func (s *Store) Close() error {
	sqlDB, err := s.db.DB()
	if err != nil {
		return err
	}
	return sqlDB.Close()
}

func (s *Store) migrate(ctx context.Context) error {
	if err := s.db.WithContext(ctx).AutoMigrate(
		&sourceEntity{},
		&cloudSourceBindingEntity{},
		&cloudSyncCheckpointEntity{},
		&cloudObjectIndexEntity{},
		&cloudSyncRunEntity{},
		&agentEntity{},
		&agentCommandEntity{},
		&documentEntity{},
		&parseTaskEntity{},
		&parseTaskDeadLetterEntity{},
		&reconcileSnapshotEntity{},
		&sourceBaselineSnapshotEntity{},
		&sourceFileSnapshotEntity{},
		&sourceFileSnapshotItemEntity{},
		&sourceSnapshotRelationEntity{},
		&manualPullJobEntity{},
	); err != nil {
		return err
	}
	return s.ensureParseTaskIndexes(ctx)
}

func (s *Store) ensureParseTaskIndexes(ctx context.Context) error {
	switch s.db.Dialector.Name() {
	case "postgres":
		// 兼容历史 schema：旧版本使用 document_id 全局唯一索引/约束。
		if err := s.db.WithContext(ctx).Exec("ALTER TABLE parse_tasks DROP CONSTRAINT IF EXISTS uk_parse_task_document").Error; err != nil {
			return err
		}
	}
	if err := s.db.WithContext(ctx).Exec("DROP INDEX IF EXISTS uk_parse_task_document").Error; err != nil {
		return err
	}
	if err := s.db.WithContext(ctx).Exec(
		"CREATE UNIQUE INDEX IF NOT EXISTS uk_parse_task_document_pending ON parse_tasks (document_id) WHERE status IN ('PENDING','RETRY_WAITING')",
	).Error; err != nil {
		return err
	}
	indexSQLs := []string{
		"CREATE INDEX IF NOT EXISTS idx_parse_tasks_tenant_status_updated ON parse_tasks (tenant_id, status, updated_at)",
		"CREATE INDEX IF NOT EXISTS idx_parse_tasks_core_task ON parse_tasks (core_task_id)",
		"CREATE INDEX IF NOT EXISTS idx_parse_tasks_orchestration_status ON parse_tasks (scan_orchestration_status)",
		"CREATE INDEX IF NOT EXISTS idx_parse_tasks_idempotency ON parse_tasks (idempotency_key)",
	}
	for _, sql := range indexSQLs {
		if err := s.db.WithContext(ctx).Exec(sql).Error; err != nil {
			return err
		}
	}
	return nil
}
