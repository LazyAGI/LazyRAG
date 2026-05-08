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
	baseItems, _, err := s.snapshotItemsForDiffBase(ctx, snapshot.SourceID, snapshot.BaseSnapshotID)
	if err != nil {
		return nil, err
	}
	return diffSnapshotMaps(baseItems, currentItems), nil
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

func (s *Store) snapshotItemsForDiffBase(ctx context.Context, sourceID, baseSnapshotID string) (map[string]sourceFileSnapshotItemEntity, string, error) {
	sourceID = strings.TrimSpace(sourceID)
	baseSnapshotID = strings.TrimSpace(baseSnapshotID)
	baseItems, err := s.snapshotItemsByPath(ctx, baseSnapshotID)
	if err != nil {
		return nil, "", err
	}
	if baseSnapshotID == "" || len(baseItems) > 0 {
		return baseItems, baseSnapshotID, nil
	}

	var baseSnapshot sourceFileSnapshotEntity
	err = s.db.WithContext(ctx).
		Select("snapshot_id", "file_count").
		Take(&baseSnapshot, "snapshot_id = ? AND source_id = ?", baseSnapshotID, sourceID).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return baseItems, baseSnapshotID, nil
		}
		return nil, "", err
	}
	if baseSnapshot.FileCount == 0 {
		return baseItems, baseSnapshotID, nil
	}

	// Older snapshot_source ACKs could point the committed relation at metadata-only snapshots.
	// Diff must use a committed snapshot that actually has item rows.
	fallbackID, err := s.latestCommittedSnapshotWithItems(ctx, sourceID)
	if err != nil {
		return nil, "", err
	}
	if fallbackID == "" {
		return baseItems, baseSnapshotID, nil
	}
	fallbackItems, err := s.snapshotItemsByPath(ctx, fallbackID)
	if err != nil {
		return nil, "", err
	}
	return fallbackItems, fallbackID, nil
}

func (s *Store) latestCommittedSnapshotWithItems(ctx context.Context, sourceID string) (string, error) {
	var snap sourceFileSnapshotEntity
	err := s.db.WithContext(ctx).
		Where("source_id = ? AND snapshot_type = ?", strings.TrimSpace(sourceID), "COMMITTED").
		Where("EXISTS (SELECT 1 FROM source_file_snapshot_items WHERE source_file_snapshot_items.snapshot_id = source_file_snapshots.snapshot_id)").
		Order("created_at DESC").
		Take(&snap).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return "", nil
		}
		return "", err
	}
	return strings.TrimSpace(snap.SnapshotID), nil
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
