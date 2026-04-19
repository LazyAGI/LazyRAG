package store

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"gorm.io/gorm"
	"gorm.io/gorm/clause"
)

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
