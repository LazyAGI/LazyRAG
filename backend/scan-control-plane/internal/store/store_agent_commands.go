package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.uber.org/zap"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"github.com/lazyrag/scan_control_plane/internal/model"
)

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
			ids = append(ids, item.ID)
			resp.Commands = append(resp.Commands, pulled)
		}
		if len(resp.Commands) > 0 {
			s.log.Info("dispatching commands to agent",
				zap.String("agent_id", req.AgentID),
				zap.Int("count", len(resp.Commands)),
			)
		}
		if len(ids) == 0 {
			return nil
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
