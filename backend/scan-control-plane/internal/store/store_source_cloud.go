package store

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"time"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"github.com/lazyrag/scan_control_plane/internal/model"
)

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

func (s *Store) UpsertCloudSourceBinding(ctx context.Context, sourceID string, req model.UpsertCloudSourceBindingRequest) (model.CloudSourceBinding, error) {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" {
		return model.CloudSourceBinding{}, fmt.Errorf("source_id is required")
	}
	var src sourceEntity
	if err := s.db.WithContext(ctx).Take(&src, "id = ?", sourceID).Error; err != nil {
		return model.CloudSourceBinding{}, err
	}

	now := time.Now().UTC()
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var existing cloudSourceBindingEntity
		found := true
		if err := tx.Take(&existing, "source_id = ?", sourceID).Error; err != nil {
			if !errors.Is(err, gorm.ErrRecordNotFound) {
				return err
			}
			found = false
			existing = cloudSourceBindingEntity{
				SourceID:  sourceID,
				TenantID:  src.TenantID,
				CreatedAt: now,
			}
		}

		provider := strings.ToLower(strings.TrimSpace(req.Provider))
		if provider == "" {
			provider = strings.ToLower(strings.TrimSpace(existing.Provider))
		}
		if provider == "" {
			return fmt.Errorf("provider is required")
		}

		authConnectionID := strings.TrimSpace(req.AuthConnectionID)
		if authConnectionID == "" {
			authConnectionID = strings.TrimSpace(existing.AuthConnectionID)
		}
		if authConnectionID == "" {
			return fmt.Errorf("auth_connection_id is required")
		}

		enabled := true
		if found {
			enabled = existing.Enabled
		}
		if req.Enabled != nil {
			enabled = *req.Enabled
		}

		reconcileAfterSync := true
		if found {
			reconcileAfterSync = existing.ReconcileAfterSync
		}
		if req.ReconcileAfterSync != nil {
			reconcileAfterSync = *req.ReconcileAfterSync
		}

		reconcileDelayMinutes := req.ReconcileDelayMinutes
		if reconcileDelayMinutes <= 0 {
			if found && existing.ReconcileDelayMinutes > 0 {
				reconcileDelayMinutes = existing.ReconcileDelayMinutes
			} else {
				reconcileDelayMinutes = 10
			}
		}

		scheduleExpr := strings.TrimSpace(req.ScheduleExpr)
		if scheduleExpr == "" {
			scheduleExpr = strings.TrimSpace(existing.ScheduleExpr)
		}
		if scheduleExpr == "" {
			scheduleExpr = "daily@02:00"
		}
		if _, _, _, err := parseReconcileScheduleExpr(scheduleExpr); err != nil {
			return fmt.Errorf("invalid schedule_expr: %w", err)
		}
		scheduleTZ := strings.TrimSpace(req.ScheduleTZ)
		if scheduleTZ == "" {
			scheduleTZ = strings.TrimSpace(existing.ScheduleTZ)
		}
		if scheduleTZ == "" {
			scheduleTZ = strings.TrimSpace(s.defaultScheduleTZ)
			if scheduleTZ == "" {
				scheduleTZ = defaultScheduleTZ
			}
		}

		targetType := strings.TrimSpace(req.TargetType)
		if targetType == "" {
			targetType = strings.TrimSpace(existing.TargetType)
		}
		targetRef := strings.TrimSpace(req.TargetRef)
		if targetRef == "" {
			targetRef = strings.TrimSpace(existing.TargetRef)
		}

		includePatterns := decodeStringSliceJSON(existing.IncludePatternsJSON)
		if req.IncludePatterns != nil {
			includePatterns = normalizePatterns(req.IncludePatterns)
		}
		excludePatterns := decodeStringSliceJSON(existing.ExcludePatternsJSON)
		if req.ExcludePatterns != nil {
			excludePatterns = normalizePatterns(req.ExcludePatterns)
		}

		providerOptions := decodeMapJSON(existing.ProviderOptionsJSON)
		if req.ProviderOptions != nil {
			providerOptions = req.ProviderOptions
		}

		maxObjectSizeBytes := req.MaxObjectSizeBytes
		if maxObjectSizeBytes <= 0 {
			if found && existing.MaxObjectSizeBytes > 0 {
				maxObjectSizeBytes = existing.MaxObjectSizeBytes
			} else {
				maxObjectSizeBytes = 200 * 1024 * 1024
			}
		}

		status := "ACTIVE"
		if !enabled {
			status = "PAUSED"
		}

		existing.TenantID = src.TenantID
		existing.Provider = provider
		existing.Enabled = enabled
		existing.Status = status
		existing.AuthConnectionID = authConnectionID
		existing.TargetType = targetType
		existing.TargetRef = targetRef
		existing.ScheduleExpr = scheduleExpr
		existing.ScheduleTZ = scheduleTZ
		existing.ReconcileAfterSync = reconcileAfterSync
		existing.ReconcileDelayMinutes = reconcileDelayMinutes
		existing.IncludePatternsJSON = encodeJSON(includePatterns)
		existing.ExcludePatternsJSON = encodeJSON(excludePatterns)
		existing.MaxObjectSizeBytes = maxObjectSizeBytes
		existing.ProviderOptionsJSON = encodeJSON(providerOptions)
		existing.LastError = ""
		existing.UpdatedAt = now

		if found {
			if err := tx.Save(&existing).Error; err != nil {
				return err
			}
		} else {
			if err := tx.Create(&existing).Error; err != nil {
				return err
			}
		}

		nextSyncAt := s.computeNextSyncAt(scheduleExpr, scheduleTZ, now)
		if !enabled {
			nextSyncAt = nil
		}
		var checkpoint cloudSyncCheckpointEntity
		if err := tx.Take(&checkpoint, "source_id = ?", sourceID).Error; err != nil {
			if !errors.Is(err, gorm.ErrRecordNotFound) {
				return err
			}
			checkpoint = cloudSyncCheckpointEntity{
				SourceID:   sourceID,
				Provider:   provider,
				NextSyncAt: nextSyncAt,
				UpdatedAt:  now,
			}
			return tx.Create(&checkpoint).Error
		}
		checkpoint.Provider = provider
		checkpoint.NextSyncAt = nextSyncAt
		checkpoint.UpdatedAt = now
		return tx.Save(&checkpoint).Error
	})
	if err != nil {
		return model.CloudSourceBinding{}, err
	}
	return s.GetCloudSourceBinding(ctx, sourceID)
}

func (s *Store) GetCloudSourceBinding(ctx context.Context, sourceID string) (model.CloudSourceBinding, error) {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" {
		return model.CloudSourceBinding{}, fmt.Errorf("source_id is required")
	}
	var binding cloudSourceBindingEntity
	if err := s.db.WithContext(ctx).Take(&binding, "source_id = ?", sourceID).Error; err != nil {
		return model.CloudSourceBinding{}, err
	}
	var checkpoint cloudSyncCheckpointEntity
	var nextSyncAt *time.Time
	if err := s.db.WithContext(ctx).Take(&checkpoint, "source_id = ?", sourceID).Error; err == nil {
		nextSyncAt = checkpoint.NextSyncAt
	}
	return toModelCloudSourceBinding(binding, nextSyncAt), nil
}

func (s *Store) TriggerCloudSync(ctx context.Context, sourceID string, req model.TriggerCloudSyncRequest) (model.CloudSyncRun, error) {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" {
		return model.CloudSyncRun{}, fmt.Errorf("source_id is required")
	}
	var src sourceEntity
	if err := s.db.WithContext(ctx).Take(&src, "id = ?", sourceID).Error; err != nil {
		return model.CloudSyncRun{}, err
	}
	var binding cloudSourceBindingEntity
	if err := s.db.WithContext(ctx).Take(&binding, "source_id = ?", sourceID).Error; err != nil {
		return model.CloudSyncRun{}, err
	}
	if !binding.Enabled || !strings.EqualFold(strings.TrimSpace(binding.Status), "ACTIVE") {
		return model.CloudSyncRun{}, fmt.Errorf("cloud binding is disabled")
	}

	triggerType := strings.ToLower(strings.TrimSpace(req.TriggerType))
	if triggerType == "" {
		triggerType = "manual"
	}
	switch triggerType {
	case "scheduled", "manual", "retry":
	default:
		return model.CloudSyncRun{}, fmt.Errorf("trigger_type must be one of scheduled/manual/retry")
	}

	now := time.Now().UTC()
	run := cloudSyncRunEntity{
		RunID:       cloudSyncRunID(),
		SourceID:    sourceID,
		TenantID:    src.TenantID,
		Provider:    binding.Provider,
		TriggerType: triggerType,
		Status:      "RUNNING",
		StartedAt:   &now,
		CreatedAt:   now,
		UpdatedAt:   now,
	}

	if err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(&run).Error; err != nil {
			return err
		}
		var checkpoint cloudSyncCheckpointEntity
		if err := tx.Take(&checkpoint, "source_id = ?", sourceID).Error; err != nil {
			if !errors.Is(err, gorm.ErrRecordNotFound) {
				return err
			}
			nextSyncAt := s.computeNextSyncAt(binding.ScheduleExpr, binding.ScheduleTZ, now)
			if triggerType == "manual" || triggerType == "retry" {
				nextSyncAt = &now
			}
			if !binding.Enabled && triggerType == "scheduled" {
				nextSyncAt = nil
			}
			checkpoint = cloudSyncCheckpointEntity{
				SourceID:   sourceID,
				Provider:   binding.Provider,
				NextSyncAt: nextSyncAt,
				LastRunID:  run.RunID,
				UpdatedAt:  now,
			}
			return tx.Create(&checkpoint).Error
		}
		checkpoint.Provider = binding.Provider
		checkpoint.LastRunID = run.RunID
		nextSyncAt := s.computeNextSyncAt(binding.ScheduleExpr, binding.ScheduleTZ, now)
		if triggerType == "manual" || triggerType == "retry" {
			nextSyncAt = &now
		}
		if !binding.Enabled && triggerType == "scheduled" {
			nextSyncAt = nil
		}
		checkpoint.NextSyncAt = nextSyncAt
		checkpoint.UpdatedAt = now
		return tx.Save(&checkpoint).Error
	}); err != nil {
		return model.CloudSyncRun{}, err
	}
	return toModelCloudSyncRun(run), nil
}

func (s *Store) ListCloudSyncRuns(ctx context.Context, sourceID string, limit int) ([]model.CloudSyncRun, error) {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" {
		return nil, fmt.Errorf("source_id is required")
	}
	if limit <= 0 {
		limit = 20
	}
	if limit > 200 {
		limit = 200
	}
	var src sourceEntity
	if err := s.db.WithContext(ctx).Take(&src, "id = ?", sourceID).Error; err != nil {
		return nil, err
	}
	var runs []cloudSyncRunEntity
	if err := s.db.WithContext(ctx).
		Where("source_id = ?", sourceID).
		Order("started_at DESC, created_at DESC").
		Limit(limit).
		Find(&runs).Error; err != nil {
		return nil, err
	}
	result := make([]model.CloudSyncRun, 0, len(runs))
	for _, item := range runs {
		result = append(result, toModelCloudSyncRun(item))
	}
	return result, nil
}

func (s *Store) ClaimDueCloudSources(ctx context.Context, lockOwner string, now time.Time, limit int, lockTTL time.Duration) ([]CloudSyncClaim, error) {
	lockOwner = strings.TrimSpace(lockOwner)
	if lockOwner == "" {
		return nil, fmt.Errorf("lock_owner is required")
	}
	if limit <= 0 {
		limit = 1
	}
	if lockTTL <= 0 {
		lockTTL = 5 * time.Minute
	}
	now = now.UTC()
	lockUntil := now.Add(lockTTL)
	claims := make([]CloudSyncClaim, 0, limit)
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var rows []cloudSyncClaimRow
		if err := tx.Table("cloud_source_bindings b").
			Select(`
				b.source_id AS source_id,
				b.tenant_id AS tenant_id,
				s.root_path AS root_path,
				b.provider AS provider,
				b.auth_connection_id AS auth_connection_id,
				b.target_type AS target_type,
				b.target_ref AS target_ref,
				b.schedule_expr AS schedule_expr,
				b.schedule_tz AS schedule_tz,
				b.reconcile_after_sync AS reconcile_after_sync,
				b.reconcile_delay_minutes AS reconcile_delay_minutes,
				b.include_patterns_json AS include_patterns_json,
				b.exclude_patterns_json AS exclude_patterns_json,
				b.max_object_size_bytes AS max_object_size_bytes,
				b.provider_options_json AS provider_options_json,
				c.last_run_id AS last_run_id
			`).
			Joins("JOIN sources s ON s.id = b.source_id").
			Joins("JOIN cloud_sync_checkpoints c ON c.source_id = b.source_id").
			Where("b.enabled = ? AND b.status = ?", true, "ACTIVE").
			Where("c.next_sync_at IS NOT NULL AND c.next_sync_at <= ?", now).
			Where("(c.lock_until IS NULL OR c.lock_until <= ?)", now).
			Order("c.next_sync_at ASC").
			Limit(limit).
			Scan(&rows).Error; err != nil {
			return err
		}
		for _, row := range rows {
			res := tx.Model(&cloudSyncCheckpointEntity{}).
				Where("source_id = ? AND (lock_until IS NULL OR lock_until <= ?)", row.SourceID, now).
				Updates(map[string]any{
					"lock_owner": lockOwner,
					"lock_until": &lockUntil,
					"updated_at": now,
				})
			if res.Error != nil {
				return res.Error
			}
			if res.RowsAffected == 0 {
				continue
			}
			claim := toCloudSyncClaim(row)
			if strings.TrimSpace(row.LastRunID) != "" {
				var run cloudSyncRunEntity
				if err := tx.Take(&run, "run_id = ? AND source_id = ?", strings.TrimSpace(row.LastRunID), row.SourceID).Error; err == nil {
					if strings.EqualFold(strings.TrimSpace(run.Status), "RUNNING") && run.FinishedAt == nil {
						claim.ExistingRunID = run.RunID
					}
				}
			}
			claims = append(claims, claim)
		}
		return nil
	})
	return claims, err
}

func (s *Store) ClaimCloudSourceByID(ctx context.Context, sourceID, lockOwner string, now time.Time, lockTTL time.Duration) (CloudSyncClaim, error) {
	sourceID = strings.TrimSpace(sourceID)
	lockOwner = strings.TrimSpace(lockOwner)
	if sourceID == "" {
		return CloudSyncClaim{}, fmt.Errorf("source_id is required")
	}
	if lockOwner == "" {
		return CloudSyncClaim{}, fmt.Errorf("lock_owner is required")
	}
	if lockTTL <= 0 {
		lockTTL = 5 * time.Minute
	}
	now = now.UTC()
	lockUntil := now.Add(lockTTL)

	var out CloudSyncClaim
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var row cloudSyncClaimRow
		if err := tx.Table("cloud_source_bindings b").
			Select(`
				b.source_id AS source_id,
				b.tenant_id AS tenant_id,
				s.root_path AS root_path,
				b.provider AS provider,
				b.auth_connection_id AS auth_connection_id,
				b.target_type AS target_type,
				b.target_ref AS target_ref,
				b.schedule_expr AS schedule_expr,
				b.schedule_tz AS schedule_tz,
				b.reconcile_after_sync AS reconcile_after_sync,
				b.reconcile_delay_minutes AS reconcile_delay_minutes,
				b.include_patterns_json AS include_patterns_json,
				b.exclude_patterns_json AS exclude_patterns_json,
				b.max_object_size_bytes AS max_object_size_bytes,
				b.provider_options_json AS provider_options_json
			`).
			Joins("JOIN sources s ON s.id = b.source_id").
			Where("b.source_id = ?", sourceID).
			Take(&row).Error; err != nil {
			return err
		}

		var checkpoint cloudSyncCheckpointEntity
		if err := tx.Take(&checkpoint, "source_id = ?", sourceID).Error; err != nil {
			if !errors.Is(err, gorm.ErrRecordNotFound) {
				return err
			}
			checkpoint = cloudSyncCheckpointEntity{
				SourceID:   sourceID,
				Provider:   row.Provider,
				NextSyncAt: &now,
				UpdatedAt:  now,
			}
			if err := tx.Create(&checkpoint).Error; err != nil {
				return err
			}
		}
		if checkpoint.LockUntil != nil && checkpoint.LockUntil.UTC().After(now) {
			return ErrCloudSyncLocked
		}
		res := tx.Model(&cloudSyncCheckpointEntity{}).
			Where("source_id = ? AND (lock_until IS NULL OR lock_until <= ?)", sourceID, now).
			Updates(map[string]any{
				"provider":     row.Provider,
				"next_sync_at": &now,
				"lock_owner":   lockOwner,
				"lock_until":   &lockUntil,
				"updated_at":   now,
			})
		if res.Error != nil {
			return res.Error
		}
		if res.RowsAffected == 0 {
			return ErrCloudSyncLocked
		}

		row.LastRunID = strings.TrimSpace(checkpoint.LastRunID)
		out = toCloudSyncClaim(row)
		if row.LastRunID != "" {
			var run cloudSyncRunEntity
			if err := tx.Take(&run, "run_id = ? AND source_id = ?", row.LastRunID, sourceID).Error; err == nil {
				if strings.EqualFold(strings.TrimSpace(run.Status), "RUNNING") && run.FinishedAt == nil {
					out.ExistingRunID = run.RunID
				}
			}
		}
		return nil
	})
	return out, err
}

func (s *Store) ReleaseCloudSyncLock(ctx context.Context, sourceID string, now time.Time) error {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" {
		return fmt.Errorf("source_id is required")
	}
	now = now.UTC()
	return s.db.WithContext(ctx).Model(&cloudSyncCheckpointEntity{}).
		Where("source_id = ?", sourceID).
		Updates(map[string]any{
			"lock_owner": "",
			"lock_until": nil,
			"updated_at": now,
		}).Error
}

func (s *Store) StartCloudSyncRun(ctx context.Context, sourceID, triggerType, requestedRunID string, startedAt time.Time) (model.CloudSyncRun, error) {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" {
		return model.CloudSyncRun{}, fmt.Errorf("source_id is required")
	}
	triggerType = strings.ToLower(strings.TrimSpace(triggerType))
	if triggerType == "" {
		triggerType = "scheduled"
	}
	startedAt = startedAt.UTC()
	if startedAt.IsZero() {
		startedAt = time.Now().UTC()
	}
	var src sourceEntity
	if err := s.db.WithContext(ctx).Take(&src, "id = ?", sourceID).Error; err != nil {
		return model.CloudSyncRun{}, err
	}
	var binding cloudSourceBindingEntity
	if err := s.db.WithContext(ctx).Take(&binding, "source_id = ?", sourceID).Error; err != nil {
		return model.CloudSyncRun{}, err
	}

	runID := strings.TrimSpace(requestedRunID)
	if runID == "" {
		runID = cloudSyncRunID()
	}
	now := time.Now().UTC()
	run := cloudSyncRunEntity{}
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Take(&run, "run_id = ? AND source_id = ?", runID, sourceID).Error; err != nil {
			if !errors.Is(err, gorm.ErrRecordNotFound) {
				return err
			}
			run = cloudSyncRunEntity{
				RunID:       runID,
				SourceID:    sourceID,
				TenantID:    src.TenantID,
				Provider:    binding.Provider,
				TriggerType: triggerType,
				Status:      "RUNNING",
				StartedAt:   &startedAt,
				CreatedAt:   now,
				UpdatedAt:   now,
			}
			return tx.Create(&run).Error
		}
		run.SourceID = sourceID
		run.TenantID = src.TenantID
		run.Provider = binding.Provider
		run.TriggerType = triggerType
		run.Status = "RUNNING"
		if run.StartedAt == nil || run.StartedAt.IsZero() {
			run.StartedAt = &startedAt
		}
		run.FinishedAt = nil
		run.UpdatedAt = now
		return tx.Save(&run).Error
	})
	if err != nil {
		return model.CloudSyncRun{}, err
	}
	return toModelCloudSyncRun(run), nil
}

func (s *Store) FinishCloudSyncRun(ctx context.Context, sourceID string, finalize CloudSyncRunFinalize) error {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" {
		return fmt.Errorf("source_id is required")
	}
	runID := strings.TrimSpace(finalize.RunID)
	if runID == "" {
		return fmt.Errorf("run_id is required")
	}
	status := strings.ToUpper(strings.TrimSpace(finalize.Status))
	if status == "" {
		status = "FAILED"
	}
	finishedAt := finalize.FinishedAt.UTC()
	if finishedAt.IsZero() {
		finishedAt = time.Now().UTC()
	}
	now := time.Now().UTC()
	return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var run cloudSyncRunEntity
		if err := tx.Take(&run, "run_id = ? AND source_id = ?", runID, sourceID).Error; err != nil {
			return err
		}
		run.Status = status
		run.FinishedAt = &finishedAt
		run.RemoteTotal = max(0, finalize.RemoteTotal)
		run.CreatedCount = max(0, finalize.CreatedCount)
		run.UpdatedCount = max(0, finalize.UpdatedCount)
		run.DeletedCount = max(0, finalize.DeletedCount)
		run.SkippedCount = max(0, finalize.SkippedCount)
		run.FailedCount = max(0, finalize.FailedCount)
		run.ErrorCode = strings.TrimSpace(finalize.ErrorCode)
		run.ErrorMessage = strings.TrimSpace(finalize.ErrorMessage)
		run.UpdatedAt = now
		if err := tx.Save(&run).Error; err != nil {
			return err
		}

		var binding cloudSourceBindingEntity
		if err := tx.Take(&binding, "source_id = ?", sourceID).Error; err != nil {
			return err
		}
		nextSyncAt := s.computeNextSyncAt(binding.ScheduleExpr, binding.ScheduleTZ, finishedAt)
		if !binding.Enabled {
			nextSyncAt = nil
		}

		checkpointUpdates := map[string]any{
			"provider":     binding.Provider,
			"next_sync_at": nextSyncAt,
			"last_sync_at": &finishedAt,
			"last_run_id":  runID,
			"lock_owner":   "",
			"lock_until":   nil,
			"updated_at":   now,
		}
		if status == "SUCCEEDED" {
			checkpointUpdates["last_success_at"] = &finishedAt
		}
		if err := tx.Model(&cloudSyncCheckpointEntity{}).
			Where("source_id = ?", sourceID).
			Updates(checkpointUpdates).Error; err != nil {
			return err
		}

		lastError := ""
		if status == "FAILED" || status == "PARTIAL_SUCCESS" {
			lastError = strings.TrimSpace(finalize.ErrorMessage)
		}
		return tx.Model(&cloudSourceBindingEntity{}).
			Where("source_id = ?", sourceID).
			Updates(map[string]any{
				"last_error": lastError,
				"updated_at": now,
			}).Error
	})
}

func (s *Store) ListCloudObjectIndex(ctx context.Context, sourceID string) ([]CloudObjectIndexRecord, error) {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" {
		return nil, fmt.Errorf("source_id is required")
	}
	var rows []cloudObjectIndexEntity
	if err := s.db.WithContext(ctx).Where("source_id = ?", sourceID).Find(&rows).Error; err != nil {
		return nil, err
	}
	out := make([]CloudObjectIndexRecord, 0, len(rows))
	for _, row := range rows {
		out = append(out, CloudObjectIndexRecord{
			SourceID:           row.SourceID,
			Provider:           row.Provider,
			ExternalObjectID:   row.ExternalObjectID,
			ExternalParentID:   row.ExternalParentID,
			ExternalPath:       row.ExternalPath,
			ExternalName:       row.ExternalName,
			ExternalKind:       row.ExternalKind,
			ExternalVersion:    row.ExternalVersion,
			ExternalModifiedAt: row.ExternalModifiedAt,
			LocalRelPath:       row.LocalRelPath,
			LocalAbsPath:       row.LocalAbsPath,
			Checksum:           row.Checksum,
			SizeBytes:          row.SizeBytes,
			IsDeleted:          row.IsDeleted,
			LastSyncedAt:       row.LastSyncedAt,
			ProviderMeta:       decodeMapJSON(row.ProviderMetaJSON),
		})
	}
	return out, nil
}

func (s *Store) UpsertCloudObjectIndexBatch(ctx context.Context, sourceID, provider string, records []CloudObjectIndexRecord, now time.Time) error {
	sourceID = strings.TrimSpace(sourceID)
	provider = strings.ToLower(strings.TrimSpace(provider))
	if sourceID == "" {
		return fmt.Errorf("source_id is required")
	}
	if provider == "" {
		return fmt.Errorf("provider is required")
	}
	if len(records) == 0 {
		return nil
	}
	now = now.UTC()
	rows := make([]cloudObjectIndexEntity, 0, len(records))
	for _, rec := range records {
		extID := strings.TrimSpace(rec.ExternalObjectID)
		if extID == "" {
			continue
		}
		rows = append(rows, cloudObjectIndexEntity{
			SourceID:           sourceID,
			Provider:           provider,
			ExternalObjectID:   extID,
			ExternalParentID:   strings.TrimSpace(rec.ExternalParentID),
			ExternalPath:       strings.TrimSpace(rec.ExternalPath),
			ExternalName:       strings.TrimSpace(rec.ExternalName),
			ExternalKind:       strings.TrimSpace(rec.ExternalKind),
			ExternalVersion:    strings.TrimSpace(rec.ExternalVersion),
			ExternalModifiedAt: rec.ExternalModifiedAt,
			LocalRelPath:       strings.TrimSpace(rec.LocalRelPath),
			LocalAbsPath:       strings.TrimSpace(rec.LocalAbsPath),
			Checksum:           strings.TrimSpace(rec.Checksum),
			SizeBytes:          rec.SizeBytes,
			IsDeleted:          false,
			LastSyncedAt:       &now,
			ProviderMetaJSON:   encodeJSON(rec.ProviderMeta),
			CreatedAt:          now,
			UpdatedAt:          now,
		})
	}
	if len(rows) == 0 {
		return nil
	}
	return s.db.WithContext(ctx).Clauses(clause.OnConflict{
		Columns: []clause.Column{
			{Name: "source_id"},
			{Name: "external_object_id"},
		},
		DoUpdates: clause.Assignments(map[string]any{
			"provider":             gorm.Expr("excluded.provider"),
			"external_parent_id":   gorm.Expr("excluded.external_parent_id"),
			"external_path":        gorm.Expr("excluded.external_path"),
			"external_name":        gorm.Expr("excluded.external_name"),
			"external_kind":        gorm.Expr("excluded.external_kind"),
			"external_version":     gorm.Expr("excluded.external_version"),
			"external_modified_at": gorm.Expr("excluded.external_modified_at"),
			"local_rel_path":       gorm.Expr("excluded.local_rel_path"),
			"local_abs_path":       gorm.Expr("excluded.local_abs_path"),
			"checksum":             gorm.Expr("excluded.checksum"),
			"size_bytes":           gorm.Expr("excluded.size_bytes"),
			"is_deleted":           false,
			"last_synced_at":       gorm.Expr("excluded.last_synced_at"),
			"provider_meta_json":   gorm.Expr("excluded.provider_meta_json"),
			"updated_at":           gorm.Expr("excluded.updated_at"),
		}),
	}).Create(&rows).Error
}

func (s *Store) MarkCloudObjectsDeleted(ctx context.Context, sourceID string, externalObjectIDs []string, now time.Time) error {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" || len(externalObjectIDs) == 0 {
		return nil
	}
	filtered := make([]string, 0, len(externalObjectIDs))
	seen := make(map[string]struct{}, len(externalObjectIDs))
	for _, raw := range externalObjectIDs {
		id := strings.TrimSpace(raw)
		if id == "" {
			continue
		}
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		filtered = append(filtered, id)
	}
	if len(filtered) == 0 {
		return nil
	}
	now = now.UTC()
	return s.db.WithContext(ctx).Model(&cloudObjectIndexEntity{}).
		Where("source_id = ? AND external_object_id IN ?", sourceID, filtered).
		Updates(map[string]any{
			"is_deleted":     true,
			"last_synced_at": &now,
			"updated_at":     now,
		}).Error
}

func (s *Store) EmitCloudFileEvents(ctx context.Context, events []model.FileEvent) error {
	mutations, err := s.BuildMutationsFromEvents(ctx, events)
	if err != nil {
		return err
	}
	return s.BatchApplyDocumentMutations(ctx, mutations)
}

func (s *Store) BuildCloudTreeByPath(ctx context.Context, sourceID, path string, maxDepth int, includeFiles bool) ([]model.TreeNode, error) {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" {
		return nil, fmt.Errorf("source_id is required")
	}
	if maxDepth <= 0 {
		maxDepth = 2
	}
	if maxDepth > 8 {
		maxDepth = 8
	}

	var src sourceEntity
	if err := s.db.WithContext(ctx).Take(&src, "id = ?", sourceID).Error; err != nil {
		return nil, err
	}

	rootPath := filepath.Clean(strings.TrimSpace(src.RootPath))
	if rootPath == "" || rootPath == "." {
		return nil, fmt.Errorf("source root_path is empty")
	}
	targetPath := filepath.Clean(strings.TrimSpace(path))
	if targetPath == "" || targetPath == "." {
		targetPath = rootPath
	}
	if !pathInScope(targetPath, []string{rootPath}) {
		return nil, ErrTreePathInvalid
	}

	var rows []cloudObjectIndexEntity
	if err := s.db.WithContext(ctx).
		Where("source_id = ? AND is_deleted = ?", sourceID, false).
		Find(&rows).Error; err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		if targetPath != rootPath {
			return nil, ErrTreePathInvalid
		}
		return []model.TreeNode{}, nil
	}

	nodeMap := make(map[string]*model.TreeNode, len(rows))
	childMap := make(map[string]map[string]struct{}, len(rows))
	hasScopedObject := false
	pathIsFile := false

	for _, row := range rows {
		objectPath := resolveCloudObjectLocalPath(rootPath, row)
		if objectPath == "" {
			continue
		}
		objectPath = filepath.Clean(objectPath)
		if !pathInScope(objectPath, []string{rootPath}) {
			continue
		}

		isDir := cloudObjectIsDirectory(row.ExternalKind)
		if objectPath == targetPath {
			hasScopedObject = true
			if !isDir {
				pathIsFile = true
			} else {
				ensureCloudNode(nodeMap, childMap, objectPath, true, strings.TrimSpace(row.ExternalName), "")
			}
		}

		if !pathInScope(objectPath, []string{targetPath}) {
			continue
		}
		hasScopedObject = true

		depth := treeRelativeDepth(targetPath, objectPath)
		if depth < 0 {
			continue
		}
		if depth > 0 {
			ensureCloudAncestorNodes(nodeMap, childMap, targetPath, objectPath, maxDepth)
		}
		if depth == 0 {
			continue
		}
		if depth > maxDepth {
			continue
		}
		if !isDir && !includeFiles {
			continue
		}
		externalFileID := ""
		if !isDir {
			externalFileID = strings.TrimSpace(row.ExternalObjectID)
		}
		ensureCloudNode(nodeMap, childMap, objectPath, isDir, strings.TrimSpace(row.ExternalName), externalFileID)
	}

	if targetPath != rootPath {
		if !hasScopedObject || pathIsFile {
			return nil, ErrTreePathInvalid
		}
	}
	return buildCloudTreeNodes(targetPath, nodeMap, childMap), nil
}
