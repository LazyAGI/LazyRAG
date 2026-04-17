package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"go.uber.org/zap"
	"gorm.io/driver/postgres"
	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"github.com/lazyrag/scan_control_plane/internal/model"
)

type Store struct {
	db                *gorm.DB
	defaultIdleWindow time.Duration
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

const (
	commandStatusPending    = "PENDING"
	commandStatusDispatched = "DISPATCHED"
	commandStatusAcked      = "ACKED"
	commandStatusFailed     = "FAILED"
	selectionTokenTTL       = 30 * time.Minute

	taskActionCreate  = "CREATE"
	taskActionReparse = "REPARSE"
	taskActionDelete  = "DELETE"
)

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

	s := &Store{db: db, defaultIdleWindow: defaultIdleWindow, log: log}
	if err := s.migrate(context.Background()); err != nil {
		return nil, err
	}
	return s, nil
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

func sourceID() string {
	return fmt.Sprintf("src_%d", time.Now().UnixNano())
}

func manualPullJobID() string {
	return fmt.Sprintf("mpj_%d", time.Now().UnixNano())
}

func normalizeReconcilePolicy(reconcileSeconds int64, reconcileSchedule string, fallbackSeconds int64) (int64, string, error) {
	schedule := strings.TrimSpace(reconcileSchedule)
	if schedule == "" {
		if reconcileSeconds <= 0 {
			reconcileSeconds = fallbackSeconds
		}
		return reconcileSeconds, "", nil
	}
	if _, _, _, err := parseReconcileScheduleExpr(schedule); err != nil {
		return 0, "", err
	}
	if reconcileSeconds <= 0 {
		reconcileSeconds = fallbackSeconds
	}
	return reconcileSeconds, schedule, nil
}

func parseReconcileScheduleExpr(expr string) (everyDays int, hour int, minute int, err error) {
	raw := strings.TrimSpace(expr)
	if raw == "" {
		return 0, 0, 0, fmt.Errorf("reconcile_schedule is empty")
	}
	lower := strings.ToLower(raw)
	if strings.HasPrefix(lower, "daily@") {
		h, m, perr := parseHourMinuteToken(raw[len("daily@"):])
		if perr != nil {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: %w", expr, perr)
		}
		return 1, h, m, nil
	}
	if strings.HasPrefix(lower, "every") && strings.Contains(lower, "d@") {
		pos := strings.Index(lower, "d@")
		dayToken := strings.TrimSpace(raw[len("every"):pos])
		days, derr := strconv.Atoi(dayToken)
		if derr != nil || days <= 0 {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: invalid everyNd day token", expr)
		}
		h, m, perr := parseHourMinuteToken(raw[pos+2:])
		if perr != nil {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: %w", expr, perr)
		}
		return days, h, m, nil
	}
	if strings.HasPrefix(raw, "每天") {
		h, m, perr := parseHourMinuteToken(strings.TrimSpace(strings.TrimPrefix(raw, "每天")))
		if perr != nil {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: %w", expr, perr)
		}
		return 1, h, m, nil
	}
	if strings.HasPrefix(raw, "每") && strings.Contains(raw, "天") {
		pos := strings.Index(raw, "天")
		dayToken := strings.TrimSpace(raw[len("每"):pos])
		timeToken := strings.TrimSpace(raw[pos+len("天"):])
		days, derr := parseDayToken(dayToken)
		if derr != nil {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: %w", expr, derr)
		}
		h, m, perr := parseHourMinuteToken(timeToken)
		if perr != nil {
			return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule %q: %w", expr, perr)
		}
		return days, h, m, nil
	}
	return 0, 0, 0, fmt.Errorf("invalid reconcile_schedule format: %q", expr)
}

func parseHourMinuteToken(token string) (int, int, error) {
	value := strings.TrimSpace(token)
	if value == "" {
		return 0, 0, fmt.Errorf("time token is empty")
	}
	value = strings.ReplaceAll(value, "：", ":")
	if strings.Contains(value, ":") {
		parts := strings.Split(value, ":")
		if len(parts) != 2 {
			return 0, 0, fmt.Errorf("invalid hh:mm")
		}
		h, errH := strconv.Atoi(strings.TrimSpace(parts[0]))
		m, errM := strconv.Atoi(strings.TrimSpace(parts[1]))
		if errH != nil || errM != nil {
			return 0, 0, fmt.Errorf("invalid hh:mm")
		}
		if h < 0 || h > 23 || m < 0 || m > 59 {
			return 0, 0, fmt.Errorf("hour/minute out of range")
		}
		return h, m, nil
	}
	value = strings.ReplaceAll(value, "时", "点")
	if strings.Contains(value, "点") {
		parts := strings.SplitN(value, "点", 2)
		if len(parts) != 2 {
			return 0, 0, fmt.Errorf("invalid 点 format")
		}
		h, err := strconv.Atoi(strings.TrimSpace(parts[0]))
		if err != nil {
			return 0, 0, fmt.Errorf("invalid hour")
		}
		minuteRaw := strings.TrimSpace(parts[1])
		minuteRaw = strings.TrimSuffix(minuteRaw, "分")
		m := 0
		if strings.TrimSpace(minuteRaw) != "" {
			mv, err := strconv.Atoi(strings.TrimSpace(minuteRaw))
			if err != nil {
				return 0, 0, fmt.Errorf("invalid minute")
			}
			m = mv
		}
		if h < 0 || h > 23 || m < 0 || m > 59 {
			return 0, 0, fmt.Errorf("hour/minute out of range")
		}
		return h, m, nil
	}
	// Fallback: only hour token.
	h, err := strconv.Atoi(value)
	if err != nil {
		return 0, 0, fmt.Errorf("invalid hour")
	}
	if h < 0 || h > 23 {
		return 0, 0, fmt.Errorf("hour out of range")
	}
	return h, 0, nil
}

func parseDayToken(token string) (int, error) {
	raw := strings.TrimSpace(token)
	if raw == "" {
		return 0, fmt.Errorf("empty day token")
	}
	if v, err := strconv.Atoi(raw); err == nil && v > 0 {
		return v, nil
	}
	parsed := parseChineseNumber(raw)
	if parsed <= 0 {
		return 0, fmt.Errorf("invalid day token")
	}
	return parsed, nil
}

func parseChineseNumber(raw string) int {
	s := strings.TrimSpace(raw)
	if s == "" {
		return 0
	}
	digit := map[string]int{
		"零": 0,
		"一": 1,
		"二": 2,
		"两": 2,
		"三": 3,
		"四": 4,
		"五": 5,
		"六": 6,
		"七": 7,
		"八": 8,
		"九": 9,
	}
	if v, ok := digit[s]; ok {
		return v
	}
	if strings.Contains(s, "十") {
		parts := strings.SplitN(s, "十", 2)
		tens := 1
		if strings.TrimSpace(parts[0]) != "" {
			v, ok := digit[strings.TrimSpace(parts[0])]
			if !ok {
				return 0
			}
			tens = v
		}
		ones := 0
		if len(parts) > 1 && strings.TrimSpace(parts[1]) != "" {
			v, ok := digit[strings.TrimSpace(parts[1])]
			if !ok {
				return 0
			}
			ones = v
		}
		return tens*10 + ones
	}
	return 0
}

func (s *Store) CreateSource(ctx context.Context, req model.CreateSourceRequest) (model.Source, error) {
	if req.TenantID == "" || req.Name == "" || req.RootPath == "" || req.AgentID == "" {
		return model.Source{}, fmt.Errorf("tenant_id/name/root_path/agent_id are required")
	}
	return s.ensureSourceByRootPath(ctx, req)
}

func (s *Store) ensureSourceByRootPath(ctx context.Context, req model.CreateSourceRequest) (model.Source, error) {
	if req.TenantID == "" || req.Name == "" || req.RootPath == "" || req.AgentID == "" {
		return model.Source{}, fmt.Errorf("tenant_id/name/root_path/agent_id are required")
	}
	rootPath := filepath.Clean(strings.TrimSpace(req.RootPath))
	if rootPath == "." || rootPath == "" {
		return model.Source{}, fmt.Errorf("root_path is required")
	}

	idle := req.IdleWindowSeconds
	if idle <= 0 {
		idle = int64(s.defaultIdleWindow.Seconds())
	}
	reconcile, reconcileSchedule, err := normalizeReconcilePolicy(req.ReconcileSeconds, req.ReconcileSchedule, 600)
	if err != nil {
		return model.Source{}, err
	}
	defaultOriginType := strings.TrimSpace(req.DefaultOriginType)
	if defaultOriginType == "" {
		defaultOriginType = string(model.OriginTypeLocalFS)
	}
	defaultOriginPlatform := strings.TrimSpace(req.DefaultOriginPlatform)
	if defaultOriginPlatform == "" {
		defaultOriginPlatform = "LOCAL"
	}
	defaultTriggerPolicy := strings.TrimSpace(req.DefaultTriggerPolicy)
	if defaultTriggerPolicy == "" {
		defaultTriggerPolicy = string(model.TriggerPolicyIdleWindow)
	}
	datasetID := strings.TrimSpace(req.DatasetID)

	now := time.Now().UTC()
	err = s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var existing sourceEntity
		findErr := tx.Where("tenant_id = ? AND agent_id = ? AND root_path = ?", req.TenantID, req.AgentID, rootPath).Take(&existing).Error
		if findErr == nil {
			existing.Name = req.Name
			existing.IdleWindowSeconds = idle
			existing.ReconcileSeconds = reconcile
			existing.ReconcileSchedule = reconcileSchedule
			if datasetID != "" {
				existing.DatasetID = datasetID
			}
			existing.DefaultOriginType = defaultOriginType
			existing.DefaultOriginPlatform = defaultOriginPlatform
			existing.DefaultTriggerPolicy = defaultTriggerPolicy
			existing.UpdatedAt = now
			if req.WatchEnabled {
				existing.WatchEnabled = true
				existing.Status = string(model.SourceStatusEnabled)
				existing.WatchUpdatedAt = &now
			}
			if err := tx.Save(&existing).Error; err != nil {
				return err
			}
			if req.WatchEnabled {
				return enqueueSourceCommand(tx, existing.AgentID, model.CommandStartSource, model.SourcePayload{
					SourceID:          existing.ID,
					TenantID:          existing.TenantID,
					RootPath:          existing.RootPath,
					SkipInitialScan:   false,
					ReconcileSeconds:  existing.ReconcileSeconds,
					ReconcileSchedule: existing.ReconcileSchedule,
				})
			}
			return nil
		}
		if findErr != nil && !errors.Is(findErr, gorm.ErrRecordNotFound) {
			return findErr
		}

		status := model.SourceStatusDisabled
		if req.WatchEnabled {
			status = model.SourceStatusEnabled
		}
		var watchUpdatedAt *time.Time
		if req.WatchEnabled {
			watchUpdatedAt = &now
		}

		src := sourceEntity{
			ID:                    sourceID(),
			TenantID:              req.TenantID,
			Name:                  req.Name,
			SourceType:            "local_fs",
			RootPath:              rootPath,
			Status:                string(status),
			WatchEnabled:          req.WatchEnabled,
			WatchUpdatedAt:        watchUpdatedAt,
			IdleWindowSeconds:     idle,
			ReconcileSeconds:      reconcile,
			ReconcileSchedule:     reconcileSchedule,
			AgentID:               req.AgentID,
			DatasetID:             datasetID,
			DefaultOriginType:     defaultOriginType,
			DefaultOriginPlatform: defaultOriginPlatform,
			DefaultTriggerPolicy:  defaultTriggerPolicy,
			CreatedAt:             now,
			UpdatedAt:             now,
		}
		if err := tx.Create(&src).Error; err != nil {
			return err
		}
		if !req.WatchEnabled {
			return nil
		}
		return enqueueSourceCommand(tx, src.AgentID, model.CommandStartSource, model.SourcePayload{
			SourceID:          src.ID,
			TenantID:          src.TenantID,
			RootPath:          src.RootPath,
			SkipInitialScan:   false,
			ReconcileSeconds:  src.ReconcileSeconds,
			ReconcileSchedule: src.ReconcileSchedule,
		})
	})
	if err != nil {
		return model.Source{}, err
	}
	var src sourceEntity
	if err := s.db.WithContext(ctx).Where("tenant_id = ? AND agent_id = ? AND root_path = ?", req.TenantID, req.AgentID, rootPath).Take(&src).Error; err != nil {
		return model.Source{}, err
	}
	return toModelSource(src), nil
}

func (s *Store) UpdateSource(ctx context.Context, id string, req model.UpdateSourceRequest) (model.Source, error) {
	var src sourceEntity
	if err := s.db.WithContext(ctx).First(&src, "id = ?", id).Error; err != nil {
		return model.Source{}, err
	}

	if req.Name != "" {
		src.Name = req.Name
	}
	if req.RootPath != "" {
		src.RootPath = filepath.Clean(strings.TrimSpace(req.RootPath))
	}
	if strings.TrimSpace(req.DatasetID) != "" {
		src.DatasetID = strings.TrimSpace(req.DatasetID)
	}
	if req.IdleWindowSeconds > 0 {
		src.IdleWindowSeconds = req.IdleWindowSeconds
	}
	if req.ReconcileSeconds > 0 {
		src.ReconcileSeconds = req.ReconcileSeconds
		src.ReconcileSchedule = ""
	}
	if strings.TrimSpace(req.ReconcileSchedule) != "" {
		reconcile, reconcileSchedule, err := normalizeReconcilePolicy(req.ReconcileSeconds, req.ReconcileSchedule, src.ReconcileSeconds)
		if err != nil {
			return model.Source{}, err
		}
		src.ReconcileSeconds = reconcile
		src.ReconcileSchedule = reconcileSchedule
	}
	if strings.TrimSpace(req.DefaultOriginType) != "" {
		src.DefaultOriginType = strings.TrimSpace(req.DefaultOriginType)
	}
	if strings.TrimSpace(req.DefaultOriginPlatform) != "" {
		src.DefaultOriginPlatform = strings.TrimSpace(req.DefaultOriginPlatform)
	}
	if strings.TrimSpace(req.DefaultTriggerPolicy) != "" {
		src.DefaultTriggerPolicy = strings.TrimSpace(req.DefaultTriggerPolicy)
	}
	src.UpdatedAt = time.Now().UTC()

	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Save(&src).Error; err != nil {
			return err
		}
		if src.Status == string(model.SourceStatusEnabled) && src.WatchEnabled {
			return enqueueSourceCommand(tx, src.AgentID, model.CommandReloadSource, model.SourcePayload{
				SourceID:          src.ID,
				TenantID:          src.TenantID,
				RootPath:          src.RootPath,
				SkipInitialScan:   true,
				ReconcileSeconds:  src.ReconcileSeconds,
				ReconcileSchedule: src.ReconcileSchedule,
			})
		}
		return nil
	})
	if err != nil {
		return model.Source{}, err
	}
	return toModelSource(src), nil
}

func (s *Store) SetSourceEnabled(ctx context.Context, id string, enabled bool) (model.Source, error) {
	var src sourceEntity
	if err := s.db.WithContext(ctx).First(&src, "id = ?", id).Error; err != nil {
		return model.Source{}, err
	}

	now := time.Now().UTC()
	targetStatus := model.SourceStatusDisabled
	cmdType := model.CommandStopSource
	if enabled {
		targetStatus = model.SourceStatusEnabled
		cmdType = model.CommandStartSource
	}

	src.Status = string(targetStatus)
	src.WatchEnabled = enabled
	src.WatchUpdatedAt = &now
	src.UpdatedAt = now

	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Save(&src).Error; err != nil {
			return err
		}
		if !enabled {
			if err := enqueueSourceCommand(tx, src.AgentID, model.CommandSnapshotSource, model.SourcePayload{
				SourceID: src.ID,
				TenantID: src.TenantID,
				RootPath: src.RootPath,
				Reason:   "WATCH_STOP_BASELINE",
			}); err != nil {
				return err
			}
		}
		return enqueueSourceCommand(tx, src.AgentID, cmdType, model.SourcePayload{
			SourceID:          src.ID,
			TenantID:          src.TenantID,
			RootPath:          src.RootPath,
			SkipInitialScan:   enabled,
			ReconcileSeconds:  src.ReconcileSeconds,
			ReconcileSchedule: src.ReconcileSchedule,
		})
	})
	if err != nil {
		return model.Source{}, err
	}
	return toModelSource(src), nil
}

func (s *Store) ListSources(ctx context.Context, tenantID string) ([]model.Source, error) {
	var entities []sourceEntity
	db := s.db.WithContext(ctx).Order("created_at DESC")
	if tenantID != "" {
		db = db.Where("tenant_id = ?", tenantID)
	}
	if err := db.Find(&entities).Error; err != nil {
		return nil, err
	}

	result := make([]model.Source, 0, len(entities))
	for _, e := range entities {
		result = append(result, toModelSource(e))
	}
	return result, nil
}

func (s *Store) GetSource(ctx context.Context, id string) (model.Source, error) {
	var src sourceEntity
	if err := s.db.WithContext(ctx).First(&src, "id = ?", id).Error; err != nil {
		return model.Source{}, err
	}
	return toModelSource(src), nil
}

func (s *Store) ListSourceDocuments(ctx context.Context, sourceID string, req model.ListSourceDocumentsRequest) (model.SourceDocumentsResponse, error) {
	resp := model.SourceDocumentsResponse{
		Items: []model.SourceDocumentItem{},
	}
	tenantID := strings.TrimSpace(req.TenantID)
	if tenantID == "" {
		return resp, fmt.Errorf("tenant_id is required")
	}
	var src sourceEntity
	if err := s.db.WithContext(ctx).
		Where("id = ? AND tenant_id = ?", strings.TrimSpace(sourceID), tenantID).
		Take(&src).Error; err != nil {
		return resp, err
	}

	page, pageSize := normalizePageAndSize(req.Page, req.PageSize)
	resp.Page = page
	resp.PageSize = pageSize

	docQuery := s.db.WithContext(ctx).
		Model(&documentEntity{}).
		Where("tenant_id = ? AND source_id = ?", tenantID, src.ID)

	keyword := strings.TrimSpace(req.Keyword)
	if keyword != "" {
		pattern := "%" + keyword + "%"
		if s.db.Dialector.Name() == "postgres" {
			docQuery = docQuery.Where("source_object_id ILIKE ?", pattern)
		} else {
			docQuery = docQuery.Where("LOWER(source_object_id) LIKE ?", strings.ToLower(pattern))
		}
	}

	if parseStates := splitCSV(req.ParseState); len(parseStates) > 0 {
		docQuery = docQuery.Where("parse_status IN ?", parseStates)
	}

	updateType := normalizeUpdateTypeFilter(req.UpdateType)
	docQuery = applyUpdateTypeFilter(docQuery, updateType)

	if err := docQuery.Count(&resp.Total).Error; err != nil {
		return resp, err
	}

	offset := (page - 1) * pageSize
	var docs []documentEntity
	if err := docQuery.
		Order("updated_at DESC, id DESC").
		Offset(offset).
		Limit(pageSize).
		Find(&docs).Error; err != nil {
		return resp, err
	}

	docIDs := make([]int64, 0, len(docs))
	for _, doc := range docs {
		docIDs = append(docIDs, doc.ID)
	}
	latestTasksByDocID, err := s.latestParseTasksByDocumentIDs(ctx, docIDs)
	if err != nil {
		return resp, err
	}

	for _, doc := range docs {
		update := inferDocumentUpdateType(doc.DesiredVersionID, doc.CurrentVersionID, doc.ParseStatus)
		var hasUpdate *bool
		switch update {
		case "NEW", "MODIFIED", "DELETED":
			v := true
			hasUpdate = &v
		case "UNCHANGED":
			v := false
			hasUpdate = &v
		}
		lastSyncedAt := doc.UpdatedAt
		latestTask := latestTasksByDocID[doc.ID]
		resp.Items = append(resp.Items, model.SourceDocumentItem{
			DocumentID:              doc.ID,
			Name:                    filepath.Base(doc.SourceObjectID),
			Path:                    doc.SourceObjectID,
			Directory:               filepath.Base(filepath.Dir(doc.SourceObjectID)),
			HasUpdate:               hasUpdate,
			UpdateType:              update,
			UpdateDesc:              updateTypeDescription(update),
			ParseState:              doc.ParseStatus,
			FileType:                fileTypeFromPath(doc.SourceObjectID),
			SizeBytes:               0,
			LastSyncedAt:            &lastSyncedAt,
			CoreDatasetID:           latestTask.CoreDatasetID,
			CoreTaskID:              latestTask.CoreTaskID,
			ScanOrchestrationStatus: latestTask.ScanOrchestrationStatus,
		})
	}

	type summaryDoc struct {
		ParseStatus      string
		DesiredVersionID string
		CurrentVersionID string
		UpdatedAt        time.Time
	}
	var summaryDocs []summaryDoc
	if err := s.db.WithContext(ctx).
		Table("documents").
		Select("parse_status, desired_version_id, current_version_id, updated_at").
		Where("tenant_id = ? AND source_id = ?", tenantID, src.ID).
		Scan(&summaryDocs).Error; err != nil {
		return resp, err
	}

	var (
		parsedCount int64
		newCount    int64
		modCount    int64
		delCount    int64
		latest      *time.Time
	)
	for _, doc := range summaryDocs {
		update := inferDocumentUpdateType(doc.DesiredVersionID, doc.CurrentVersionID, doc.ParseStatus)
		switch update {
		case "NEW":
			newCount++
		case "MODIFIED":
			modCount++
		case "DELETED":
			delCount++
		}
		if strings.TrimSpace(doc.CurrentVersionID) != "" && strings.ToUpper(strings.TrimSpace(doc.ParseStatus)) != "DELETED" {
			parsedCount++
		}
		updated := doc.UpdatedAt
		if latest == nil || updated.After(*latest) {
			latest = &updated
		}
	}

	agentOnline := false
	if strings.TrimSpace(src.AgentID) != "" {
		var agent agentEntity
		if err := s.db.WithContext(ctx).Take(&agent, "agent_id = ?", src.AgentID).Error; err == nil {
			agentOnline = strings.ToUpper(strings.TrimSpace(agent.Status)) != "OFFLINE"
		}
	}

	resp.Source = model.SourceDocumentsSource{
		ID:                      src.ID,
		Name:                    src.Name,
		RootPath:                src.RootPath,
		WatchEnabled:            src.WatchEnabled,
		AgentID:                 src.AgentID,
		AgentOnline:             agentOnline,
		UpdateTrackingSupported: true,
		LastSyncedAt:            latest,
	}
	resp.Summary = model.SourceDocumentsSummary{
		ParsedDocumentCount: parsedCount,
		StorageBytes:        0,
		TotalDocumentCount:  int64(len(summaryDocs)),
		NewCount:            newCount,
		ModifiedCount:       modCount,
		DeletedCount:        delCount,
		PendingPullCount:    newCount + modCount + delCount,
	}
	return resp, nil
}

func (s *Store) ListSourceDocumentCoreRefs(ctx context.Context, sourceID, tenantID string) ([]SourceDocumentCoreRef, error) {
	sourceID = strings.TrimSpace(sourceID)
	tenantID = strings.TrimSpace(tenantID)
	if sourceID == "" {
		return nil, fmt.Errorf("source_id is required")
	}
	if tenantID == "" {
		return nil, fmt.Errorf("tenant_id is required")
	}
	var src sourceEntity
	if err := s.db.WithContext(ctx).
		Where("id = ? AND tenant_id = ?", sourceID, tenantID).
		Take(&src).Error; err != nil {
		return nil, err
	}
	sub := s.db.WithContext(ctx).
		Table("parse_tasks").
		Select("MAX(id) AS max_id, document_id").
		Group("document_id")
	rows := make([]SourceDocumentCoreRef, 0, 128)
	if err := s.db.WithContext(ctx).
		Table("documents d").
		Select(`
			d.id AS document_id,
			d.parse_status AS parse_status,
			d.desired_version_id AS desired_version_id,
			d.current_version_id AS current_version_id,
			d.updated_at AS updated_at,
			pt.core_dataset_id AS core_dataset_id,
			d.core_document_id AS core_document_id,
			pt.core_task_id AS core_task_id
		`).
		Joins("LEFT JOIN (?) latest ON latest.document_id = d.id", sub).
		Joins("LEFT JOIN parse_tasks pt ON pt.id = latest.max_id").
		Where("d.tenant_id = ? AND d.source_id = ?", tenantID, src.ID).
		Scan(&rows).Error; err != nil {
		return nil, err
	}
	return rows, nil
}

func (s *Store) BuildTreeUpdateState(ctx context.Context, sourceID string, items []model.TreeNode, fileStats map[string]model.TreeFileStat) ([]model.TreeNode, string, error) {
	var src sourceEntity
	if err := s.db.WithContext(ctx).Take(&src, "id = ?", strings.TrimSpace(sourceID)).Error; err != nil {
		return nil, "", err
	}
	scopeRoots := collectTreeScopeRoots(items)
	filePaths := collectTreeFilePaths(items)
	pathMap := make(map[string]treeDocumentRow)
	queueMap := make(map[int64]parseTaskDocJoin)
	if len(filePaths) > 0 {
		var docs []treeDocumentRow
		if err := s.db.WithContext(ctx).
			Table("documents").
			Select("id, source_object_id, desired_version_id, current_version_id, parse_status").
			Where("source_id = ? AND source_object_id IN ?", src.ID, filePaths).
			Scan(&docs).Error; err != nil {
			return nil, "", err
		}
		for _, doc := range docs {
			pathMap[doc.SourceObjectID] = doc
		}
		docIDs := make([]int64, 0, len(docs))
		for _, doc := range docs {
			docIDs = append(docIDs, doc.ID)
		}
		latestTasks, err := s.latestParseTasksByDocumentIDs(ctx, docIDs)
		if err != nil {
			return nil, "", err
		}
		for docID, task := range latestTasks {
			queueMap[docID] = task
		}
	}

	selectionToken := fmt.Sprintf("sel_%s_%d", src.ID, time.Now().UTC().UnixNano())
	if src.WatchEnabled {
		// Even in watch mode we persist a preview snapshot so selection_token can be
		// strongly validated, expired and one-time consumed by tasks/generate.
		if _, err := s.createPreviewSnapshotAndDiff(ctx, src, scopeRoots, filePaths, fileStats, selectionToken); err != nil {
			return nil, "", err
		}
		updated := applyWatchTreeNodeStates(items, pathMap, queueMap)
		deletedPaths, err := s.deletedDocumentPaths(ctx, src.ID, scopeRoots, filePaths)
		if err != nil {
			return nil, "", err
		}
		updated = addDeletedNodes(updated, deletedPaths, src.RootPath, "DOCUMENTS", pathMap, queueMap)
		return updated, selectionToken, nil
	}

	diffByPath, err := s.createPreviewSnapshotAndDiff(ctx, src, scopeRoots, filePaths, fileStats, selectionToken)
	if err != nil {
		return nil, "", err
	}
	updated := applySnapshotTreeNodeStates(items, diffByPath, pathMap, queueMap)
	deletedPaths := collectDeletedPathsFromDiff(diffByPath, filePaths)
	updated = addDeletedNodes(updated, deletedPaths, src.RootPath, "SNAPSHOT", pathMap, queueMap)
	return updated, selectionToken, nil
}

func (s *Store) createPreviewSnapshotAndDiff(ctx context.Context, src sourceEntity, scopeRoots []string, filePaths []string, fileStats map[string]model.TreeFileStat, selectionToken string) (map[string]string, error) {
	currentItems := make([]sourceFileSnapshotItemEntity, 0, len(filePaths))
	now := time.Now().UTC()
	seen := make(map[string]struct{}, len(filePaths))
	for _, rawPath := range filePaths {
		path := filepath.Clean(strings.TrimSpace(rawPath))
		if path == "" || path == "." {
			continue
		}
		if _, ok := seen[path]; ok {
			continue
		}
		seen[path] = struct{}{}
		stat := fileStats[path]
		if strings.TrimSpace(stat.Path) == "" {
			stat.Path = path
		}
		item := sourceFileSnapshotItemEntity{
			Path:      path,
			IsDir:     stat.IsDir,
			SizeBytes: stat.Size,
			Checksum:  strings.TrimSpace(stat.Checksum),
		}
		if stat.ModTime != nil && !stat.ModTime.IsZero() {
			mt := stat.ModTime.UTC()
			item.ModTime = &mt
		}
		currentItems = append(currentItems, item)
	}

	var relation sourceSnapshotRelationEntity
	if err := s.db.WithContext(ctx).Take(&relation, "source_id = ?", src.ID).Error; err != nil {
		if !errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, err
		}
		relation = sourceSnapshotRelationEntity{SourceID: src.ID}
	}

	baseSnapshotID := strings.TrimSpace(relation.LastCommittedSnapshotID)
	previewSnapshotID := sourceSnapshotID()
	expiresAt := now.Add(selectionTokenTTL)
	preview := sourceFileSnapshotEntity{
		SnapshotID:     previewSnapshotID,
		SourceID:       src.ID,
		TenantID:       src.TenantID,
		SnapshotType:   "PREVIEW",
		BaseSnapshotID: baseSnapshotID,
		SelectionToken: strings.TrimSpace(selectionToken),
		ExpiresAt:      &expiresAt,
		FileCount:      int64(len(currentItems)),
		CreatedAt:      now,
	}

	if err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(&preview).Error; err != nil {
			return err
		}
		if len(currentItems) > 0 {
			rows := make([]sourceFileSnapshotItemEntity, 0, len(currentItems))
			for _, item := range currentItems {
				item.SnapshotID = previewSnapshotID
				rows = append(rows, item)
			}
			if err := tx.Create(&rows).Error; err != nil {
				return err
			}
		}
		return tx.Clauses(clause.OnConflict{
			Columns: []clause.Column{{Name: "source_id"}},
			DoUpdates: clause.Assignments(map[string]any{
				"last_preview_snapshot_id": previewSnapshotID,
				"updated_at":               now,
			}),
		}).Create(&sourceSnapshotRelationEntity{
			SourceID:              src.ID,
			LastPreviewSnapshotID: previewSnapshotID,
			UpdatedAt:             now,
		}).Error
	}); err != nil {
		return nil, err
	}

	baseItems, err := s.snapshotItemsByPath(ctx, baseSnapshotID)
	if err != nil {
		return nil, err
	}
	if len(scopeRoots) > 0 {
		filtered := make(map[string]sourceFileSnapshotItemEntity, len(baseItems))
		for path, item := range baseItems {
			if pathInScope(path, scopeRoots) {
				filtered[path] = item
			}
		}
		baseItems = filtered
	}
	currentMap := make(map[string]sourceFileSnapshotItemEntity, len(currentItems))
	for _, item := range currentItems {
		currentMap[item.Path] = item
	}
	return diffSnapshotMaps(baseItems, currentMap), nil
}

func sourceSnapshotID() string {
	return fmt.Sprintf("ss_%d", time.Now().UTC().UnixNano())
}

func parseTaskIdempotencyKey(documentID int64, targetVersionID, taskAction string) string {
	return fmt.Sprintf(
		"doc:%d|ver:%s|action:%s",
		documentID,
		strings.TrimSpace(targetVersionID),
		normalizeTaskAction(taskAction),
	)
}

func normalizeTaskAction(raw string) string {
	switch strings.ToUpper(strings.TrimSpace(raw)) {
	case taskActionDelete:
		return taskActionDelete
	case taskActionReparse:
		return taskActionReparse
	default:
		return taskActionCreate
	}
}

func inferTaskActionForDocument(doc documentEntity) string {
	if strings.EqualFold(strings.TrimSpace(doc.ParseStatus), "DELETED") {
		return taskActionDelete
	}
	if strings.TrimSpace(doc.CoreDocumentID) != "" {
		return taskActionReparse
	}
	return taskActionCreate
}

func diffSnapshotMaps(baseItems map[string]sourceFileSnapshotItemEntity, currentItems map[string]sourceFileSnapshotItemEntity) map[string]string {
	diff := make(map[string]string, len(baseItems)+len(currentItems))
	for path, current := range currentItems {
		base, ok := baseItems[path]
		if !ok {
			diff[path] = "NEW"
			continue
		}
		if snapshotItemChanged(base, current) {
			diff[path] = "MODIFIED"
			continue
		}
		diff[path] = "UNCHANGED"
	}
	for path := range baseItems {
		if _, ok := currentItems[path]; !ok {
			diff[path] = "DELETED"
		}
	}
	return diff
}

func snapshotItemChanged(base, current sourceFileSnapshotItemEntity) bool {
	if strings.TrimSpace(base.Checksum) != "" && strings.TrimSpace(current.Checksum) != "" {
		return strings.TrimSpace(base.Checksum) != strings.TrimSpace(current.Checksum)
	}
	if base.SizeBytes != current.SizeBytes {
		return true
	}
	if base.ModTime == nil && current.ModTime == nil {
		return false
	}
	if base.ModTime == nil || current.ModTime == nil {
		return true
	}
	return !base.ModTime.UTC().Equal(current.ModTime.UTC())
}

func (s *Store) snapshotItemsByPath(ctx context.Context, snapshotID string) (map[string]sourceFileSnapshotItemEntity, error) {
	itemsMap := make(map[string]sourceFileSnapshotItemEntity)
	snapshotID = strings.TrimSpace(snapshotID)
	if snapshotID == "" {
		return itemsMap, nil
	}
	var items []sourceFileSnapshotItemEntity
	if err := s.db.WithContext(ctx).Where("snapshot_id = ?", snapshotID).Find(&items).Error; err != nil {
		return nil, err
	}
	for _, item := range items {
		itemsMap[item.Path] = item
	}
	return itemsMap, nil
}

func (s *Store) GenerateTasksForSource(ctx context.Context, sourceID string, req model.GenerateTasksRequest) (resp model.GenerateTasksResponse, retErr error) {
	var src sourceEntity
	if err := s.db.WithContext(ctx).First(&src, "id = ?", strings.TrimSpace(sourceID)).Error; err != nil {
		return resp, err
	}
	now := time.Now().UTC()
	job := manualPullJobEntity{
		JobID:          manualPullJobID(),
		TenantID:       src.TenantID,
		SourceID:       src.ID,
		Status:         "RUNNING",
		Mode:           strings.TrimSpace(req.Mode),
		TriggerPolicy:  strings.TrimSpace(req.TriggerPolicy),
		SelectionToken: strings.TrimSpace(req.SelectionToken),
		UpdatedOnly:    req.UpdatedOnly,
		RequestedCount: len(req.Paths),
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	if job.Mode == "" {
		job.Mode = "partial"
	}
	if err := s.db.WithContext(ctx).Create(&job).Error; err != nil {
		return resp, err
	}
	resp.ManualPullJobID = job.JobID
	defer func() {
		updates := map[string]any{
			"accepted_count":          resp.AcceptedCount,
			"skipped_count":           resp.SkippedCount,
			"ignored_unchanged_count": resp.IgnoredUnchangedCount,
			"updated_at":              time.Now().UTC(),
		}
		finishedAt := time.Now().UTC()
		if retErr != nil {
			updates["status"] = "FAILED"
			updates["error_message"] = retErr.Error()
		} else {
			updates["status"] = "SUCCEEDED"
			updates["error_message"] = ""
		}
		updates["finished_at"] = &finishedAt
		if err := s.db.WithContext(ctx).Model(&manualPullJobEntity{}).Where("job_id = ?", job.JobID).Updates(updates).Error; err != nil && s.log != nil {
			s.log.Warn("finalize manual pull job failed", zap.String("job_id", job.JobID), zap.Error(err))
		}
	}()

	resp.RequestedCount = len(req.Paths)
	paths, invalid := normalizePathsUnderRoot(req.Paths, src.RootPath)
	resp.SkippedCount += invalid
	selectionToken := strings.TrimSpace(req.SelectionToken)
	if src.WatchEnabled && selectionToken == "" {
		return resp, fmt.Errorf("selection_token is required when watch is enabled")
	}

	var (
		selectedPreview *sourceFileSnapshotEntity
		diffByPath      map[string]string
	)
	if selectionToken != "" {
		preview, err := s.loadUsablePreviewSnapshotBySelectionToken(ctx, src.ID, selectionToken, now)
		if err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return resp, fmt.Errorf("invalid selection_token")
			}
			return resp, err
		}
		diff, err := s.diffBySnapshotID(ctx, preview)
		if err != nil {
			return resp, err
		}
		selectedPreview = &preview
		diffByPath = diff
	} else if !src.WatchEnabled {
		var relation sourceSnapshotRelationEntity
		if err := s.db.WithContext(ctx).Take(&relation, "source_id = ?", src.ID).Error; err == nil {
			if strings.TrimSpace(relation.LastPreviewSnapshotID) != "" {
				preview, err := s.loadSnapshotByID(ctx, relation.LastPreviewSnapshotID)
				if err == nil {
					diff, err := s.diffBySnapshotID(ctx, preview)
					if err != nil {
						return resp, err
					}
					selectedPreview = &preview
					diffByPath = diff
				}
			}
		}
	}

	if selectedPreview != nil && selectionToken != "" {
		unknownPaths := make([]string, 0, len(paths))
		for _, path := range paths {
			if _, ok := diffByPath[path]; !ok {
				unknownPaths = append(unknownPaths, path)
			}
		}
		if len(unknownPaths) > 0 {
			return resp, fmt.Errorf("paths not found in selection snapshot: %s", strings.Join(unknownPaths, ", "))
		}
	}

	if req.UpdatedOnly {
		if selectedPreview != nil {
			if src.WatchEnabled {
				filtered, ignored, err := s.filterPathsByUpdatedOnly(ctx, src.ID, paths)
				if err != nil {
					return resp, err
				}
				resp.IgnoredUnchangedCount = ignored
				resp.SkippedCount += ignored
				paths = filtered
			} else {
				filtered, ignored := filterPathsByDiff(paths, diffByPath)
				resp.IgnoredUnchangedCount = ignored
				resp.SkippedCount += ignored
				paths = filtered
			}
		} else {
			filtered, ignored, err := s.filterPathsByUpdatedOnly(ctx, src.ID, paths)
			if err != nil {
				return resp, err
			}
			resp.IgnoredUnchangedCount = ignored
			resp.SkippedCount += ignored
			paths = filtered
		}
	}
	if len(paths) == 0 {
		if selectedPreview != nil {
			if err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
				if err := s.promotePreviewSnapshotToCommittedTx(tx, src.ID, selectedPreview.SnapshotID, now); err != nil {
					return err
				}
				if selectionToken != "" {
					return s.consumeSelectionTokenTx(tx, selectedPreview.SnapshotID, now)
				}
				return nil
			}); err != nil {
				return resp, err
			}
		}
		return resp, nil
	}
	pathEventType := make(map[string]string, len(paths))
	for _, path := range paths {
		pathEventType[path] = "modified"
	}
	if selectedPreview != nil && !src.WatchEnabled {
		for _, path := range paths {
			if strings.EqualFold(strings.TrimSpace(diffByPath[path]), "DELETED") {
				pathEventType[path] = "deleted"
			}
		}
	} else {
		var rows []struct {
			SourceObjectID string
			ParseStatus    string
		}
		if err := s.db.WithContext(ctx).
			Table("documents").
			Select("source_object_id, parse_status").
			Where("source_id = ? AND source_object_id IN ?", src.ID, paths).
			Scan(&rows).Error; err != nil {
			return resp, err
		}
		for _, row := range rows {
			if strings.EqualFold(strings.TrimSpace(row.ParseStatus), "DELETED") {
				pathEventType[filepath.Clean(strings.TrimSpace(row.SourceObjectID))] = "deleted"
			}
		}
	}
	events := make([]model.FileEvent, 0, len(paths))
	for i, p := range paths {
		eventType := normalizeEventType(pathEventType[p])
		events = append(events, model.FileEvent{
			SourceID:      src.ID,
			EventType:     eventType,
			Path:          p,
			IsDir:         false,
			OccurredAt:    now.Add(time.Duration(i) * time.Nanosecond),
			TriggerPolicy: strings.TrimSpace(req.TriggerPolicy),
		})
	}
	mutations, err := s.BuildMutationsFromEvents(ctx, events)
	if err != nil {
		return resp, err
	}
	resp.AcceptedCount = len(mutations)
	resp.SkippedCount += len(paths) - len(mutations)
	if err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		for _, m := range mutations {
			if err := applyDocumentMutation(tx, m, s.log); err != nil {
				return err
			}
		}
		if selectedPreview != nil {
			if err := s.promotePreviewSnapshotToCommittedTx(tx, src.ID, selectedPreview.SnapshotID, now); err != nil {
				return err
			}
			if selectionToken != "" {
				if err := s.consumeSelectionTokenTx(tx, selectedPreview.SnapshotID, now); err != nil {
					return err
				}
			}
		}
		if err := enqueueSourceCommand(tx, src.AgentID, model.CommandSnapshotSource, model.SourcePayload{
			SourceID: src.ID,
			TenantID: src.TenantID,
			RootPath: src.RootPath,
			Reason:   "UPLOAD_BASELINE",
		}); err != nil {
			return err
		}
		resp.BaselineSnapshotQueued = true
		return nil
	}); err != nil {
		return resp, err
	}
	return resp, nil
}

func (s *Store) ListManualPullJobs(ctx context.Context, sourceID string, req model.ListManualPullJobsRequest) (model.ListManualPullJobsResponse, error) {
	resp := model.ListManualPullJobsResponse{
		Items: []model.ManualPullJob{},
	}
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" {
		return resp, fmt.Errorf("source_id is required")
	}
	var src sourceEntity
	if err := s.db.WithContext(ctx).Take(&src, "id = ?", sourceID).Error; err != nil {
		return resp, err
	}
	page, pageSize := normalizePageAndSize(req.Page, req.PageSize)
	resp.Page = page
	resp.PageSize = pageSize
	query := s.db.WithContext(ctx).
		Model(&manualPullJobEntity{}).
		Where("source_id = ?", src.ID)
	if statuses := splitCSV(req.Status); len(statuses) > 0 {
		query = query.Where("status IN ?", statuses)
	}
	if err := query.Count(&resp.Total).Error; err != nil {
		return resp, err
	}
	var rows []manualPullJobEntity
	offset := (page - 1) * pageSize
	if err := query.
		Order("created_at DESC, job_id DESC").
		Offset(offset).
		Limit(pageSize).
		Find(&rows).Error; err != nil {
		return resp, err
	}
	resp.Items = make([]model.ManualPullJob, 0, len(rows))
	for _, row := range rows {
		resp.Items = append(resp.Items, toModelManualPullJob(row))
	}
	return resp, nil
}

func (s *Store) EnableSourceWatch(ctx context.Context, sourceID string, req model.EnableWatchRequest) (model.Source, error) {
	var src sourceEntity
	if err := s.db.WithContext(ctx).First(&src, "id = ?", strings.TrimSpace(sourceID)).Error; err != nil {
		return model.Source{}, err
	}
	now := time.Now().UTC()
	switch {
	case strings.TrimSpace(req.ReconcileSchedule) != "":
		reconcile, reconcileSchedule, err := normalizeReconcilePolicy(req.ReconcileSeconds, req.ReconcileSchedule, src.ReconcileSeconds)
		if err != nil {
			return model.Source{}, err
		}
		src.ReconcileSeconds = reconcile
		src.ReconcileSchedule = reconcileSchedule
	case req.ReconcileSeconds > 0:
		src.ReconcileSeconds = req.ReconcileSeconds
		src.ReconcileSchedule = ""
	}
	src.Status = string(model.SourceStatusEnabled)
	src.WatchEnabled = true
	src.WatchUpdatedAt = &now
	src.UpdatedAt = now

	if err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Save(&src).Error; err != nil {
			return err
		}
		return enqueueSourceCommand(tx, src.AgentID, model.CommandStartSource, model.SourcePayload{
			SourceID:          src.ID,
			TenantID:          src.TenantID,
			RootPath:          src.RootPath,
			SkipInitialScan:   true,
			ReconcileSeconds:  src.ReconcileSeconds,
			ReconcileSchedule: src.ReconcileSchedule,
		})
	}); err != nil {
		return model.Source{}, err
	}
	return toModelSource(src), nil
}

func (s *Store) DisableSourceWatch(ctx context.Context, sourceID string) (model.Source, bool, error) {
	var src sourceEntity
	if err := s.db.WithContext(ctx).First(&src, "id = ?", strings.TrimSpace(sourceID)).Error; err != nil {
		return model.Source{}, false, err
	}
	now := time.Now().UTC()
	src.Status = string(model.SourceStatusDisabled)
	src.WatchEnabled = false
	src.WatchUpdatedAt = &now
	src.UpdatedAt = now

	if err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Save(&src).Error; err != nil {
			return err
		}
		if err := enqueueSourceCommand(tx, src.AgentID, model.CommandSnapshotSource, model.SourcePayload{
			SourceID: src.ID,
			TenantID: src.TenantID,
			RootPath: src.RootPath,
			Reason:   "WATCH_STOP_BASELINE",
		}); err != nil {
			return err
		}
		return enqueueSourceCommand(tx, src.AgentID, model.CommandStopSource, model.SourcePayload{
			SourceID: src.ID,
			TenantID: src.TenantID,
			RootPath: src.RootPath,
		})
	}); err != nil {
		return model.Source{}, false, err
	}
	return toModelSource(src), true, nil
}

func (s *Store) ExpediteTasksByPaths(ctx context.Context, sourceID string, req model.ExpediteTasksRequest) (model.ExpediteTasksResponse, error) {
	var resp model.ExpediteTasksResponse
	var src sourceEntity
	if err := s.db.WithContext(ctx).First(&src, "id = ?", strings.TrimSpace(sourceID)).Error; err != nil {
		return resp, err
	}
	paths, invalid := normalizePathsUnderRoot(req.Paths, src.RootPath)
	resp.SkippedCount += invalid
	if len(paths) == 0 {
		return resp, nil
	}
	now := time.Now().UTC()
	if err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		for _, p := range paths {
			var doc documentEntity
			err := tx.Where("tenant_id = ? AND source_id = ? AND source_object_id = ?", src.TenantID, src.ID, p).Take(&doc).Error
			if err != nil {
				if errors.Is(err, gorm.ErrRecordNotFound) {
					resp.SkippedCount++
					continue
				}
				return err
			}
			taskAction := inferTaskActionForDocument(doc)
			if taskAction != taskActionDelete && strings.TrimSpace(doc.DesiredVersionID) == "" {
				resp.SkippedCount++
				continue
			}
			if taskAction == taskActionDelete && strings.TrimSpace(doc.CoreDocumentID) == "" {
				resp.SkippedCount++
				continue
			}
			targetVersion := strings.TrimSpace(doc.DesiredVersionID)
			if targetVersion == "" {
				targetVersion = fmt.Sprintf("v_%d", now.UTC().UnixNano())
			}
			idempotencyKey := parseTaskIdempotencyKey(doc.ID, targetVersion, taskAction)

			updateRes := tx.Model(&parseTaskEntity{}).
				Where("document_id = ? AND status IN ?", doc.ID, []string{"PENDING", "RETRY_WAITING"}).
				Updates(map[string]any{
					"task_action":               taskAction,
					"status":                    "PENDING",
					"scan_orchestration_status": "PENDING",
					"next_run_at":               now,
					"retry_count":               0,
					"target_version_id":         targetVersion,
					"idempotency_key":           idempotencyKey,
					"core_document_id":          strings.TrimSpace(doc.CoreDocumentID),
					"lease_owner":               "",
					"lease_until":               nil,
					"updated_at":                now,
				})
			if updateRes.Error != nil {
				return updateRes.Error
			}
			if updateRes.RowsAffected > 0 {
				resp.UpdatedExistingTaskCount++
				docUpdates := map[string]any{
					"next_parse_at": nil,
					"updated_at":    now,
				}
				if taskAction == taskActionDelete {
					docUpdates["parse_status"] = "DELETED"
				} else {
					docUpdates["parse_status"] = "QUEUED"
				}
				if err := tx.Model(&documentEntity{}).Where("id = ?", doc.ID).Updates(docUpdates).Error; err != nil {
					return err
				}
				continue
			}
			task := parseTaskEntity{
				TenantID:                doc.TenantID,
				DocumentID:              doc.ID,
				TaskAction:              taskAction,
				TargetVersionID:         targetVersion,
				IdempotencyKey:          idempotencyKey,
				OriginType:              firstNonEmpty(doc.OriginType, string(model.OriginTypeLocalFS)),
				OriginPlatform:          firstNonEmpty(doc.OriginPlatform, "LOCAL"),
				TriggerPolicy:           firstNonEmpty(doc.TriggerPolicy, string(model.TriggerPolicyIdleWindow)),
				CoreDocumentID:          strings.TrimSpace(doc.CoreDocumentID),
				Status:                  "PENDING",
				ScanOrchestrationStatus: "PENDING",
				NextRunAt:               now,
				RetryCount:              0,
				MaxRetryCount:           8,
				CreatedAt:               now,
				UpdatedAt:               now,
			}
			if err := tx.Create(&task).Error; err != nil {
				if !isUniqueConstraintError(err) {
					return err
				}
				retryRes := tx.Model(&parseTaskEntity{}).
					Where("document_id = ? AND status IN ?", doc.ID, []string{"PENDING", "RETRY_WAITING"}).
					Updates(map[string]any{
						"task_action":               taskAction,
						"status":                    "PENDING",
						"scan_orchestration_status": "PENDING",
						"next_run_at":               now,
						"retry_count":               0,
						"target_version_id":         targetVersion,
						"idempotency_key":           idempotencyKey,
						"core_document_id":          strings.TrimSpace(doc.CoreDocumentID),
						"lease_owner":               "",
						"lease_until":               nil,
						"updated_at":                now,
					})
				if retryRes.Error != nil {
					return retryRes.Error
				}
				if retryRes.RowsAffected == 0 {
					resp.SkippedCount++
					continue
				}
				resp.UpdatedExistingTaskCount++
			} else {
				resp.CreatedTaskCount++
			}
			docUpdates := map[string]any{
				"next_parse_at": nil,
				"updated_at":    now,
			}
			if taskAction == taskActionDelete {
				docUpdates["parse_status"] = "DELETED"
			} else {
				docUpdates["parse_status"] = "QUEUED"
			}
			if err := tx.Model(&documentEntity{}).Where("id = ?", doc.ID).Updates(docUpdates).Error; err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		return resp, err
	}
	return resp, nil
}

func (s *Store) RequeueEnabledSourcesOnStartup(ctx context.Context) (int, error) {
	var enabled []sourceEntity
	if err := s.db.WithContext(ctx).Where("status = ? AND watch_enabled = ?", string(model.SourceStatusEnabled), true).Find(&enabled).Error; err != nil {
		return 0, err
	}
	queued := 0
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		for _, src := range enabled {
			if err := enqueueSourceCommand(tx, src.AgentID, model.CommandStartSource, model.SourcePayload{
				SourceID:          src.ID,
				TenantID:          src.TenantID,
				RootPath:          src.RootPath,
				SkipInitialScan:   true,
				ReconcileSeconds:  src.ReconcileSeconds,
				ReconcileSchedule: src.ReconcileSchedule,
			}); err != nil {
				return err
			}
			queued++
		}
		return nil
	})
	return queued, err
}

func enqueueSourceCommand(tx *gorm.DB, agentID string, typ model.CommandType, payload model.SourcePayload) error {
	raw, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	now := time.Now().UTC()
	nextRetry := now
	cmd := agentCommandEntity{
		AgentID:      agentID,
		Type:         string(typ),
		Payload:      string(raw),
		Status:       commandStatusPending,
		NextRetryAt:  &nextRetry,
		AttemptCount: 0,
		CreatedAt:    now,
	}
	return tx.Create(&cmd).Error
}

func enqueueScanCommand(tx *gorm.DB, agentID string, payload model.SourcePayload, mode string) error {
	raw, err := json.Marshal(map[string]any{
		"source_id": payload.SourceID,
		"tenant_id": payload.TenantID,
		"root_path": payload.RootPath,
		"mode":      mode,
	})
	if err != nil {
		return err
	}
	now := time.Now().UTC()
	nextRetry := now
	cmd := agentCommandEntity{
		AgentID:      agentID,
		Type:         string(model.CommandScanSource),
		Payload:      string(raw),
		Status:       commandStatusPending,
		AttemptCount: 0,
		NextRetryAt:  &nextRetry,
		CreatedAt:    now,
	}
	return tx.Create(&cmd).Error
}

func (s *Store) RegisterAgent(ctx context.Context, req model.RegisterAgentRequest) error {
	if req.AgentID == "" || req.TenantID == "" {
		return fmt.Errorf("agent_id and tenant_id are required")
	}
	listenAddr := req.ListenAddr
	if listenAddr == "" {
		listenAddr = "http://127.0.0.1:19090"
	}
	now := time.Now().UTC()
	agent := agentEntity{
		AgentID:           req.AgentID,
		TenantID:          req.TenantID,
		Hostname:          req.Hostname,
		Version:           req.Version,
		Status:            "ONLINE",
		ListenAddr:        listenAddr,
		LastHeartbeatAt:   now,
		ActiveSourceCount: 0,
		ActiveWatchCount:  0,
		ActiveTaskCount:   0,
		UpdatedAt:         now,
	}
	return s.db.WithContext(ctx).Clauses(clause.OnConflict{
		Columns: []clause.Column{{Name: "agent_id"}},
		DoUpdates: clause.Assignments(map[string]any{
			"tenant_id":           agent.TenantID,
			"hostname":            agent.Hostname,
			"version":             agent.Version,
			"status":              "ONLINE",
			"listen_addr":         agent.ListenAddr,
			"last_heartbeat_at":   agent.LastHeartbeatAt,
			"active_source_count": 0,
			"active_watch_count":  0,
			"active_task_count":   0,
			"updated_at":          agent.UpdatedAt,
		}),
	}).Create(&agent).Error
}

func (s *Store) UpdateHeartbeat(ctx context.Context, hb model.HeartbeatPayload) error {
	if hb.AgentID == "" || hb.TenantID == "" {
		return fmt.Errorf("agent_id and tenant_id are required")
	}
	now := time.Now().UTC()
	last := hb.LastHeartbeatAt.UTC()
	if last.IsZero() {
		last = now
	}

	var existing agentEntity
	err := s.db.WithContext(ctx).First(&existing, "agent_id = ?", hb.AgentID).Error
	if err != nil && err != gorm.ErrRecordNotFound {
		return err
	}

	listenAddr := hb.ListenAddr
	if listenAddr == "" {
		if err == nil && existing.ListenAddr != "" {
			listenAddr = existing.ListenAddr
		} else {
			listenAddr = "http://127.0.0.1:19090"
		}
	}

	status := strings.TrimSpace(hb.Status)
	if status == "" {
		status = "ONLINE"
	}

	agent := agentEntity{
		AgentID:           hb.AgentID,
		TenantID:          hb.TenantID,
		Hostname:          hb.Hostname,
		Version:           hb.Version,
		Status:            status,
		ListenAddr:        listenAddr,
		LastHeartbeatAt:   last,
		ActiveSourceCount: hb.SourceCount,
		ActiveWatchCount:  hb.ActiveWatchCount,
		ActiveTaskCount:   hb.ActiveTaskCount,
		UpdatedAt:         now,
	}
	wasOffline := err == nil && strings.EqualFold(existing.Status, "OFFLINE")
	return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Clauses(clause.OnConflict{
			Columns: []clause.Column{{Name: "agent_id"}},
			DoUpdates: clause.Assignments(map[string]any{
				"tenant_id":           agent.TenantID,
				"hostname":            agent.Hostname,
				"version":             agent.Version,
				"status":              agent.Status,
				"listen_addr":         agent.ListenAddr,
				"last_heartbeat_at":   agent.LastHeartbeatAt,
				"active_source_count": agent.ActiveSourceCount,
				"active_watch_count":  agent.ActiveWatchCount,
				"active_task_count":   agent.ActiveTaskCount,
				"updated_at":          agent.UpdatedAt,
			}),
		}).Create(&agent).Error; err != nil {
			return err
		}

		if wasOffline && strings.EqualFold(status, "ONLINE") {
			var sources []sourceEntity
			if err := tx.Where("agent_id = ? AND status IN ? AND watch_enabled = ?", hb.AgentID, []string{string(model.SourceStatusEnabled), string(model.SourceStatusDegraded)}, true).Find(&sources).Error; err != nil {
				return err
			}
			for _, src := range sources {
				if err := tx.Model(&sourceEntity{}).Where("id = ?", src.ID).Updates(map[string]any{
					"status":     string(model.SourceStatusEnabled),
					"updated_at": now,
				}).Error; err != nil {
					return err
				}
				payload := model.SourcePayload{SourceID: src.ID, TenantID: src.TenantID, RootPath: src.RootPath}
				payload.SkipInitialScan = true
				payload.ReconcileSeconds = src.ReconcileSeconds
				if err := enqueueSourceCommand(tx, src.AgentID, model.CommandStartSource, payload); err != nil {
					return err
				}
				if err := enqueueScanCommand(tx, src.AgentID, payload, "reconcile"); err != nil {
					return err
				}
			}
		}
		return nil
	})
}

func (s *Store) PullPendingCommands(ctx context.Context, req model.PullCommandsRequest) (model.PullCommandsResponse, error) {
	var resp model.PullCommandsResponse
	if req.AgentID == "" {
		return resp, fmt.Errorf("agent_id is required")
	}
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var entities []agentCommandEntity
		now := time.Now().UTC()
		if err := tx.Where("agent_id = ? AND status = ? AND (next_retry_at IS NULL OR next_retry_at <= ?)", req.AgentID, commandStatusPending, now).
			Order("id ASC").
			Limit(100).
			Find(&entities).Error; err != nil {
			return err
		}
		if len(entities) == 0 {
			return nil
		}

		ids := make([]int64, 0, len(entities))
		for _, item := range entities {
			ids = append(ids, item.ID)
			pulled := model.PulledCommand{ID: item.ID, Type: model.CommandType(item.Type)}
			switch model.CommandType(item.Type) {
			case model.CommandStageFile:
				var payload StageCommandPayload
				if err := json.Unmarshal([]byte(item.Payload), &payload); err != nil {
					s.log.Warn("decode stage command payload failed", zap.Int64("id", item.ID), zap.Error(err))
					continue
				}
				pulled.SourceID = payload.SourceID
				pulled.DocumentID = payload.DocumentID
				pulled.VersionID = payload.VersionID
				pulled.SrcPath = payload.SrcPath
			case model.CommandScanSource:
				var payload struct {
					SourceID string `json:"source_id"`
					TenantID string `json:"tenant_id"`
					RootPath string `json:"root_path"`
					Mode     string `json:"mode"`
				}
				if err := json.Unmarshal([]byte(item.Payload), &payload); err != nil {
					s.log.Warn("decode scan command payload failed", zap.Int64("id", item.ID), zap.Error(err))
					continue
				}
				pulled.SourceID = payload.SourceID
				pulled.TenantID = payload.TenantID
				pulled.RootPath = payload.RootPath
				pulled.Mode = payload.Mode
			default:
				var payload model.SourcePayload
				if err := json.Unmarshal([]byte(item.Payload), &payload); err != nil {
					s.log.Warn("decode source command payload failed", zap.Int64("id", item.ID), zap.Error(err))
					continue
				}
				pulled.SourceID = payload.SourceID
				pulled.TenantID = payload.TenantID
				pulled.RootPath = payload.RootPath
				pulled.Reason = payload.Reason
				pulled.SkipInitialScan = payload.SkipInitialScan
				pulled.ReconcileSeconds = payload.ReconcileSeconds
				pulled.ReconcileSchedule = payload.ReconcileSchedule
			}
			resp.Commands = append(resp.Commands, pulled)
		}
		if len(resp.Commands) > 0 {
			s.log.Info("dispatching commands to agent",
				zap.String("agent_id", req.AgentID),
				zap.Int("count", len(resp.Commands)),
			)
		}

		return tx.Model(&agentCommandEntity{}).
			Where("id IN ?", ids).
			Updates(map[string]any{
				"status":        commandStatusDispatched,
				"dispatched_at": &now,
				"attempt_count": gorm.Expr("attempt_count + 1"),
			}).Error
	})
	return resp, err
}

func (s *Store) AckCommand(ctx context.Context, req model.AckCommandRequest) error {
	if req.AgentID == "" || req.CommandID <= 0 {
		return fmt.Errorf("agent_id and command_id are required")
	}
	now := time.Now().UTC()
	updates := map[string]any{
		"acked_at":    &now,
		"last_error":  strings.TrimSpace(req.Error),
		"result_json": strings.TrimSpace(req.ResultJSON),
	}
	if req.Success {
		updates["status"] = commandStatusAcked
	} else {
		updates["status"] = commandStatusFailed
	}

	if err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var cmd agentCommandEntity
		if err := tx.Take(&cmd, "id = ? AND agent_id = ? AND status = ?", req.CommandID, req.AgentID, commandStatusDispatched).Error; err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				return fmt.Errorf("command not found or not dispatchable")
			}
			return err
		}
		if err := tx.Model(&agentCommandEntity{}).
			Where("id = ?", cmd.ID).
			Updates(updates).Error; err != nil {
			return err
		}
		if !req.Success || model.CommandType(cmd.Type) != model.CommandSnapshotSource {
			return nil
		}

		var payload model.SourcePayload
		if err := json.Unmarshal([]byte(cmd.Payload), &payload); err != nil {
			s.log.Warn("decode snapshot_source payload failed", zap.Int64("command_id", cmd.ID), zap.Error(err))
			return nil
		}
		var snapshotResult struct {
			SnapshotRef string    `json:"snapshot_ref"`
			FileCount   int64     `json:"file_count"`
			TakenAt     time.Time `json:"taken_at"`
		}
		raw := strings.TrimSpace(req.ResultJSON)
		if raw != "" {
			if err := json.Unmarshal([]byte(raw), &snapshotResult); err != nil {
				s.log.Warn("decode snapshot_source result failed", zap.Int64("command_id", cmd.ID), zap.Error(err))
			}
		}
		takenAt := snapshotResult.TakenAt.UTC()
		if takenAt.IsZero() {
			takenAt = now
		}
		snapshotRef := strings.TrimSpace(snapshotResult.SnapshotRef)
		if snapshotRef == "" {
			snapshotRef = "local://unknown"
		}
		reason := strings.TrimSpace(payload.Reason)
		if reason == "" {
			reason = "UNKNOWN"
		}
		baseline := sourceBaselineSnapshotEntity{
			SourceID:    strings.TrimSpace(payload.SourceID),
			SnapshotRef: snapshotRef,
			FileCount:   snapshotResult.FileCount,
			TakenAt:     takenAt,
			Reason:      reason,
			UpdatedAt:   now,
		}
		if baseline.SourceID == "" {
			return nil
		}
		if err := tx.Clauses(clause.OnConflict{
			Columns: []clause.Column{{Name: "source_id"}},
			DoUpdates: clause.Assignments(map[string]any{
				"snapshot_ref": baseline.SnapshotRef,
				"file_count":   baseline.FileCount,
				"taken_at":     baseline.TakenAt,
				"reason":       baseline.Reason,
				"updated_at":   baseline.UpdatedAt,
			}),
		}).Create(&baseline).Error; err != nil {
			return err
		}
		return s.syncCommittedSnapshotMetadataTx(
			tx,
			strings.TrimSpace(payload.SourceID),
			strings.TrimSpace(payload.TenantID),
			snapshotRef,
			snapshotResult.FileCount,
			takenAt,
			now,
		)
	}); err != nil {
		return err
	}
	s.log.Info("command ack persisted",
		zap.String("agent_id", req.AgentID),
		zap.Int64("command_id", req.CommandID),
		zap.Bool("success", req.Success),
		zap.String("error", strings.TrimSpace(req.Error)),
	)
	return nil
}

func (s *Store) EnqueueStageCommand(ctx context.Context, agentID string, payload StageCommandPayload) (int64, error) {
	if strings.TrimSpace(agentID) == "" {
		return 0, fmt.Errorf("agent_id is required")
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return 0, err
	}
	now := time.Now().UTC()
	nextRetry := now
	cmd := agentCommandEntity{
		AgentID:      strings.TrimSpace(agentID),
		Type:         string(model.CommandStageFile),
		Payload:      string(raw),
		Status:       commandStatusPending,
		AttemptCount: 0,
		NextRetryAt:  &nextRetry,
		CreatedAt:    now,
	}
	if err := s.db.WithContext(ctx).Create(&cmd).Error; err != nil {
		return 0, err
	}
	return cmd.ID, nil
}

func (s *Store) AwaitCommandResult(ctx context.Context, commandID int64, pollInterval time.Duration) (string, error) {
	if commandID <= 0 {
		return "", fmt.Errorf("command_id must be > 0")
	}
	if pollInterval <= 0 {
		pollInterval = 500 * time.Millisecond
	}
	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()
	for {
		var cmd agentCommandEntity
		if err := s.db.WithContext(ctx).Take(&cmd, "id = ?", commandID).Error; err != nil {
			return "", err
		}
		switch cmd.Status {
		case commandStatusAcked:
			return cmd.ResultJSON, nil
		case commandStatusFailed:
			if strings.TrimSpace(cmd.LastError) != "" {
				return "", fmt.Errorf(cmd.LastError)
			}
			return "", fmt.Errorf("command %d failed", commandID)
		}

		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-ticker.C:
		}
	}
}

func (s *Store) RequeueTimedOutCommands(ctx context.Context, now time.Time, ackTimeout time.Duration, maxAttempts int) (int64, error) {
	if ackTimeout <= 0 {
		return 0, nil
	}
	timeoutAt := now.UTC().Add(-ackTimeout)
	nextRetry := now.UTC().Add(3 * time.Second)
	res := s.db.WithContext(ctx).
		Model(&agentCommandEntity{}).
		Where("status = ? AND dispatched_at IS NOT NULL AND dispatched_at <= ? AND attempt_count < ?", commandStatusDispatched, timeoutAt, maxAttempts).
		Updates(map[string]any{
			"status":        commandStatusPending,
			"next_retry_at": &nextRetry,
			"last_error":    "ack timeout",
		})
	if res.Error == nil && res.RowsAffected > 0 {
		s.log.Warn("requeued timed-out commands", zap.Int64("count", res.RowsAffected))
	}
	return res.RowsAffected, res.Error
}

func (s *Store) FailExhaustedCommands(ctx context.Context, maxAttempts int) (int64, error) {
	res := s.db.WithContext(ctx).
		Model(&agentCommandEntity{}).
		Where("status IN (?, ?) AND attempt_count >= ?", commandStatusPending, commandStatusDispatched, maxAttempts).
		Updates(map[string]any{
			"status":     commandStatusFailed,
			"last_error": "max attempts reached",
		})
	if res.Error == nil && res.RowsAffected > 0 {
		s.log.Warn("marked commands failed after max attempts", zap.Int64("count", res.RowsAffected))
	}
	return res.RowsAffected, res.Error
}

func (s *Store) IngestEvents(ctx context.Context, req model.ReportEventsRequest) error {
	mutations, err := s.BuildMutationsFromEvents(ctx, req.Events)
	if err != nil {
		return err
	}
	return s.BatchApplyDocumentMutations(ctx, mutations)
}

func (s *Store) IngestScanResults(ctx context.Context, req model.ReportScanResultsRequest) error {
	events := make([]model.FileEvent, 0, len(req.Records))
	for _, rec := range req.Records {
		events = append(events, model.FileEvent{
			SourceID:       rec.SourceID,
			EventType:      "modified",
			Path:           rec.Path,
			IsDir:          rec.IsDir,
			OccurredAt:     rec.ModTime,
			OriginType:     rec.OriginType,
			OriginPlatform: rec.OriginPlatform,
			OriginRef:      rec.OriginRef,
			TriggerPolicy:  rec.TriggerPolicy,
		})
	}
	mutations, err := s.BuildMutationsFromEvents(ctx, events)
	if err != nil {
		return err
	}
	return s.BatchApplyDocumentMutations(ctx, mutations)
}

func (s *Store) BuildMutationsFromEvents(ctx context.Context, events []model.FileEvent) ([]DocumentMutation, error) {
	mutations := make([]DocumentMutation, 0, len(events))
	sourceCache := make(map[string]sourceEntity)
	var (
		skippedIsDir          int
		skippedEmptyPath      int
		skippedMissingSource  int
		skippedSourceNotFound int
	)
	for _, ev := range events {
		if ev.IsDir {
			skippedIsDir++
			s.log.Debug("event skipped",
				zap.String("reason", "is_dir"),
				zap.String("source_id", strings.TrimSpace(ev.SourceID)),
				zap.String("path", strings.TrimSpace(ev.Path)),
				zap.String("event_type", normalizeEventType(ev.EventType)),
			)
			continue
		}
		path := strings.TrimSpace(ev.Path)
		if path == "" {
			skippedEmptyPath++
			s.log.Debug("event skipped",
				zap.String("reason", "empty_path"),
				zap.String("source_id", strings.TrimSpace(ev.SourceID)),
				zap.String("event_type", normalizeEventType(ev.EventType)),
			)
			continue
		}
		srcID := strings.TrimSpace(ev.SourceID)
		if srcID == "" {
			skippedMissingSource++
			s.log.Debug("event skipped",
				zap.String("reason", "missing_source_id"),
				zap.String("path", path),
				zap.String("event_type", normalizeEventType(ev.EventType)),
			)
			continue
		}

		src, ok := sourceCache[srcID]
		if !ok {
			var row sourceEntity
			if err := s.db.WithContext(ctx).First(&row, "id = ?", srcID).Error; err != nil {
				if errors.Is(err, gorm.ErrRecordNotFound) {
					skippedSourceNotFound++
					s.log.Debug("event skipped",
						zap.String("reason", "source_not_found"),
						zap.String("source_id", srcID),
						zap.String("path", path),
						zap.String("event_type", normalizeEventType(ev.EventType)),
					)
					continue
				}
				return nil, err
			}
			sourceCache[srcID] = row
			src = row
		}

		occurred := ev.OccurredAt.UTC()
		if occurred.IsZero() {
			occurred = time.Now().UTC()
		}

		idleSeconds := src.IdleWindowSeconds
		if idleSeconds <= 0 {
			idleSeconds = int64(s.defaultIdleWindow.Seconds())
		}

		mutations = append(mutations, DocumentMutation{
			TenantID:          src.TenantID,
			SourceID:          src.ID,
			SourceObjectID:    path,
			IdleWindowSeconds: idleSeconds,
			EventType:         normalizeEventType(ev.EventType),
			OccurredAt:        occurred,
			OriginType:        firstNonEmpty(strings.TrimSpace(ev.OriginType), src.DefaultOriginType, string(model.OriginTypeLocalFS)),
			OriginPlatform:    firstNonEmpty(strings.TrimSpace(ev.OriginPlatform), src.DefaultOriginPlatform, "LOCAL"),
			OriginRef:         strings.TrimSpace(ev.OriginRef),
			TriggerPolicy:     firstNonEmpty(strings.TrimSpace(ev.TriggerPolicy), src.DefaultTriggerPolicy, string(model.TriggerPolicyIdleWindow)),
		})
	}
	if len(events) > 0 {
		s.log.Debug("built document mutations from events",
			zap.Int("events", len(events)),
			zap.Int("mutations", len(mutations)),
			zap.Int("skipped_is_dir", skippedIsDir),
			zap.Int("skipped_empty_path", skippedEmptyPath),
			zap.Int("skipped_missing_source", skippedMissingSource),
			zap.Int("skipped_source_not_found", skippedSourceNotFound),
		)
	}
	return mutations, nil
}

func (s *Store) BatchApplyDocumentMutations(ctx context.Context, mutations []DocumentMutation) error {
	if len(mutations) == 0 {
		return nil
	}
	return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		for _, m := range mutations {
			if err := applyDocumentMutation(tx, m, s.log); err != nil {
				return err
			}
		}
		return nil
	})
}

func applyDocumentMutation(tx *gorm.DB, m DocumentMutation, log *zap.Logger) error {
	now := time.Now().UTC()
	occurred := m.OccurredAt.UTC()
	if occurred.IsZero() {
		occurred = now
	}
	policy := firstNonEmpty(strings.TrimSpace(m.TriggerPolicy), string(model.TriggerPolicyIdleWindow))
	var nextParse *time.Time
	if normalizeEventType(m.EventType) != "deleted" {
		when := occurred
		if policy == string(model.TriggerPolicyIdleWindow) {
			idle := m.IdleWindowSeconds
			if idle <= 0 {
				idle = 1
			}
			when = occurred.Add(time.Duration(idle) * time.Second)
		}
		nextParse = &when
	}

	var doc documentEntity
	err := tx.Where("tenant_id = ? AND source_id = ? AND source_object_id = ?", m.TenantID, m.SourceID, m.SourceObjectID).Take(&doc).Error
	if err != nil && err != gorm.ErrRecordNotFound {
		return err
	}

	existingLast := time.Time{}
	if err == nil && doc.LastModifiedAt != nil {
		existingLast = doc.LastModifiedAt.UTC()
	}
	// 对同一文件，仅接受“更新的”事件时间。
	// 这样可以避免 full-scan/restart 时用相同 mtime 重复触发任务。
	if !existingLast.IsZero() && !occurred.After(existingLast) {
		if log != nil {
			log.Debug("event skipped",
				zap.String("reason", "old_timestamp"),
				zap.Int64("document_id", doc.ID),
				zap.String("source_id", m.SourceID),
				zap.String("source_object_id", m.SourceObjectID),
				zap.Time("event_occurred_at", occurred),
				zap.Time("last_modified_at", existingLast),
			)
		}
		return nil
	}

	if normalizeEventType(m.EventType) == "deleted" {
		desiredVersion := fmt.Sprintf("d_%d", occurred.UnixNano())
		nextDeleteAt := occurred
		updates := map[string]any{
			"desired_version_id": desiredVersion,
			"last_modified_at":   occurred,
			"next_parse_at":      &nextDeleteAt,
			"parse_status":       "DELETED",
			"origin_type":        firstNonEmpty(m.OriginType, string(model.OriginTypeLocalFS)),
			"origin_platform":    firstNonEmpty(m.OriginPlatform, "LOCAL"),
			"origin_ref":         m.OriginRef,
			"trigger_policy":     policy,
			"updated_at":         now,
		}
		if err == gorm.ErrRecordNotFound {
			doc = documentEntity{
				TenantID:         m.TenantID,
				SourceID:         m.SourceID,
				SourceObjectID:   m.SourceObjectID,
				DesiredVersionID: desiredVersion,
				LastModifiedAt:   &occurred,
				NextParseAt:      &nextDeleteAt,
				ParseStatus:      "DELETED",
				OriginType:       firstNonEmpty(m.OriginType, string(model.OriginTypeLocalFS)),
				OriginPlatform:   firstNonEmpty(m.OriginPlatform, "LOCAL"),
				OriginRef:        m.OriginRef,
				TriggerPolicy:    policy,
				UpdatedAt:        now,
			}
			return tx.Create(&doc).Error
		}
		return tx.Model(&documentEntity{}).Where("id = ?", doc.ID).Updates(updates).Error
	}

	desiredVersion := fmt.Sprintf("v_%d", occurred.UnixNano())
	updates := map[string]any{
		"desired_version_id": desiredVersion,
		"last_modified_at":   occurred,
		"next_parse_at":      nextParse,
		"parse_status":       "PENDING",
		"origin_type":        firstNonEmpty(m.OriginType, string(model.OriginTypeLocalFS)),
		"origin_platform":    firstNonEmpty(m.OriginPlatform, "LOCAL"),
		"origin_ref":         m.OriginRef,
		"trigger_policy":     policy,
		"updated_at":         now,
	}
	if err == nil && strings.EqualFold(strings.TrimSpace(doc.ParseStatus), "DELETED") {
		// Deleted -> recreated at same path: treat as a brand new document in core.
		updates["core_document_id"] = ""
		updates["current_version_id"] = ""
	}
	if err == gorm.ErrRecordNotFound {
		doc = documentEntity{
			TenantID:         m.TenantID,
			SourceID:         m.SourceID,
			SourceObjectID:   m.SourceObjectID,
			DesiredVersionID: desiredVersion,
			LastModifiedAt:   &occurred,
			NextParseAt:      nextParse,
			ParseStatus:      "PENDING",
			OriginType:       firstNonEmpty(m.OriginType, string(model.OriginTypeLocalFS)),
			OriginPlatform:   firstNonEmpty(m.OriginPlatform, "LOCAL"),
			OriginRef:        m.OriginRef,
			TriggerPolicy:    policy,
			UpdatedAt:        now,
		}
		return tx.Create(&doc).Error
	}
	return tx.Model(&documentEntity{}).Where("id = ?", doc.ID).Updates(updates).Error
}

func (s *Store) ScheduleDueParses(ctx context.Context, now time.Time) (int, error) {
	var docs []documentEntity
	if err := s.db.WithContext(ctx).
		Where("next_parse_at IS NOT NULL AND next_parse_at <= ?", now.UTC()).
		Find(&docs).Error; err != nil {
		return 0, err
	}

	created := 0
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		for _, doc := range docs {
			taskAction := inferTaskActionForDocument(doc)
			if taskAction != taskActionDelete && strings.TrimSpace(doc.DesiredVersionID) == "" {
				continue
			}
			if taskAction == taskActionDelete && strings.TrimSpace(doc.CoreDocumentID) == "" {
				if err := tx.Model(&documentEntity{}).Where("id = ?", doc.ID).Updates(map[string]any{
					"next_parse_at": nil,
					"updated_at":    now.UTC(),
				}).Error; err != nil {
					return err
				}
				continue
			}

			targetVersion := strings.TrimSpace(doc.DesiredVersionID)
			if targetVersion == "" {
				targetVersion = fmt.Sprintf("v_%d", now.UTC().UnixNano())
			}
			originType := firstNonEmpty(doc.OriginType, string(model.OriginTypeLocalFS))
			originPlatform := firstNonEmpty(doc.OriginPlatform, "LOCAL")
			triggerPolicy := firstNonEmpty(doc.TriggerPolicy, string(model.TriggerPolicyIdleWindow))
			var pendingTask parseTaskEntity
			pendingErr := tx.
				Where("document_id = ? AND status IN ?", doc.ID, []string{"PENDING", "RETRY_WAITING"}).
				Order("id ASC").
				Take(&pendingTask).Error
			if pendingErr != nil && pendingErr != gorm.ErrRecordNotFound {
				return pendingErr
			}
			hadPending := pendingErr == nil
			oldVersion := ""
			pendingTaskID := int64(0)
			if hadPending {
				oldVersion = pendingTask.TargetVersionID
				pendingTaskID = pendingTask.ID
			}
			taskUpdates := map[string]any{
				"task_action":               taskAction,
				"target_version_id":         targetVersion,
				"idempotency_key":           parseTaskIdempotencyKey(doc.ID, targetVersion, taskAction),
				"origin_type":               originType,
				"origin_platform":           originPlatform,
				"trigger_policy":            triggerPolicy,
				"core_document_id":          strings.TrimSpace(doc.CoreDocumentID),
				"status":                    "PENDING",
				"scan_orchestration_status": "PENDING",
				"next_run_at":               now.UTC(),
				"retry_count":               0,
				"max_retry_count":           8,
				"lease_owner":               "",
				"lease_until":               nil,
				"last_error":                "",
				"updated_at":                now.UTC(),
			}

			// 只合并“未执行任务”；已执行任务保留为历史记录。
			updateRes := tx.Model(&parseTaskEntity{}).
				Where("document_id = ? AND status IN ?", doc.ID, []string{"PENDING", "RETRY_WAITING"}).
				Updates(taskUpdates)
			if updateRes.Error != nil {
				return updateRes.Error
			}
			if updateRes.RowsAffected > 0 {
				s.log.Info("schedule due parse merged into pending task",
					zap.Int64("document_id", doc.ID),
					zap.Int64("task_id", pendingTaskID),
					zap.String("task_action", taskAction),
					zap.String("old_version", oldVersion),
					zap.String("new_version", targetVersion),
				)
			}

			if updateRes.RowsAffected == 0 {
				task := parseTaskEntity{
					TenantID:                doc.TenantID,
					DocumentID:              doc.ID,
					TaskAction:              taskAction,
					TargetVersionID:         targetVersion,
					IdempotencyKey:          parseTaskIdempotencyKey(doc.ID, targetVersion, taskAction),
					OriginType:              originType,
					OriginPlatform:          originPlatform,
					TriggerPolicy:           triggerPolicy,
					CoreDocumentID:          strings.TrimSpace(doc.CoreDocumentID),
					Status:                  "PENDING",
					ScanOrchestrationStatus: "PENDING",
					NextRunAt:               now.UTC(),
					RetryCount:              0,
					MaxRetryCount:           8,
					CreatedAt:               now.UTC(),
					UpdatedAt:               now.UTC(),
				}
				if err := tx.Create(&task).Error; err != nil {
					// 并发场景下可能被唯一索引拦住，回退到 update 即可。
					if isUniqueConstraintError(err) {
						if lookupErr := tx.
							Where("document_id = ? AND status IN ?", doc.ID, []string{"PENDING", "RETRY_WAITING"}).
							Order("id ASC").
							Take(&pendingTask).Error; lookupErr == nil {
							pendingTaskID = pendingTask.ID
							oldVersion = pendingTask.TargetVersionID
						}
						retryRes := tx.Model(&parseTaskEntity{}).
							Where("document_id = ? AND status IN ?", doc.ID, []string{"PENDING", "RETRY_WAITING"}).
							Updates(taskUpdates)
						if retryRes.Error != nil {
							return retryRes.Error
						}
						if retryRes.RowsAffected == 0 {
							return err
						}
						s.log.Info("schedule due parse merged into pending task",
							zap.Int64("document_id", doc.ID),
							zap.Int64("task_id", pendingTaskID),
							zap.String("task_action", taskAction),
							zap.String("old_version", oldVersion),
							zap.String("new_version", targetVersion),
						)
					} else {
						return err
					}
				} else {
					s.log.Info("schedule due parse created task",
						zap.Int64("document_id", doc.ID),
						zap.Int64("task_id", task.ID),
						zap.String("task_action", taskAction),
						zap.String("old_version", oldVersion),
						zap.String("new_version", targetVersion),
					)
					created++
				}
			}

			documentUpdates := map[string]any{
				"next_parse_at": nil,
				"updated_at":    now.UTC(),
			}
			if taskAction == taskActionDelete {
				documentUpdates["parse_status"] = "DELETED"
			} else {
				documentUpdates["parse_status"] = "QUEUED"
			}
			if err := tx.Model(&documentEntity{}).Where("id = ?", doc.ID).Updates(documentUpdates).Error; err != nil {
				return err
			}
		}
		return nil
	})
	return created, err
}

func (s *Store) ClaimDueTasks(ctx context.Context, leaseOwner string, now time.Time, limit int, leaseDuration time.Duration) ([]PendingTask, error) {
	if limit <= 0 {
		limit = 1
	}
	if leaseDuration <= 0 {
		leaseDuration = 30 * time.Second
	}
	leaseUntil := now.UTC().Add(leaseDuration)
	claimed := make([]parseTaskEntity, 0, limit)

	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var candidates []parseTaskEntity
		if err := tx.Where("status IN ? AND next_run_at <= ? AND (lease_until IS NULL OR lease_until <= ?)", []string{"PENDING", "RETRY_WAITING"}, now.UTC(), now.UTC()).
			Order("next_run_at ASC").
			Limit(limit).
			Find(&candidates).Error; err != nil {
			return err
		}
		for _, candidate := range candidates {
			started := now.UTC()
			idempotencyKey := strings.TrimSpace(candidate.IdempotencyKey)
			if idempotencyKey == "" {
				idempotencyKey = parseTaskIdempotencyKey(candidate.DocumentID, candidate.TargetVersionID, candidate.TaskAction)
			}
			res := tx.Model(&parseTaskEntity{}).
				Where("id = ? AND status IN ? AND (lease_until IS NULL OR lease_until <= ?)", candidate.ID, []string{"PENDING", "RETRY_WAITING"}, now.UTC()).
				Updates(map[string]any{
					"status":                    "RUNNING",
					"scan_orchestration_status": "RUNNING",
					"idempotency_key":           idempotencyKey,
					"lease_owner":               leaseOwner,
					"lease_until":               &leaseUntil,
					"started_at":                &started,
					"updated_at":                now.UTC(),
				})
			if res.Error != nil {
				return res.Error
			}
			if res.RowsAffected == 0 {
				continue
			}
			candidate.Status = "RUNNING"
			candidate.IdempotencyKey = idempotencyKey
			candidate.LeaseOwner = leaseOwner
			candidate.LeaseUntil = &leaseUntil
			candidate.StartedAt = &started
			claimed = append(claimed, candidate)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	if len(claimed) == 0 {
		return nil, nil
	}

	result := make([]PendingTask, 0, len(claimed))
	for _, task := range claimed {
		var row struct {
			DocumentID       int64
			SourceID         string
			SourceDatasetID  string
			CoreDocumentID   string
			SourceObjectID   string
			DesiredVersionID string
			AgentID          string
			ListenAddr       string
		}
		if err := s.db.WithContext(ctx).
			Table("documents d").
			Select("d.id as document_id, d.source_id, s.dataset_id as source_dataset_id, d.core_document_id, d.source_object_id, d.desired_version_id, s.agent_id, a.listen_addr").
			Joins("JOIN sources s ON s.id = d.source_id").
			Joins("LEFT JOIN agents a ON a.agent_id = s.agent_id").
			Where("d.id = ?", task.DocumentID).
			Take(&row).Error; err != nil {
			return nil, err
		}
		result = append(result, PendingTask{
			TaskID:           task.ID,
			TenantID:         task.TenantID,
			DocumentID:       task.DocumentID,
			TaskAction:       normalizeTaskAction(task.TaskAction),
			TargetVersionID:  task.TargetVersionID,
			IdempotencyKey:   strings.TrimSpace(task.IdempotencyKey),
			RetryCount:       task.RetryCount,
			MaxRetryCount:    max(1, task.MaxRetryCount),
			OriginType:       task.OriginType,
			OriginPlatform:   task.OriginPlatform,
			TriggerPolicy:    task.TriggerPolicy,
			SourceID:         row.SourceID,
			SourceDatasetID:  strings.TrimSpace(row.SourceDatasetID),
			CoreDocumentID:   firstNonEmpty(strings.TrimSpace(task.CoreDocumentID), strings.TrimSpace(row.CoreDocumentID)),
			SourceObjectID:   row.SourceObjectID,
			DesiredVersionID: row.DesiredVersionID,
			AgentID:          row.AgentID,
			AgentListenAddr:  row.ListenAddr,
		})
	}
	return result, nil
}

func (s *Store) MarkTaskSuperseded(ctx context.Context, taskID int64, reason string) error {
	now := time.Now().UTC()
	return s.db.WithContext(ctx).Model(&parseTaskEntity{}).Where("id = ?", taskID).Updates(map[string]any{
		"status":                    "SUPERSEDED",
		"scan_orchestration_status": "SUPERSEDED",
		"last_error":                reason,
		"finished_at":               &now,
		"lease_owner":               "",
		"lease_until":               nil,
		"updated_at":                now,
	}).Error
}

func (s *Store) MarkTaskStaging(ctx context.Context, taskID int64) error {
	now := time.Now().UTC()
	return s.db.WithContext(ctx).Model(&parseTaskEntity{}).Where("id = ?", taskID).Updates(map[string]any{
		"status":                    "STAGING",
		"scan_orchestration_status": "STAGING",
		"submit_error_message":      "",
		"updated_at":                now,
	}).Error
}

func (s *Store) MarkTaskSubmitted(ctx context.Context, taskID int64, coreDatasetID, coreDocumentID, coreTaskID string, submitAt time.Time) error {
	at := submitAt.UTC()
	if at.IsZero() {
		at = time.Now().UTC()
	}
	return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var task parseTaskEntity
		if err := tx.Take(&task, "id = ?", taskID).Error; err != nil {
			return err
		}
		if err := tx.Model(&parseTaskEntity{}).Where("id = ?", taskID).Updates(map[string]any{
			"status":                    "SUBMITTED",
			"scan_orchestration_status": "SUBMITTED",
			"core_dataset_id":           strings.TrimSpace(coreDatasetID),
			"core_document_id":          strings.TrimSpace(coreDocumentID),
			"core_task_id":              strings.TrimSpace(coreTaskID),
			"submit_error_message":      "",
			"submit_at":                 &at,
			"last_error":                "",
			"lease_owner":               "",
			"lease_until":               nil,
			"finished_at":               &at,
			"updated_at":                at,
		}).Error; err != nil {
			return err
		}
		docUpdates := map[string]any{
			"next_parse_at": nil,
			"updated_at":    at,
		}
		if strings.TrimSpace(coreDocumentID) != "" {
			docUpdates["core_document_id"] = strings.TrimSpace(coreDocumentID)
		}
		if normalizeTaskAction(task.TaskAction) == taskActionDelete {
			docUpdates["parse_status"] = "DELETED"
		} else {
			docUpdates["parse_status"] = "QUEUED"
		}
		return tx.Model(&documentEntity{}).Where("id = ?", task.DocumentID).Updates(docUpdates).Error
	})
}

type SubmittedCoreTaskRef struct {
	TaskID         int64
	CoreDatasetID  string
	CoreDocumentID string
	CoreTaskID     string
}

func (s *Store) FindSubmittedTaskByIdempotencyKey(ctx context.Context, tenantID, idempotencyKey string, excludeTaskID int64) (SubmittedCoreTaskRef, error) {
	ref := SubmittedCoreTaskRef{}
	tenantID = strings.TrimSpace(tenantID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if tenantID == "" || idempotencyKey == "" {
		return ref, nil
	}
	query := s.db.WithContext(ctx).
		Model(&parseTaskEntity{}).
		Select("id AS task_id, core_dataset_id, core_document_id, core_task_id").
		Where("tenant_id = ? AND idempotency_key = ? AND core_task_id IS NOT NULL AND core_task_id <> ''", tenantID, idempotencyKey).
		Where("status IN ?", []string{"SUBMITTED", "SUCCEEDED"})
	if excludeTaskID > 0 {
		query = query.Where("id <> ?", excludeTaskID)
	}
	err := query.Order("id DESC").Limit(1).Scan(&ref).Error
	if err != nil {
		return SubmittedCoreTaskRef{}, err
	}
	return ref, nil
}

func (s *Store) MarkTaskSubmitFailed(ctx context.Context, taskID int64, lastError string) error {
	now := time.Now().UTC()
	return s.db.WithContext(ctx).Model(&parseTaskEntity{}).Where("id = ?", taskID).Updates(map[string]any{
		"status":                    "SUBMIT_FAILED",
		"scan_orchestration_status": "SUBMIT_FAILED",
		"submit_error_message":      lastError,
		"last_error":                lastError,
		"finished_at":               &now,
		"lease_owner":               "",
		"lease_until":               nil,
		"updated_at":                now,
	}).Error
}

func (s *Store) MarkTaskRetryWaiting(ctx context.Context, taskID int64, retryCount int, nextRunAt time.Time, lastError string) error {
	now := time.Now().UTC()
	return s.db.WithContext(ctx).Model(&parseTaskEntity{}).Where("id = ?", taskID).Updates(map[string]any{
		"status":                    "RETRY_WAITING",
		"scan_orchestration_status": "RETRY_WAITING",
		"retry_count":               retryCount,
		"next_run_at":               nextRunAt.UTC(),
		"submit_error_message":      lastError,
		"last_error":                lastError,
		"lease_owner":               "",
		"lease_until":               nil,
		"updated_at":                now,
	}).Error
}

func (s *Store) MarkTaskFailed(ctx context.Context, taskID int64, lastError string) error {
	now := time.Now().UTC()
	return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var task parseTaskEntity
		if err := tx.Take(&task, "id = ?", taskID).Error; err != nil {
			return err
		}
		if err := tx.Model(&parseTaskEntity{}).Where("id = ?", taskID).Updates(map[string]any{
			"status":                    "FAILED",
			"scan_orchestration_status": "FAILED",
			"last_error":                lastError,
			"finished_at":               &now,
			"lease_owner":               "",
			"lease_until":               nil,
			"updated_at":                now,
		}).Error; err != nil {
			return err
		}
		dead := parseTaskDeadLetterEntity{
			TaskID:          task.ID,
			TenantID:        task.TenantID,
			DocumentID:      task.DocumentID,
			TargetVersionID: task.TargetVersionID,
			RetryCount:      task.RetryCount,
			OriginType:      task.OriginType,
			OriginPlatform:  task.OriginPlatform,
			TriggerPolicy:   task.TriggerPolicy,
			LastError:       lastError,
			FailedAt:        now,
			CreatedAt:       now,
		}
		return tx.Create(&dead).Error
	})
}

func (s *Store) MarkTaskSucceeded(ctx context.Context, taskID int64, documentID int64, targetVersion string) error {
	now := time.Now().UTC()
	return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var task parseTaskEntity
		if err := tx.Take(&task, "id = ?", taskID).Error; err != nil {
			return err
		}
		if err := tx.Model(&parseTaskEntity{}).Where("id = ?", taskID).Updates(map[string]any{
			"status":                    "SUCCEEDED",
			"scan_orchestration_status": "SUCCEEDED",
			"last_error":                "",
			"finished_at":               &now,
			"lease_owner":               "",
			"lease_until":               nil,
			"updated_at":                now,
		}).Error; err != nil {
			return err
		}
		docUpdates := map[string]any{
			"updated_at": now,
		}
		if normalizeTaskAction(task.TaskAction) == taskActionDelete {
			docUpdates["current_version_id"] = ""
			docUpdates["desired_version_id"] = ""
			docUpdates["core_document_id"] = ""
			docUpdates["parse_status"] = "DELETED"
			docUpdates["next_parse_at"] = nil
		} else {
			docUpdates["current_version_id"] = targetVersion
			docUpdates["parse_status"] = "SUCCEEDED"
		}
		return tx.Model(&documentEntity{}).Where("id = ?", documentID).Updates(docUpdates).Error
	})
}

func (s *Store) UpdateDocumentRunning(ctx context.Context, documentID int64) error {
	now := time.Now().UTC()
	return s.db.WithContext(ctx).Model(&documentEntity{}).Where("id = ?", documentID).Updates(map[string]any{
		"parse_status": "RUNNING",
		"updated_at":   now,
	}).Error
}

func (s *Store) DesiredVersionMatches(ctx context.Context, documentID int64, targetVersion string) (bool, error) {
	var doc documentEntity
	if err := s.db.WithContext(ctx).Select("id", "desired_version_id").Take(&doc, "id = ?", documentID).Error; err != nil {
		return false, err
	}
	return strings.TrimSpace(doc.DesiredVersionID) == strings.TrimSpace(targetVersion), nil
}

func (s *Store) MarkAgentsOffline(ctx context.Context, now time.Time, timeout time.Duration) (int64, error) {
	if timeout <= 0 {
		return 0, nil
	}
	threshold := now.UTC().Add(-timeout)
	var offlineIDs []string
	if err := s.db.WithContext(ctx).Model(&agentEntity{}).
		Where("status <> ? AND last_heartbeat_at <= ?", "OFFLINE", threshold).
		Pluck("agent_id", &offlineIDs).Error; err != nil {
		return 0, err
	}
	if len(offlineIDs) == 0 {
		return 0, nil
	}
	return int64(len(offlineIDs)), s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Model(&agentEntity{}).
			Where("agent_id IN ?", offlineIDs).
			Updates(map[string]any{
				"status":     "OFFLINE",
				"updated_at": now.UTC(),
			}).Error; err != nil {
			return err
		}
		return tx.Model(&sourceEntity{}).
			Where("agent_id IN ? AND status = ?", offlineIDs, string(model.SourceStatusEnabled)).
			Updates(map[string]any{
				"status":     string(model.SourceStatusDegraded),
				"updated_at": now.UTC(),
			}).Error
	})
}

func (s *Store) ReportSnapshotMetadata(ctx context.Context, req model.ReportSnapshotRequest) error {
	if strings.TrimSpace(req.SourceID) == "" {
		return fmt.Errorf("source_id is required")
	}
	takenAt := req.TakenAt.UTC()
	if takenAt.IsZero() {
		takenAt = time.Now().UTC()
	}
	now := time.Now().UTC()
	entity := reconcileSnapshotEntity{
		SourceID:    strings.TrimSpace(req.SourceID),
		SnapshotRef: strings.TrimSpace(req.SnapshotRef),
		FileCount:   req.FileCount,
		TakenAt:     takenAt,
		UpdatedAt:   now,
	}
	if entity.SnapshotRef == "" {
		entity.SnapshotRef = "local://unknown"
	}
	return s.db.WithContext(ctx).Clauses(clause.OnConflict{
		Columns: []clause.Column{{Name: "source_id"}},
		DoUpdates: clause.Assignments(map[string]any{
			"snapshot_ref": entity.SnapshotRef,
			"file_count":   entity.FileCount,
			"taken_at":     entity.TakenAt,
			"updated_at":   entity.UpdatedAt,
		}),
	}).Create(&entity).Error
}

type parseTaskListRow struct {
	TaskID                  int64
	TenantID                string
	SourceID                string
	SourceName              string
	DocumentID              int64
	SourceObjectID          string
	TaskAction              string
	TargetVersionID         string
	Status                  string
	RetryCount              int
	MaxRetryCount           int
	OriginType              string
	OriginPlatform          string
	TriggerPolicy           string
	NextRunAt               time.Time
	StartedAt               *time.Time
	FinishedAt              *time.Time
	LastError               string
	CreatedAt               time.Time
	UpdatedAt               time.Time
	AgentID                 string
	AgentListenAddr         string
	CoreDatasetID           string
	CoreDocumentID          string
	CoreTaskID              string
	ScanOrchestrationStatus string
	SubmitErrorMessage      string
	SubmitAt                *time.Time
}

type parseTaskDetailRow struct {
	TaskID                  int64
	TenantID                string
	SourceID                string
	SourceName              string
	DocumentID              int64
	SourceObjectID          string
	TaskAction              string
	TargetVersionID         string
	Status                  string
	RetryCount              int
	MaxRetryCount           int
	OriginType              string
	OriginPlatform          string
	TriggerPolicy           string
	NextRunAt               time.Time
	StartedAt               *time.Time
	FinishedAt              *time.Time
	LastError               string
	CreatedAt               time.Time
	UpdatedAt               time.Time
	AgentID                 string
	AgentListenAddr         string
	CoreDatasetID           string
	CoreDocumentID          string
	CoreTaskID              string
	ScanOrchestrationStatus string
	SubmitErrorMessage      string
	SubmitAt                *time.Time
	DesiredVersionID        string
	CurrentVersionID        string
	DocumentParseStatus     string
}

func (s *Store) ListParseTasks(ctx context.Context, req model.ListParseTasksRequest) (model.ListParseTasksResponse, error) {
	resp := model.ListParseTasksResponse{
		Items: []model.ParseTaskListItem{},
	}
	filter := buildParseTaskFilter(req)
	if filter.TenantID == "" {
		return resp, fmt.Errorf("tenant_id is required")
	}
	page, pageSize := normalizePageAndSize(req.Page, req.PageSize)
	resp.Page = page
	resp.PageSize = pageSize

	countQuery := s.db.WithContext(ctx).
		Table("parse_tasks pt").
		Joins("JOIN documents d ON d.id = pt.document_id")
	countQuery = s.applyParseTaskFilters(countQuery, filter)
	if err := countQuery.Count(&resp.Total).Error; err != nil {
		return resp, err
	}

	var rows []parseTaskListRow
	query := s.db.WithContext(ctx).
		Table("parse_tasks pt").
		Select(`
			pt.id AS task_id,
			pt.tenant_id AS tenant_id,
			d.source_id AS source_id,
			s.name AS source_name,
			pt.document_id AS document_id,
			d.source_object_id AS source_object_id,
			pt.task_action AS task_action,
			pt.target_version_id AS target_version_id,
			pt.status AS status,
			pt.retry_count AS retry_count,
			pt.max_retry_count AS max_retry_count,
			pt.origin_type AS origin_type,
			pt.origin_platform AS origin_platform,
			pt.trigger_policy AS trigger_policy,
			pt.next_run_at AS next_run_at,
			pt.started_at AS started_at,
			pt.finished_at AS finished_at,
			pt.last_error AS last_error,
			pt.created_at AS created_at,
			pt.updated_at AS updated_at,
			s.agent_id AS agent_id,
			a.listen_addr AS agent_listen_addr,
			pt.core_dataset_id AS core_dataset_id,
			pt.core_document_id AS core_document_id,
			pt.core_task_id AS core_task_id,
			pt.scan_orchestration_status AS scan_orchestration_status,
			pt.submit_error_message AS submit_error_message,
			pt.submit_at AS submit_at`).
		Joins("JOIN documents d ON d.id = pt.document_id").
		Joins("JOIN sources s ON s.id = d.source_id").
		Joins("LEFT JOIN agents a ON a.agent_id = s.agent_id")
	query = s.applyParseTaskFilters(query, filter)
	offset := (page - 1) * pageSize
	if err := query.
		Order("pt.updated_at DESC, pt.id DESC").
		Offset(offset).
		Limit(pageSize).
		Scan(&rows).Error; err != nil {
		return resp, err
	}

	resp.Items = make([]model.ParseTaskListItem, 0, len(rows))
	for _, row := range rows {
		resp.Items = append(resp.Items, toModelParseTaskListItem(row))
	}
	return resp, nil
}

func (s *Store) GetParseTask(ctx context.Context, taskID int64) (model.ParseTaskDetailResponse, error) {
	var row parseTaskDetailRow
	err := s.db.WithContext(ctx).
		Table("parse_tasks pt").
		Select(`
			pt.id AS task_id,
			pt.tenant_id AS tenant_id,
			d.source_id AS source_id,
			s.name AS source_name,
			pt.document_id AS document_id,
			d.source_object_id AS source_object_id,
			pt.task_action AS task_action,
			pt.target_version_id AS target_version_id,
			pt.status AS status,
			pt.retry_count AS retry_count,
			pt.max_retry_count AS max_retry_count,
			pt.origin_type AS origin_type,
			pt.origin_platform AS origin_platform,
			pt.trigger_policy AS trigger_policy,
			pt.next_run_at AS next_run_at,
			pt.started_at AS started_at,
			pt.finished_at AS finished_at,
			pt.last_error AS last_error,
			pt.created_at AS created_at,
			pt.updated_at AS updated_at,
			s.agent_id AS agent_id,
			a.listen_addr AS agent_listen_addr,
			pt.core_dataset_id AS core_dataset_id,
			pt.core_document_id AS core_document_id,
			pt.core_task_id AS core_task_id,
			pt.scan_orchestration_status AS scan_orchestration_status,
			pt.submit_error_message AS submit_error_message,
			pt.submit_at AS submit_at,
			d.desired_version_id AS desired_version_id,
			d.current_version_id AS current_version_id,
			d.parse_status AS document_parse_status`).
		Joins("JOIN documents d ON d.id = pt.document_id").
		Joins("JOIN sources s ON s.id = d.source_id").
		Joins("LEFT JOIN agents a ON a.agent_id = s.agent_id").
		Where("pt.id = ?", taskID).
		Take(&row).Error
	if err != nil {
		return model.ParseTaskDetailResponse{}, err
	}
	return toModelParseTaskDetail(row), nil
}

func (s *Store) CountParseTasksByStatusWithFilter(ctx context.Context, tenantID, sourceID string) (map[string]int64, error) {
	filter := parseTaskFilter{
		TenantID: strings.TrimSpace(tenantID),
		SourceID: strings.TrimSpace(sourceID),
	}
	if filter.TenantID == "" {
		return nil, fmt.Errorf("tenant_id is required")
	}
	type row struct {
		Status string
		Count  int64
	}
	var rows []row
	query := s.db.WithContext(ctx).
		Table("parse_tasks pt").
		Select("pt.status AS status, COUNT(*) AS count").
		Joins("JOIN documents d ON d.id = pt.document_id")
	query = s.applyParseTaskFilters(query, filter)
	if err := query.Group("pt.status").Scan(&rows).Error; err != nil {
		return nil, err
	}
	result := make(map[string]int64, len(rows))
	for _, item := range rows {
		result[item.Status] = item.Count
	}
	return result, nil
}

func (s *Store) latestParseTasksByDocumentIDs(ctx context.Context, documentIDs []int64) (map[int64]parseTaskDocJoin, error) {
	result := make(map[int64]parseTaskDocJoin)
	if len(documentIDs) == 0 {
		return result, nil
	}
	sub := s.db.WithContext(ctx).
		Table("parse_tasks").
		Select("MAX(id) AS max_id").
		Where("document_id IN ?", documentIDs).
		Group("document_id")
	var rows []parseTaskDocJoin
	if err := s.db.WithContext(ctx).
		Table("parse_tasks pt").
		Select("pt.document_id, pt.task_action, pt.core_document_id, pt.status, pt.core_dataset_id, pt.core_task_id, pt.scan_orchestration_status").
		Joins("JOIN (?) latest ON latest.max_id = pt.id", sub).
		Scan(&rows).Error; err != nil {
		return nil, err
	}
	for _, row := range rows {
		result[row.DocumentID] = row
	}
	return result, nil
}

func (s *Store) RetryParseTask(ctx context.Context, taskID int64) (model.ParseTaskDetailResponse, error) {
	if taskID <= 0 {
		return model.ParseTaskDetailResponse{}, fmt.Errorf("task_id must be > 0")
	}
	now := time.Now().UTC()
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var task parseTaskEntity
		if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).Take(&task, "id = ?", taskID).Error; err != nil {
			return err
		}
		status := strings.ToUpper(strings.TrimSpace(task.Status))
		allow := map[string]bool{
			"SUBMIT_FAILED": true,
		}
		if !allow[status] {
			return fmt.Errorf("task status %s does not support retry", task.Status)
		}
		if err := tx.Model(&parseTaskEntity{}).Where("id = ?", taskID).Updates(map[string]any{
			"status":                    "PENDING",
			"retry_count":               0,
			"next_run_at":               now,
			"lease_owner":               "",
			"lease_until":               nil,
			"started_at":                nil,
			"finished_at":               nil,
			"last_error":                "",
			"scan_orchestration_status": "PENDING",
			"submit_error_message":      "",
			"submit_at":                 nil,
			"updated_at":                now,
		}).Error; err != nil {
			return err
		}
		docUpdates := map[string]any{
			"next_parse_at": nil,
			"updated_at":    now,
		}
		if normalizeTaskAction(task.TaskAction) == taskActionDelete {
			docUpdates["parse_status"] = "DELETED"
		} else {
			docUpdates["parse_status"] = "QUEUED"
		}
		return tx.Model(&documentEntity{}).Where("id = ?", task.DocumentID).Updates(docUpdates).Error
	})
	if err != nil {
		return model.ParseTaskDetailResponse{}, err
	}
	return s.GetParseTask(ctx, taskID)
}

func (s *Store) CountParseTasksByStatus(ctx context.Context) (map[string]int64, error) {
	return s.countByStatus(ctx, "parse_tasks")
}

func (s *Store) CountCommandsByStatus(ctx context.Context) (map[string]int64, error) {
	return s.countByStatus(ctx, "agent_commands")
}

func (s *Store) CountAgentsByStatus(ctx context.Context) (map[string]int64, error) {
	return s.countByStatus(ctx, "agents")
}

func (s *Store) CountSourcesByStatus(ctx context.Context) (map[string]int64, error) {
	return s.countByStatus(ctx, "sources")
}

func (s *Store) countByStatus(ctx context.Context, table string) (map[string]int64, error) {
	type row struct {
		Status string
		Count  int64
	}
	var rows []row
	if err := s.db.WithContext(ctx).Table(table).
		Select("status, COUNT(*) AS count").
		Group("status").
		Scan(&rows).Error; err != nil {
		return nil, err
	}
	result := make(map[string]int64, len(rows))
	for _, item := range rows {
		result[item.Status] = item.Count
	}
	return result, nil
}

func (s *Store) ListAgents(ctx context.Context, tenantID string) ([]model.Agent, error) {
	var entities []agentEntity
	db := s.db.WithContext(ctx).Order("updated_at DESC")
	if tenantID != "" {
		db = db.Where("tenant_id = ?", tenantID)
	}
	if err := db.Find(&entities).Error; err != nil {
		return nil, err
	}

	result := make([]model.Agent, 0, len(entities))
	for _, item := range entities {
		result = append(result, toModelAgent(item))
	}
	return result, nil
}

func (s *Store) GetAgent(ctx context.Context, agentID string) (model.Agent, error) {
	var item agentEntity
	if err := s.db.WithContext(ctx).First(&item, "agent_id = ?", agentID).Error; err != nil {
		return model.Agent{}, err
	}
	return toModelAgent(item), nil
}

func (s *Store) EnsureSourceByRootPath(ctx context.Context, req model.CreateSourceRequest) (model.Source, error) {
	return s.ensureSourceByRootPath(ctx, req)
}

func normalizePathsUnderRoot(paths []string, root string) ([]string, int) {
	cleanRoot := filepath.Clean(strings.TrimSpace(root))
	if cleanRoot == "" || cleanRoot == "." {
		return nil, len(paths)
	}
	unique := make(map[string]struct{}, len(paths))
	out := make([]string, 0, len(paths))
	skipped := 0
	for _, raw := range paths {
		p := filepath.Clean(strings.TrimSpace(raw))
		if p == "" || p == "." {
			skipped++
			continue
		}
		if p != cleanRoot && !strings.HasPrefix(p, cleanRoot+string(filepath.Separator)) {
			skipped++
			continue
		}
		if _, ok := unique[p]; ok {
			continue
		}
		unique[p] = struct{}{}
		out = append(out, p)
	}
	return out, skipped
}

func normalizeEventType(v string) string {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "created":
		return "created"
	case "deleted":
		return "deleted"
	default:
		return "modified"
	}
}

func firstNonEmpty(values ...string) string {
	for _, item := range values {
		if strings.TrimSpace(item) != "" {
			return strings.TrimSpace(item)
		}
	}
	return ""
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func isUniqueConstraintError(err error) bool {
	if err == nil {
		return false
	}
	msg := strings.ToLower(err.Error())
	return strings.Contains(msg, "duplicate key") ||
		strings.Contains(msg, "unique constraint") ||
		strings.Contains(msg, "is not unique")
}

func (s *Store) applyParseTaskFilters(db *gorm.DB, filter parseTaskFilter) *gorm.DB {
	if filter.TenantID != "" {
		db = db.Where("pt.tenant_id = ?", filter.TenantID)
	}
	if filter.SourceID != "" {
		db = db.Where("d.source_id = ?", filter.SourceID)
	}
	if len(filter.Statuses) > 0 {
		db = db.Where("pt.status IN ?", filter.Statuses)
	}
	keyword := strings.TrimSpace(filter.Keyword)
	if keyword != "" {
		pattern := "%" + keyword + "%"
		if s.db.Dialector.Name() == "postgres" {
			db = db.Where("d.source_object_id ILIKE ?", pattern)
		} else {
			db = db.Where("LOWER(d.source_object_id) LIKE ?", strings.ToLower(pattern))
		}
	}
	return db
}

func buildParseTaskFilter(req model.ListParseTasksRequest) parseTaskFilter {
	return parseTaskFilter{
		TenantID: strings.TrimSpace(req.TenantID),
		SourceID: strings.TrimSpace(req.SourceID),
		Statuses: splitCSV(req.Status),
		Keyword:  strings.TrimSpace(req.Keyword),
	}
}

func splitCSV(v string) []string {
	raw := strings.TrimSpace(v)
	if raw == "" {
		return nil
	}
	parts := strings.Split(raw, ",")
	uniq := make(map[string]struct{}, len(parts))
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		item := strings.TrimSpace(p)
		if item == "" {
			continue
		}
		if _, ok := uniq[item]; ok {
			continue
		}
		uniq[item] = struct{}{}
		out = append(out, item)
	}
	return out
}

func normalizePageAndSize(page, pageSize int) (int, int) {
	if page <= 0 {
		page = 1
	}
	if pageSize <= 0 {
		pageSize = 20
	}
	if pageSize > 200 {
		pageSize = 200
	}
	return page, pageSize
}

func normalizeUpdateTypeFilter(raw string) string {
	switch strings.ToUpper(strings.TrimSpace(raw)) {
	case "NEW":
		return "NEW"
	case "MODIFIED":
		return "MODIFIED"
	case "DELETED":
		return "DELETED"
	case "NONE", "UNCHANGED":
		return "UNCHANGED"
	default:
		return ""
	}
}

func applyUpdateTypeFilter(db *gorm.DB, updateType string) *gorm.DB {
	switch updateType {
	case "NEW":
		return db.Where("parse_status <> ? AND desired_version_id IS NOT NULL AND desired_version_id <> '' AND (current_version_id IS NULL OR current_version_id = '')", "DELETED")
	case "MODIFIED":
		return db.Where("parse_status <> ? AND desired_version_id IS NOT NULL AND desired_version_id <> '' AND current_version_id IS NOT NULL AND current_version_id <> '' AND desired_version_id <> current_version_id", "DELETED")
	case "DELETED":
		return db.Where("parse_status = ?", "DELETED")
	case "UNCHANGED":
		return db.Where("parse_status <> ? AND desired_version_id IS NOT NULL AND desired_version_id <> '' AND desired_version_id = current_version_id", "DELETED")
	default:
		return db
	}
}

func collectTreeFilePaths(items []model.TreeNode) []string {
	out := make([]string, 0, 64)
	var walk func(nodes []model.TreeNode)
	walk = func(nodes []model.TreeNode) {
		for _, node := range nodes {
			if node.IsDir {
				if len(node.Children) > 0 {
					walk(node.Children)
				}
				continue
			}
			p := strings.TrimSpace(node.Key)
			if p == "" {
				continue
			}
			out = append(out, p)
		}
	}
	walk(items)
	return out
}

func applyWatchTreeNodeStates(items []model.TreeNode, docMap map[string]treeDocumentRow, queueMap map[int64]parseTaskDocJoin) []model.TreeNode {
	out := make([]model.TreeNode, 0, len(items))
	for _, node := range items {
		item := node
		if item.IsDir {
			item.Children = applyWatchTreeNodeStates(item.Children, docMap, queueMap)
			v := false
			item.Selectable = &v
			item.StatusSource = "UNKNOWN"
			out = append(out, item)
			continue
		}
		v := true
		item.Selectable = &v
		path := strings.TrimSpace(item.Key)
		doc, ok := docMap[path]
		if !ok {
			item.UpdateType = "UNKNOWN"
			item.UpdateDesc = updateTypeDescription("UNKNOWN")
			item.StatusSource = "UNKNOWN"
			out = append(out, item)
			continue
		}
		updateType := inferDocumentUpdateType(doc.DesiredVersionID, doc.CurrentVersionID, doc.ParseStatus)
		item.UpdateType = updateType
		item.UpdateDesc = updateTypeDescription(updateType)
		item.StatusSource = "DOCUMENTS"
		switch updateType {
		case "NEW", "MODIFIED", "DELETED":
			has := true
			item.HasUpdate = &has
		case "UNCHANGED":
			has := false
			item.HasUpdate = &has
		default:
			item.HasUpdate = nil
		}
		if queue, ok := queueMap[doc.ID]; ok {
			item.ParseQueueState = queue.Status
		}
		out = append(out, item)
	}
	return out
}

func applySnapshotTreeNodeStates(items []model.TreeNode, diffByPath map[string]string, docMap map[string]treeDocumentRow, queueMap map[int64]parseTaskDocJoin) []model.TreeNode {
	out := make([]model.TreeNode, 0, len(items))
	for _, node := range items {
		item := node
		if item.IsDir {
			item.Children = applySnapshotTreeNodeStates(item.Children, diffByPath, docMap, queueMap)
			v := false
			item.Selectable = &v
			item.StatusSource = "UNKNOWN"
			out = append(out, item)
			continue
		}
		v := true
		item.Selectable = &v
		path := strings.TrimSpace(item.Key)
		updateType := strings.TrimSpace(diffByPath[path])
		if updateType == "" {
			updateType = "UNKNOWN"
		}
		item.UpdateType = updateType
		item.UpdateDesc = updateTypeDescription(updateType)
		item.StatusSource = "SNAPSHOT"
		switch updateType {
		case "NEW", "MODIFIED", "DELETED":
			has := true
			item.HasUpdate = &has
		case "UNCHANGED":
			has := false
			item.HasUpdate = &has
		default:
			item.HasUpdate = nil
		}
		if doc, ok := docMap[path]; ok {
			if queue, ok := queueMap[doc.ID]; ok {
				item.ParseQueueState = queue.Status
			}
		}
		out = append(out, item)
	}
	return out
}

func (s *Store) filterPathsByUpdatedOnly(ctx context.Context, sourceID string, paths []string) ([]string, int, error) {
	if len(paths) == 0 {
		return nil, 0, nil
	}
	var docs []treeDocumentRow
	if err := s.db.WithContext(ctx).
		Table("documents").
		Select("id, source_object_id, desired_version_id, current_version_id, parse_status").
		Where("source_id = ? AND source_object_id IN ?", sourceID, paths).
		Scan(&docs).Error; err != nil {
		return nil, 0, err
	}
	docMap := make(map[string]treeDocumentRow, len(docs))
	for _, doc := range docs {
		docMap[doc.SourceObjectID] = doc
	}
	filtered := make([]string, 0, len(paths))
	ignored := 0
	for _, path := range paths {
		doc, ok := docMap[path]
		if !ok {
			// No document record yet, treat as NEW.
			filtered = append(filtered, path)
			continue
		}
		updateType := inferDocumentUpdateType(doc.DesiredVersionID, doc.CurrentVersionID, doc.ParseStatus)
		if updateType == "NEW" || updateType == "MODIFIED" || updateType == "DELETED" {
			filtered = append(filtered, path)
			continue
		}
		ignored++
	}
	return filtered, ignored, nil
}

func filterPathsByDiff(paths []string, diffByPath map[string]string) ([]string, int) {
	filtered := make([]string, 0, len(paths))
	ignored := 0
	for _, path := range paths {
		updateType := strings.ToUpper(strings.TrimSpace(diffByPath[path]))
		if updateType == "NEW" || updateType == "MODIFIED" || updateType == "DELETED" {
			filtered = append(filtered, path)
			continue
		}
		ignored++
	}
	return filtered, ignored
}

func collectDeletedPathsFromDiff(diffByPath map[string]string, currentPaths []string) []string {
	currentSet := make(map[string]struct{}, len(currentPaths))
	for _, path := range currentPaths {
		currentSet[filepath.Clean(strings.TrimSpace(path))] = struct{}{}
	}
	out := make([]string, 0, len(diffByPath))
	for path, state := range diffByPath {
		if strings.ToUpper(strings.TrimSpace(state)) != "DELETED" {
			continue
		}
		cleanPath := filepath.Clean(strings.TrimSpace(path))
		if _, ok := currentSet[cleanPath]; ok {
			continue
		}
		out = append(out, cleanPath)
	}
	return out
}

func addDeletedNodes(items []model.TreeNode, deletedPaths []string, rootPath, statusSource string, docMap map[string]treeDocumentRow, queueMap map[int64]parseTaskDocJoin) []model.TreeNode {
	for _, path := range deletedPaths {
		items = insertDeletedNode(items, path, rootPath, statusSource, docMap, queueMap)
	}
	return items
}

func insertDeletedNode(nodes []model.TreeNode, filePath, rootPath, statusSource string, docMap map[string]treeDocumentRow, queueMap map[int64]parseTaskDocJoin) []model.TreeNode {
	filePath = filepath.Clean(strings.TrimSpace(filePath))
	if filePath == "" || filePath == "." {
		return nodes
	}
	if findNodeByKey(nodes, filePath) >= 0 {
		return nodes
	}
	ancestors := buildAncestorPaths(filePath, rootPath)
	return ensureDeletedAtPath(nodes, ancestors, filePath, statusSource, docMap, queueMap)
}

func ensureDeletedAtPath(nodes []model.TreeNode, ancestors []string, filePath, statusSource string, docMap map[string]treeDocumentRow, queueMap map[int64]parseTaskDocJoin) []model.TreeNode {
	if len(ancestors) == 0 {
		if findNodeByKey(nodes, filePath) >= 0 {
			return nodes
		}
		hasUpdate := true
		selectable := true
		node := model.TreeNode{
			Title:        nodeTitleFromPath(filePath),
			Key:          filePath,
			IsDir:        false,
			HasUpdate:    &hasUpdate,
			UpdateType:   "DELETED",
			UpdateDesc:   updateTypeDescription("DELETED"),
			Selectable:   &selectable,
			StatusSource: statusSource,
		}
		if doc, ok := docMap[filePath]; ok {
			if queue, ok := queueMap[doc.ID]; ok {
				node.ParseQueueState = queue.Status
			}
		}
		return append(nodes, node)
	}
	dirPath := ancestors[0]
	idx := findDirNodeByKey(nodes, dirPath)
	if idx < 0 {
		selectable := false
		hasUpdate := true
		nodes = append(nodes, model.TreeNode{
			Title:        nodeTitleFromPath(dirPath),
			Key:          dirPath,
			IsDir:        true,
			HasUpdate:    &hasUpdate,
			UpdateType:   "DELETED",
			UpdateDesc:   updateTypeDescription("DELETED"),
			Selectable:   &selectable,
			StatusSource: statusSource,
		})
		idx = len(nodes) - 1
	}
	child := nodes[idx]
	if child.IsDir {
		hasUpdate := true
		child.HasUpdate = &hasUpdate
		if strings.TrimSpace(child.UpdateType) == "" || strings.EqualFold(strings.TrimSpace(child.UpdateType), "UNKNOWN") {
			child.UpdateType = "DELETED"
			child.UpdateDesc = updateTypeDescription("DELETED")
		}
	}
	child.Children = ensureDeletedAtPath(child.Children, ancestors[1:], filePath, statusSource, docMap, queueMap)
	nodes[idx] = child
	return nodes
}

func buildAncestorPaths(filePath, rootPath string) []string {
	filePath = filepath.Clean(strings.TrimSpace(filePath))
	rootPath = filepath.Clean(strings.TrimSpace(rootPath))
	dirPath := filepath.Clean(filepath.Dir(filePath))
	if dirPath == "." || dirPath == filePath {
		return nil
	}
	if rootPath == "" || rootPath == "." {
		return []string{dirPath}
	}
	if dirPath != rootPath && !strings.HasPrefix(dirPath, rootPath+string(filepath.Separator)) {
		return []string{dirPath}
	}
	if dirPath == rootPath {
		return []string{rootPath}
	}
	rel := strings.TrimPrefix(strings.TrimPrefix(dirPath, rootPath), string(filepath.Separator))
	parts := strings.Split(rel, string(filepath.Separator))
	out := make([]string, 0, len(parts)+1)
	out = append(out, rootPath)
	cur := rootPath
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		cur = filepath.Join(cur, part)
		out = append(out, cur)
	}
	return out
}

func findDirNodeByKey(nodes []model.TreeNode, key string) int {
	for i := range nodes {
		if nodes[i].Key == key && nodes[i].IsDir {
			return i
		}
	}
	return -1
}

func findNodeByKey(nodes []model.TreeNode, key string) int {
	for i := range nodes {
		if nodes[i].Key == key {
			return i
		}
	}
	return -1
}

func nodeTitleFromPath(path string) string {
	name := filepath.Base(strings.TrimSpace(path))
	if name == "." || name == "/" || name == string(filepath.Separator) {
		return path
	}
	return name
}

func collectTreeScopeRoots(items []model.TreeNode) []string {
	dirRoots := make([]string, 0, len(items))
	seen := make(map[string]struct{}, len(items))
	fileKeys := make([]string, 0, len(items))
	for _, item := range items {
		key := filepath.Clean(strings.TrimSpace(item.Key))
		if key == "" || key == "." {
			continue
		}
		if item.IsDir {
			if _, ok := seen[key]; ok {
				continue
			}
			seen[key] = struct{}{}
			dirRoots = append(dirRoots, key)
			continue
		}
		fileKeys = append(fileKeys, key)
	}
	if len(dirRoots) > 0 {
		return dirRoots
	}
	if len(fileKeys) == 0 {
		return nil
	}
	common := filepath.Clean(filepath.Dir(fileKeys[0]))
	for i := 1; i < len(fileKeys); i++ {
		key := filepath.Clean(fileKeys[i])
		for common != "" && common != "." && common != string(filepath.Separator) && !pathInScope(key, []string{common}) {
			parent := filepath.Clean(filepath.Dir(common))
			if parent == common {
				break
			}
			common = parent
		}
	}
	if common == "" || common == "." {
		return nil
	}
	return []string{common}
}

func pathInScope(path string, roots []string) bool {
	path = filepath.Clean(strings.TrimSpace(path))
	if path == "" || path == "." {
		return false
	}
	if len(roots) == 0 {
		return true
	}
	for _, root := range roots {
		root = filepath.Clean(strings.TrimSpace(root))
		if root == "" || root == "." {
			continue
		}
		if path == root || strings.HasPrefix(path, root+string(filepath.Separator)) {
			return true
		}
	}
	return false
}

func (s *Store) deletedDocumentPaths(ctx context.Context, sourceID string, scopeRoots []string, currentPaths []string) ([]string, error) {
	var rows []struct {
		SourceObjectID string
	}
	query := s.db.WithContext(ctx).
		Table("documents").
		Select("source_object_id").
		Where("source_id = ? AND parse_status = ?", sourceID, "DELETED")
	if err := query.Scan(&rows).Error; err != nil {
		return nil, err
	}
	currentSet := make(map[string]struct{}, len(currentPaths))
	for _, path := range currentPaths {
		currentSet[filepath.Clean(strings.TrimSpace(path))] = struct{}{}
	}
	out := make([]string, 0, len(rows))
	for _, row := range rows {
		path := filepath.Clean(strings.TrimSpace(row.SourceObjectID))
		if path == "" || path == "." {
			continue
		}
		if len(scopeRoots) > 0 && !pathInScope(path, scopeRoots) {
			continue
		}
		if _, ok := currentSet[path]; ok {
			continue
		}
		out = append(out, path)
	}
	return out, nil
}

func (s *Store) loadPreviewSnapshotBySelectionToken(ctx context.Context, sourceID, selectionToken string) (sourceFileSnapshotEntity, error) {
	var snap sourceFileSnapshotEntity
	err := s.db.WithContext(ctx).
		Where("source_id = ? AND selection_token = ? AND snapshot_type = ?", sourceID, strings.TrimSpace(selectionToken), "PREVIEW").
		Take(&snap).Error
	return snap, err
}

func (s *Store) loadUsablePreviewSnapshotBySelectionToken(ctx context.Context, sourceID, selectionToken string, now time.Time) (sourceFileSnapshotEntity, error) {
	var snap sourceFileSnapshotEntity
	err := s.db.WithContext(ctx).
		Where("source_id = ? AND selection_token = ? AND snapshot_type = ? AND consumed_at IS NULL AND (expires_at IS NULL OR expires_at > ?)", sourceID, strings.TrimSpace(selectionToken), "PREVIEW", now.UTC()).
		Take(&snap).Error
	return snap, err
}

func (s *Store) loadSnapshotByID(ctx context.Context, snapshotID string) (sourceFileSnapshotEntity, error) {
	var snap sourceFileSnapshotEntity
	err := s.db.WithContext(ctx).Take(&snap, "snapshot_id = ?", strings.TrimSpace(snapshotID)).Error
	return snap, err
}

func (s *Store) diffBySnapshotID(ctx context.Context, snapshot sourceFileSnapshotEntity) (map[string]string, error) {
	currentItems, err := s.snapshotItemsByPath(ctx, snapshot.SnapshotID)
	if err != nil {
		return nil, err
	}
	baseItems, err := s.snapshotItemsByPath(ctx, snapshot.BaseSnapshotID)
	if err != nil {
		return nil, err
	}
	return diffSnapshotMaps(baseItems, currentItems), nil
}

func (s *Store) promotePreviewSnapshotToCommitted(ctx context.Context, sourceID, snapshotID string) error {
	sourceID = strings.TrimSpace(sourceID)
	snapshotID = strings.TrimSpace(snapshotID)
	if sourceID == "" || snapshotID == "" {
		return nil
	}
	now := time.Now().UTC()
	return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		return s.promotePreviewSnapshotToCommittedTx(tx, sourceID, snapshotID, now)
	})
}

func (s *Store) syncCommittedSnapshotMetadataTx(tx *gorm.DB, sourceID, tenantID, snapshotRef string, fileCount int64, takenAt, now time.Time) error {
	sourceID = strings.TrimSpace(sourceID)
	tenantID = strings.TrimSpace(tenantID)
	if sourceID == "" {
		return nil
	}
	if tenantID == "" {
		var src sourceEntity
		if err := tx.Select("tenant_id").Take(&src, "id = ?", sourceID).Error; err == nil {
			tenantID = strings.TrimSpace(src.TenantID)
		}
	}
	if tenantID == "" {
		return nil
	}
	var relation sourceSnapshotRelationEntity
	if err := tx.Take(&relation, "source_id = ?", sourceID).Error; err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		return err
	}
	createdAt := takenAt.UTC()
	if createdAt.IsZero() {
		createdAt = now.UTC()
	}
	snapshotID := sourceSnapshotID()
	entity := sourceFileSnapshotEntity{
		SnapshotID:     snapshotID,
		SourceID:       sourceID,
		TenantID:       tenantID,
		SnapshotType:   "COMMITTED",
		BaseSnapshotID: strings.TrimSpace(relation.LastCommittedSnapshotID),
		FileCount:      fileCount,
		CreatedAt:      createdAt,
	}
	if err := tx.Create(&entity).Error; err != nil {
		return err
	}
	return tx.Clauses(clause.OnConflict{
		Columns: []clause.Column{{Name: "source_id"}},
		DoUpdates: clause.Assignments(map[string]any{
			"last_committed_snapshot_id": snapshotID,
			"updated_at":                 now.UTC(),
		}),
	}).Create(&sourceSnapshotRelationEntity{
		SourceID:                sourceID,
		LastCommittedSnapshotID: snapshotID,
		UpdatedAt:               now.UTC(),
	}).Error
}

func (s *Store) promotePreviewSnapshotToCommittedTx(tx *gorm.DB, sourceID, snapshotID string, now time.Time) error {
	sourceID = strings.TrimSpace(sourceID)
	snapshotID = strings.TrimSpace(snapshotID)
	if sourceID == "" || snapshotID == "" {
		return nil
	}
	if err := tx.Model(&sourceFileSnapshotEntity{}).
		Where("snapshot_id = ? AND source_id = ?", snapshotID, sourceID).
		Updates(map[string]any{
			"snapshot_type": "COMMITTED",
			"expires_at":    nil,
		}).Error; err != nil {
		return err
	}
	return tx.Clauses(clause.OnConflict{
		Columns: []clause.Column{{Name: "source_id"}},
		DoUpdates: clause.Assignments(map[string]any{
			"last_committed_snapshot_id": snapshotID,
			"updated_at":                 now,
		}),
	}).Create(&sourceSnapshotRelationEntity{
		SourceID:                sourceID,
		LastCommittedSnapshotID: snapshotID,
		UpdatedAt:               now,
	}).Error
}

func (s *Store) consumeSelectionTokenTx(tx *gorm.DB, snapshotID string, consumedAt time.Time) error {
	snapshotID = strings.TrimSpace(snapshotID)
	if snapshotID == "" {
		return nil
	}
	at := consumedAt.UTC()
	if at.IsZero() {
		at = time.Now().UTC()
	}
	res := tx.Model(&sourceFileSnapshotEntity{}).
		Where("snapshot_id = ? AND consumed_at IS NULL", snapshotID).
		Updates(map[string]any{
			"consumed_at": &at,
		})
	if res.Error != nil {
		return res.Error
	}
	if res.RowsAffected == 0 {
		return fmt.Errorf("selection_token already consumed")
	}
	return nil
}

func inferDocumentUpdateType(desiredVersionID, currentVersionID, parseStatus string) string {
	parseStatus = strings.ToUpper(strings.TrimSpace(parseStatus))
	desiredVersionID = strings.TrimSpace(desiredVersionID)
	currentVersionID = strings.TrimSpace(currentVersionID)
	if parseStatus == "DELETED" {
		return "DELETED"
	}
	if desiredVersionID != "" && currentVersionID == "" {
		return "NEW"
	}
	if desiredVersionID != "" && currentVersionID != "" && desiredVersionID != currentVersionID {
		return "MODIFIED"
	}
	if desiredVersionID != "" && desiredVersionID == currentVersionID {
		return "UNCHANGED"
	}
	return "UNKNOWN"
}

func updateTypeDescription(updateType string) string {
	switch updateType {
	case "NEW":
		return "新文件待解析"
	case "MODIFIED":
		return "内容变化待重解析"
	case "DELETED":
		return "文件已删除待同步"
	case "UNCHANGED":
		return "无更新"
	default:
		return "状态未知"
	}
}

func fileTypeFromPath(path string) string {
	ext := strings.TrimPrefix(strings.ToLower(filepath.Ext(strings.TrimSpace(path))), ".")
	return ext
}

func toModelParseTaskListItem(row parseTaskListRow) model.ParseTaskListItem {
	return model.ParseTaskListItem{
		TaskID:                  row.TaskID,
		TenantID:                row.TenantID,
		SourceID:                row.SourceID,
		SourceName:              row.SourceName,
		DocumentID:              row.DocumentID,
		SourceObjectID:          row.SourceObjectID,
		TaskAction:              normalizeTaskAction(row.TaskAction),
		TargetVersionID:         row.TargetVersionID,
		Status:                  row.Status,
		RetryCount:              row.RetryCount,
		MaxRetryCount:           row.MaxRetryCount,
		OriginType:              row.OriginType,
		OriginPlatform:          row.OriginPlatform,
		TriggerPolicy:           row.TriggerPolicy,
		NextRunAt:               row.NextRunAt,
		StartedAt:               row.StartedAt,
		FinishedAt:              row.FinishedAt,
		LastError:               row.LastError,
		CreatedAt:               row.CreatedAt,
		UpdatedAt:               row.UpdatedAt,
		AgentID:                 row.AgentID,
		AgentListenAddr:         row.AgentListenAddr,
		CoreDatasetID:           row.CoreDatasetID,
		CoreDocumentID:          row.CoreDocumentID,
		CoreTaskID:              row.CoreTaskID,
		ScanOrchestrationStatus: row.ScanOrchestrationStatus,
		SubmitErrorMessage:      row.SubmitErrorMessage,
		SubmitAt:                row.SubmitAt,
	}
}

func toModelParseTaskDetail(row parseTaskDetailRow) model.ParseTaskDetailResponse {
	item := model.ParseTaskListItem{
		TaskID:                  row.TaskID,
		TenantID:                row.TenantID,
		SourceID:                row.SourceID,
		SourceName:              row.SourceName,
		DocumentID:              row.DocumentID,
		SourceObjectID:          row.SourceObjectID,
		TaskAction:              normalizeTaskAction(row.TaskAction),
		TargetVersionID:         row.TargetVersionID,
		Status:                  row.Status,
		RetryCount:              row.RetryCount,
		MaxRetryCount:           row.MaxRetryCount,
		OriginType:              row.OriginType,
		OriginPlatform:          row.OriginPlatform,
		TriggerPolicy:           row.TriggerPolicy,
		NextRunAt:               row.NextRunAt,
		StartedAt:               row.StartedAt,
		FinishedAt:              row.FinishedAt,
		LastError:               row.LastError,
		CreatedAt:               row.CreatedAt,
		UpdatedAt:               row.UpdatedAt,
		AgentID:                 row.AgentID,
		AgentListenAddr:         row.AgentListenAddr,
		CoreDatasetID:           row.CoreDatasetID,
		CoreDocumentID:          row.CoreDocumentID,
		CoreTaskID:              row.CoreTaskID,
		ScanOrchestrationStatus: row.ScanOrchestrationStatus,
		SubmitErrorMessage:      row.SubmitErrorMessage,
		SubmitAt:                row.SubmitAt,
	}
	return model.ParseTaskDetailResponse{
		ParseTaskListItem:   item,
		DesiredVersionID:    row.DesiredVersionID,
		CurrentVersionID:    row.CurrentVersionID,
		DocumentParseStatus: row.DocumentParseStatus,
	}
}

func toModelManualPullJob(e manualPullJobEntity) model.ManualPullJob {
	return model.ManualPullJob{
		JobID:                 e.JobID,
		TenantID:              e.TenantID,
		SourceID:              e.SourceID,
		Status:                e.Status,
		Mode:                  e.Mode,
		TriggerPolicy:         e.TriggerPolicy,
		SelectionToken:        e.SelectionToken,
		UpdatedOnly:           e.UpdatedOnly,
		RequestedCount:        e.RequestedCount,
		AcceptedCount:         e.AcceptedCount,
		SkippedCount:          e.SkippedCount,
		IgnoredUnchangedCount: e.IgnoredUnchangedCount,
		ErrorMessage:          e.ErrorMessage,
		CreatedAt:             e.CreatedAt,
		UpdatedAt:             e.UpdatedAt,
		FinishedAt:            e.FinishedAt,
	}
}

func toModelSource(e sourceEntity) model.Source {
	return model.Source{
		ID:                    e.ID,
		TenantID:              e.TenantID,
		Name:                  e.Name,
		SourceType:            e.SourceType,
		RootPath:              e.RootPath,
		Status:                model.SourceStatus(e.Status),
		WatchEnabled:          e.WatchEnabled,
		IdleWindowSeconds:     e.IdleWindowSeconds,
		ReconcileSeconds:      e.ReconcileSeconds,
		ReconcileSchedule:     e.ReconcileSchedule,
		AgentID:               e.AgentID,
		DatasetID:             strings.TrimSpace(e.DatasetID),
		DefaultOriginType:     e.DefaultOriginType,
		DefaultOriginPlatform: e.DefaultOriginPlatform,
		DefaultTriggerPolicy:  e.DefaultTriggerPolicy,
		CreatedAt:             e.CreatedAt,
		UpdatedAt:             e.UpdatedAt,
	}
}

func toModelAgent(e agentEntity) model.Agent {
	return model.Agent{
		AgentID:           e.AgentID,
		TenantID:          e.TenantID,
		Hostname:          e.Hostname,
		Version:           e.Version,
		Status:            e.Status,
		ListenAddr:        e.ListenAddr,
		LastHeartbeatAt:   e.LastHeartbeatAt,
		ActiveSourceCount: e.ActiveSourceCount,
		ActiveWatchCount:  e.ActiveWatchCount,
		ActiveTaskCount:   e.ActiveTaskCount,
		UpdatedAt:         e.UpdatedAt,
	}
}
