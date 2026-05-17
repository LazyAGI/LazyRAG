package store

import (
	"context"
	"errors"
	"fmt"
	"sort"
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

func (s *Store) snapshotItemsForDiffBase(ctx context.Context, sourceID, baseSnapshotID string) (map[string]sourceFileSnapshotItemEntity, string, error) {
	return s.snapshotItemsForDiffBaseDB(s.db.WithContext(ctx), sourceID, baseSnapshotID)
}

func (s *Store) snapshotItemsForDiffBaseDB(db *gorm.DB, sourceID, baseSnapshotID string) (map[string]sourceFileSnapshotItemEntity, string, error) {
	sourceID = strings.TrimSpace(sourceID)
	baseSnapshotID = strings.TrimSpace(baseSnapshotID)
	baseItems, err := s.snapshotItemsByPathDB(db, baseSnapshotID)
	if err != nil {
		return nil, "", err
	}
	if baseSnapshotID == "" || len(baseItems) > 0 {
		return baseItems, baseSnapshotID, nil
	}

	var baseSnapshot sourceFileSnapshotEntity
	err = db.
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
	fallbackID, err := s.latestCommittedSnapshotWithItemsDB(db, sourceID)
	if err != nil {
		return nil, "", err
	}
	if fallbackID == "" {
		return baseItems, baseSnapshotID, nil
	}
	fallbackItems, err := s.snapshotItemsByPathDB(db, fallbackID)
	if err != nil {
		return nil, "", err
	}
	return fallbackItems, fallbackID, nil
}

func (s *Store) latestCommittedSnapshotWithItems(ctx context.Context, sourceID string) (string, error) {
	return s.latestCommittedSnapshotWithItemsDB(s.db.WithContext(ctx), sourceID)
}

func (s *Store) latestCommittedSnapshotWithItemsDB(db *gorm.DB, sourceID string) (string, error) {
	var snap sourceFileSnapshotEntity
	err := db.
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

func (s *Store) snapshotItemsByPathDB(db *gorm.DB, snapshotID string) (map[string]sourceFileSnapshotItemEntity, error) {
	itemsMap := make(map[string]sourceFileSnapshotItemEntity)
	snapshotID = strings.TrimSpace(snapshotID)
	if snapshotID == "" {
		return itemsMap, nil
	}
	var items []sourceFileSnapshotItemEntity
	if err := db.Where("snapshot_id = ?", snapshotID).Find(&items).Error; err != nil {
		return nil, err
	}
	for _, item := range items {
		itemsMap[item.Path] = item
	}
	return itemsMap, nil
}

func (s *Store) createResidualPreviewFromSelectionTx(tx *gorm.DB, sourceID string, preview sourceFileSnapshotEntity, baseSnapshotID string, now time.Time) error {
	sourceID = strings.TrimSpace(sourceID)
	previewID := strings.TrimSpace(preview.SnapshotID)
	if sourceID == "" || previewID == "" {
		return nil
	}
	baseItems, _, err := s.snapshotItemsForDiffBaseDB(tx, sourceID, baseSnapshotID)
	if err != nil {
		return err
	}
	previewItems, err := s.snapshotItemsByPathDB(tx, previewID)
	if err != nil {
		return err
	}
	diff := diffSnapshotMaps(baseItems, previewItems)
	hasResidualUpdate := false
	for _, update := range diff {
		switch normalizeSnapshotUpdateType(update) {
		case "NEW", "MODIFIED", "DELETED":
			hasResidualUpdate = true
		}
		if hasResidualUpdate {
			break
		}
	}
	if !hasResidualUpdate {
		return nil
	}

	residualID := sourceSnapshotID()
	expiresAt := now.UTC().Add(selectionTokenTTL)
	residual := sourceFileSnapshotEntity{
		SnapshotID:     residualID,
		SourceID:       sourceID,
		TenantID:       preview.TenantID,
		SnapshotType:   "PREVIEW",
		BaseSnapshotID: baseSnapshotID,
		ExpiresAt:      &expiresAt,
		FileCount:      int64(len(previewItems)),
		CreatedAt:      now.UTC(),
	}
	if err := tx.Create(&residual).Error; err != nil {
		return err
	}
	if err := createSnapshotItemsTx(tx, residualID, previewItems); err != nil {
		return err
	}
	return tx.Clauses(clause.OnConflict{
		Columns: []clause.Column{{Name: "source_id"}},
		DoUpdates: clause.Assignments(map[string]any{
			"last_preview_snapshot_id": residualID,
			"updated_at":               now.UTC(),
		}),
	}).Create(&sourceSnapshotRelationEntity{
		SourceID:              sourceID,
		LastPreviewSnapshotID: residualID,
		UpdatedAt:             now.UTC(),
	}).Error
}

func createSnapshotItemsTx(tx *gorm.DB, snapshotID string, items map[string]sourceFileSnapshotItemEntity) error {
	if len(items) == 0 {
		return nil
	}
	paths := make([]string, 0, len(items))
	for path := range items {
		paths = append(paths, path)
	}
	sort.Strings(paths)
	rows := make([]sourceFileSnapshotItemEntity, 0, len(paths))
	for _, path := range paths {
		item := items[path]
		item.ID = 0
		item.SnapshotID = snapshotID
		rows = append(rows, item)
	}
	return tx.Create(&rows).Error
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
