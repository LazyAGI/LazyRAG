package store

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"time"

	"go.uber.org/zap"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"github.com/lazymind/scan_control_plane/internal/model"
	"github.com/lazymind/scan_control_plane/internal/sourcelayout"
)

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
		sourceID := strings.TrimSpace(rec.SourceID)
		if sourceID == "" {
			sourceID = strings.TrimSpace(req.SourceID)
		}
		events = append(events, model.FileEvent{
			SourceID:       sourceID,
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
	return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		for _, m := range mutations {
			if err := applyDocumentMutation(tx, m, s.log); err != nil {
				return err
			}
			if err := upsertSourceDocumentStateFromMutationTx(tx, m, s.log); err != nil {
				return err
			}
		}
		return s.persistScanResultSnapshotMetadataTx(tx, req)
	})
}

func (s *Store) PersistScanResultSnapshotMetadata(ctx context.Context, req model.ReportScanResultsRequest) error {
	return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		return s.persistScanResultSnapshotMetadataTx(tx, req)
	})
}

func (s *Store) persistScanResultSnapshotMetadataTx(tx *gorm.DB, req model.ReportScanResultsRequest) error {
	recordsBySource := scanResultSnapshotRecordsBySource(req)
	if len(recordsBySource) == 0 {
		return nil
	}
	for sourceID, records := range recordsBySource {
		if err := s.persistSourceScanResultSnapshotMetadataTx(tx, sourceID, records); err != nil {
			return err
		}
	}
	return nil
}

func scanResultSnapshotRecordsBySource(req model.ReportScanResultsRequest) map[string][]model.ScanRecord {
	fallbackSourceID := strings.TrimSpace(req.SourceID)
	recordsBySource := make(map[string][]model.ScanRecord)
	for _, rec := range req.Records {
		sourceID := strings.TrimSpace(rec.SourceID)
		if sourceID == "" {
			sourceID = fallbackSourceID
		}
		path := filepath.Clean(strings.TrimSpace(rec.Path))
		if sourceID == "" || path == "" || path == "." || rec.IsDir {
			continue
		}
		if isTransientSourceFilePath(path, false) {
			continue
		}
		rec.SourceID = sourceID
		rec.Path = path
		recordsBySource[sourceID] = append(recordsBySource[sourceID], rec)
	}
	return recordsBySource
}

func (s *Store) persistSourceScanResultSnapshotMetadataTx(tx *gorm.DB, sourceID string, records []model.ScanRecord) error {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" || len(records) == 0 {
		return nil
	}

	var src sourceEntity
	if err := tx.Select("id", "tenant_id").Take(&src, "id = ?", sourceID).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil
		}
		return err
	}

	var relation sourceSnapshotRelationEntity
	if err := tx.Take(&relation, "source_id = ?", src.ID).Error; err != nil {
		if !errors.Is(err, gorm.ErrRecordNotFound) {
			return err
		}
		relation = sourceSnapshotRelationEntity{SourceID: src.ID}
	}

	baseItems, baseSnapshotID, err := s.snapshotItemsForDiffBaseDB(tx, src.ID, relation.LastCommittedSnapshotID)
	if err != nil {
		return err
	}
	merged := make(map[string]sourceFileSnapshotItemEntity, len(baseItems)+len(records))
	for path, item := range baseItems {
		merged[path] = item
	}

	changed := false
	for _, rec := range records {
		path := filepath.Clean(strings.TrimSpace(rec.Path))
		if path == "" || path == "." || rec.IsDir || isTransientSourceFilePath(path, false) {
			continue
		}
		size := rec.Size
		if size < 0 {
			size = 0
		}
		item := sourceFileSnapshotItemEntity{
			Path:      path,
			IsDir:     false,
			SizeBytes: size,
			Checksum:  strings.TrimSpace(rec.Checksum),
		}
		if !rec.ModTime.IsZero() {
			mt := rec.ModTime.UTC()
			item.ModTime = &mt
		}
		existing, exists := merged[path]
		if exists {
			if item.ModTime == nil {
				item.ModTime = existing.ModTime
			}
			item.ExternalFileID = existing.ExternalFileID
		}
		if !exists ||
			existing.IsDir != item.IsDir ||
			strings.TrimSpace(existing.Checksum) != strings.TrimSpace(item.Checksum) ||
			existing.ExternalFileID != item.ExternalFileID ||
			snapshotItemChanged(existing, item) {
			changed = true
		}
		merged[path] = item
	}
	if !changed {
		return nil
	}

	now := time.Now().UTC()
	committedID := sourceSnapshotID()
	committed := sourceFileSnapshotEntity{
		SnapshotID:     committedID,
		SourceID:       src.ID,
		TenantID:       src.TenantID,
		SnapshotType:   "COMMITTED",
		BaseSnapshotID: baseSnapshotID,
		FileCount:      int64(len(merged)),
		CreatedAt:      now,
	}
	if err := tx.Create(&committed).Error; err != nil {
		return err
	}
	if err := createSnapshotItemsTx(tx, committedID, merged); err != nil {
		return err
	}
	return tx.Clauses(clause.OnConflict{
		Columns: []clause.Column{{Name: "source_id"}},
		DoUpdates: clause.Assignments(map[string]any{
			"last_committed_snapshot_id": committedID,
			"updated_at":                 now,
		}),
	}).Create(&sourceSnapshotRelationEntity{
		SourceID:                src.ID,
		LastCommittedSnapshotID: committedID,
		UpdatedAt:               now,
	}).Error
}

func (s *Store) commitCloudDocumentSnapshotAfterTaskSucceededTx(tx *gorm.DB, task parseTaskEntity, doc documentEntity, at time.Time, targetVersion string) error {
	var src sourceEntity
	if err := tx.Select("id", "tenant_id", "root_path", "default_origin_type").Take(&src, "id = ?", strings.TrimSpace(doc.SourceID)).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil
		}
		return err
	}
	if !sourcelayout.IsCloudOriginType(src.DefaultOriginType) &&
		!sourcelayout.IsCloudOriginType(task.OriginType) &&
		!sourcelayout.IsCloudOriginType(doc.OriginType) {
		return nil
	}

	path := filepath.Clean(strings.TrimSpace(doc.SourceObjectID))
	if path == "" || path == "." || isTransientSourceFilePath(path, false) {
		return nil
	}

	var relation sourceSnapshotRelationEntity
	if err := tx.Take(&relation, "source_id = ?", src.ID).Error; err != nil {
		if !errors.Is(err, gorm.ErrRecordNotFound) {
			return err
		}
		relation = sourceSnapshotRelationEntity{SourceID: src.ID}
	}
	baseItems, baseSnapshotID, err := s.snapshotItemsForDiffBaseDB(tx, src.ID, relation.LastCommittedSnapshotID)
	if err != nil {
		return err
	}
	merged := make(map[string]sourceFileSnapshotItemEntity, len(baseItems)+1)
	for itemPath, item := range baseItems {
		merged[itemPath] = item
	}

	if normalizeTaskAction(task.TaskAction) == taskActionDelete {
		paths, err := s.cloudDocumentSnapshotEquivalentPathsTx(tx, src, doc)
		if err != nil {
			return err
		}
		changed := false
		for _, itemPath := range paths {
			if _, ok := merged[itemPath]; ok {
				delete(merged, itemPath)
				changed = true
			}
		}
		if !changed {
			return nil
		}
		return s.commitCloudSourceSnapshotItemsTx(tx, src, baseSnapshotID, merged, at)
	}

	item, equivalentPaths, ok, err := s.cloudSnapshotItemForDocumentTx(tx, src, task, doc, at, targetVersion)
	if err != nil {
		return err
	}
	if !ok {
		return nil
	}
	changed := false
	for _, itemPath := range equivalentPaths {
		if itemPath == item.Path {
			continue
		}
		if _, ok := merged[itemPath]; ok {
			delete(merged, itemPath)
			changed = true
		}
	}
	if existing, exists := merged[item.Path]; !exists || !cloudSnapshotItemSame(existing, item) {
		changed = true
	}
	if !changed {
		return nil
	}
	merged[item.Path] = item
	return s.commitCloudSourceSnapshotItemsTx(tx, src, baseSnapshotID, merged, at)
}

func (s *Store) cloudSnapshotItemForDocumentTx(tx *gorm.DB, src sourceEntity, task parseTaskEntity, doc documentEntity, at time.Time, targetVersion string) (sourceFileSnapshotItemEntity, []string, bool, error) {
	path := filepath.Clean(strings.TrimSpace(doc.SourceObjectID))
	if row, ok, err := cloudObjectIndexForDocumentTx(tx, src.ID, doc, true); err != nil {
		return sourceFileSnapshotItemEntity{}, nil, false, err
	} else if ok && !row.IsDeleted {
		item := cloudSnapshotItemFromIndex(src, row, path, targetVersion, doc)
		if item.Path == "" || item.Path == "." || isTransientSourceFilePath(item.Path, false) {
			return sourceFileSnapshotItemEntity{}, nil, false, nil
		}
		return item, cloudSnapshotEquivalentPaths(src, row, path), true, nil
	}

	var state sourceDocumentStateEntity
	stateQuery := tx.Where("document_id = ? OR active_task_id = ?", doc.ID, task.ID)
	if originRef := strings.TrimSpace(doc.OriginRef); originRef != "" {
		stateQuery = stateQuery.Or("source_id = ? AND object_key = ?", src.ID, originRef)
	}
	if path != "" && path != "." {
		stateQuery = stateQuery.Or("source_id = ? AND path = ?", src.ID, path)
	}
	if err := stateQuery.Order("id DESC").Take(&state).Error; err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		return sourceFileSnapshotItemEntity{}, nil, false, err
	} else if err == nil && state.SourceExists {
		itemPath := filepath.Clean(strings.TrimSpace(firstNonEmpty(state.Path, path)))
		if itemPath == "" || itemPath == "." || isTransientSourceFilePath(itemPath, false) {
			return sourceFileSnapshotItemEntity{}, nil, false, nil
		}
		item := sourceFileSnapshotItemEntity{
			Path:           itemPath,
			IsDir:          false,
			SizeBytes:      state.SourceSizeBytes,
			Checksum:       strings.TrimSpace(firstNonEmpty(state.SourceVersion, state.SourceChecksum, targetVersion, doc.CurrentVersionID, doc.DesiredVersionID)),
			ExternalFileID: strings.TrimSpace(state.OriginRef),
		}
		if state.SourceModifiedAt != nil && !state.SourceModifiedAt.IsZero() {
			mt := state.SourceModifiedAt.UTC()
			item.ModTime = &mt
		} else if doc.LastModifiedAt != nil && !doc.LastModifiedAt.IsZero() {
			mt := doc.LastModifiedAt.UTC()
			item.ModTime = &mt
		}
		return item, uniqueCleanSnapshotPaths(path, itemPath), true, nil
	}

	if targetVersion = strings.TrimSpace(firstNonEmpty(targetVersion, doc.CurrentVersionID, doc.DesiredVersionID, task.TargetVersionID)); targetVersion == "" {
		return sourceFileSnapshotItemEntity{}, nil, false, nil
	}
	item := sourceFileSnapshotItemEntity{
		Path:      path,
		IsDir:     false,
		Checksum:  targetVersion,
		SizeBytes: 0,
	}
	if doc.LastModifiedAt != nil && !doc.LastModifiedAt.IsZero() {
		mt := doc.LastModifiedAt.UTC()
		item.ModTime = &mt
	}
	return item, []string{path}, true, nil
}

func (s *Store) cloudDocumentSnapshotEquivalentPathsTx(tx *gorm.DB, src sourceEntity, doc documentEntity) ([]string, error) {
	path := filepath.Clean(strings.TrimSpace(doc.SourceObjectID))
	row, ok, err := cloudObjectIndexForDocumentTx(tx, src.ID, doc, true)
	if err != nil {
		return nil, err
	}
	if !ok {
		return uniqueCleanSnapshotPaths(path), nil
	}
	return cloudSnapshotEquivalentPaths(src, row, path), nil
}

func cloudObjectIndexForDocumentTx(tx *gorm.DB, sourceID string, doc documentEntity, includeDeleted bool) (cloudObjectIndexEntity, bool, error) {
	sourceID = strings.TrimSpace(sourceID)
	path := filepath.Clean(strings.TrimSpace(doc.SourceObjectID))
	originRef := strings.TrimSpace(doc.OriginRef)
	take := func(query *gorm.DB) (cloudObjectIndexEntity, bool, error) {
		if !includeDeleted {
			query = query.Where("is_deleted = ?", false)
		}
		var row cloudObjectIndexEntity
		err := query.Order("id DESC").Take(&row).Error
		if err == nil {
			return row, true, nil
		}
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return cloudObjectIndexEntity{}, false, nil
		}
		return cloudObjectIndexEntity{}, false, err
	}
	if sourceID == "" {
		return cloudObjectIndexEntity{}, false, nil
	}
	if originRef != "" {
		if row, ok, err := take(tx.Where("source_id = ? AND external_object_id = ?", sourceID, originRef)); err != nil || ok {
			return row, ok, err
		}
	}
	if path != "" && path != "." {
		if row, ok, err := take(tx.Where("source_id = ? AND local_abs_path = ?", sourceID, path)); err != nil || ok {
			return row, ok, err
		}
	}
	return cloudObjectIndexEntity{}, false, nil
}

func cloudSnapshotItemFromIndex(src sourceEntity, row cloudObjectIndexEntity, fallbackPath, targetVersion string, doc documentEntity) sourceFileSnapshotItemEntity {
	mirrorRoot := filepath.Clean(sourcelayout.CloudMirrorRoot(src.RootPath))
	path := filepath.Clean(strings.TrimSpace(resolveCloudObjectLocalPath(mirrorRoot, row)))
	if path == "" || path == "." {
		path = filepath.Clean(strings.TrimSpace(fallbackPath))
	}
	item := sourceFileSnapshotItemEntity{
		Path:           path,
		IsDir:          false,
		SizeBytes:      row.SizeBytes,
		Checksum:       strings.TrimSpace(firstNonEmpty(row.ExternalVersion, row.Checksum, targetVersion, doc.CurrentVersionID, doc.DesiredVersionID)),
		ExternalFileID: strings.TrimSpace(row.ExternalObjectID),
	}
	if row.ExternalModifiedAt != nil && !row.ExternalModifiedAt.IsZero() {
		mt := row.ExternalModifiedAt.UTC()
		item.ModTime = &mt
	} else if doc.LastModifiedAt != nil && !doc.LastModifiedAt.IsZero() {
		mt := doc.LastModifiedAt.UTC()
		item.ModTime = &mt
	}
	return item
}

func cloudSnapshotEquivalentPaths(src sourceEntity, row cloudObjectIndexEntity, fallbackPath string) []string {
	mirrorRoot := filepath.Clean(sourcelayout.CloudMirrorRoot(src.RootPath))
	objectPath := filepath.Clean(strings.TrimSpace(resolveCloudObjectLocalPath(mirrorRoot, row)))
	if objectPath == "" || objectPath == "." {
		objectPath = filepath.Clean(strings.TrimSpace(fallbackPath))
	}
	treePath := filepath.Clean(cloudObjectTreePath(objectPath, row))
	return uniqueCleanSnapshotPaths(fallbackPath, objectPath, treePath)
}

func uniqueCleanSnapshotPaths(paths ...string) []string {
	out := make([]string, 0, len(paths))
	seen := make(map[string]struct{}, len(paths))
	for _, rawPath := range paths {
		path := filepath.Clean(strings.TrimSpace(rawPath))
		if path == "" || path == "." {
			continue
		}
		if _, ok := seen[path]; ok {
			continue
		}
		seen[path] = struct{}{}
		out = append(out, path)
	}
	return out
}

func cloudSnapshotItemSame(existing, current sourceFileSnapshotItemEntity) bool {
	return existing.IsDir == current.IsDir &&
		strings.TrimSpace(existing.ExternalFileID) == strings.TrimSpace(current.ExternalFileID) &&
		!snapshotItemChanged(existing, current)
}

func (s *Store) commitCloudSourceSnapshotItemsTx(tx *gorm.DB, src sourceEntity, baseSnapshotID string, items map[string]sourceFileSnapshotItemEntity, at time.Time) error {
	now := at.UTC()
	if now.IsZero() {
		now = time.Now().UTC()
	}
	committedID := sourceSnapshotID()
	committed := sourceFileSnapshotEntity{
		SnapshotID:     committedID,
		SourceID:       src.ID,
		TenantID:       src.TenantID,
		SnapshotType:   "COMMITTED",
		BaseSnapshotID: strings.TrimSpace(baseSnapshotID),
		FileCount:      int64(len(items)),
		CreatedAt:      now,
	}
	if err := tx.Create(&committed).Error; err != nil {
		return err
	}
	if err := createSnapshotItemsTx(tx, committedID, items); err != nil {
		return err
	}
	return tx.Clauses(clause.OnConflict{
		Columns: []clause.Column{{Name: "source_id"}},
		DoUpdates: clause.Assignments(map[string]any{
			"last_committed_snapshot_id": committedID,
			"updated_at":                 now,
		}),
	}).Create(&sourceSnapshotRelationEntity{
		SourceID:                src.ID,
		LastCommittedSnapshotID: committedID,
		UpdatedAt:               now,
	}).Error
}

func (s *Store) BuildMutationsFromEvents(ctx context.Context, events []model.FileEvent) ([]DocumentMutation, error) {
	mutations := make([]DocumentMutation, 0, len(events))
	sourceCache := make(map[string]sourceEntity)
	var (
		skippedIsDir          int
		skippedEmptyPath      int
		skippedTransient      int
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
		if isTransientSourceFilePath(path, false) {
			skippedTransient++
			s.log.Debug("event skipped",
				zap.String("reason", "transient_file"),
				zap.String("source_id", strings.TrimSpace(ev.SourceID)),
				zap.String("path", path),
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

		scheduleAt := automaticMutationScheduleAt(src, occurred)
		if scheduleAt == nil && sourcelayout.IsCloudOriginType(src.DefaultOriginType) {
			scheduleAt = s.cloudSourceMutationScheduleAt(ctx, src.ID, occurred)
		}
		mutations = append(mutations, DocumentMutation{
			TenantID:          src.TenantID,
			SourceID:          src.ID,
			SourceObjectID:    path,
			IdleWindowSeconds: idleSeconds,
			EventType:         normalizeEventType(ev.EventType),
			OccurredAt:        occurred,
			ScheduleAt:        scheduleAt,
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
			zap.Int("skipped_transient", skippedTransient),
			zap.Int("skipped_missing_source", skippedMissingSource),
			zap.Int("skipped_source_not_found", skippedSourceNotFound),
		)
	}
	return mutations, nil
}

func automaticMutationScheduleAt(src sourceEntity, occurred time.Time) *time.Time {
	if !src.WatchEnabled {
		return nil
	}
	occurred = occurred.UTC()
	if occurred.IsZero() {
		occurred = time.Now().UTC()
	}
	if strings.TrimSpace(src.ReconcileSchedule) != "" {
		next := computeNextReconcileTime(src.ReconcileSchedule, occurred)
		return next
	}
	reconcileSeconds := src.ReconcileSeconds
	if reconcileSeconds <= 0 {
		return nil
	}
	anchor := occurred
	if src.WatchUpdatedAt != nil && !src.WatchUpdatedAt.IsZero() {
		anchor = src.WatchUpdatedAt.UTC()
	}
	next := nextIntervalReconcileTime(anchor, occurred, time.Duration(reconcileSeconds)*time.Second)
	return &next
}

func nextIntervalReconcileTime(anchor, after time.Time, interval time.Duration) time.Time {
	anchor = anchor.UTC()
	after = after.UTC()
	if interval <= 0 {
		return after
	}
	if anchor.IsZero() || anchor.After(after) {
		return after.Add(interval)
	}
	steps := int64(after.Sub(anchor) / interval)
	next := anchor.Add(time.Duration(steps+1) * interval)
	for !next.After(after) {
		next = next.Add(interval)
	}
	return next
}

func computeNextReconcileTime(scheduleExpr string, afterUTC time.Time) *time.Time {
	return computeNextReconcileTimeWithTZ(scheduleExpr, defaultScheduleTZ, afterUTC)
}

func computeNextReconcileTimeWithTZ(scheduleExpr, scheduleTZ string, afterUTC time.Time) *time.Time {
	everyDays, hour, minute, second, err := parseReconcileScheduleExpr(scheduleExpr)
	if err != nil {
		return nil
	}
	if everyDays <= 0 {
		everyDays = 1
	}
	tz := strings.TrimSpace(scheduleTZ)
	if tz == "" {
		tz = defaultScheduleTZ
	}
	loc, err := time.LoadLocation(tz)
	if err != nil {
		loc = time.Local
	}
	localAfter := afterUTC.In(loc)
	next := time.Date(localAfter.Year(), localAfter.Month(), localAfter.Day(), hour, minute, second, 0, loc)
	for !next.After(localAfter) {
		next = next.AddDate(0, 0, everyDays)
	}
	nextUTC := next.UTC()
	return &nextUTC
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
			if err := upsertSourceDocumentStateFromMutationTx(tx, m, s.log); err != nil {
				return err
			}
		}
		return nil
	})
}

func upsertSourceDocumentStateFromMutationTx(tx *gorm.DB, m DocumentMutation, log *zap.Logger) error {
	if strings.TrimSpace(m.SourceID) == "" || strings.TrimSpace(m.SourceObjectID) == "" {
		return nil
	}
	var src sourceEntity
	if err := tx.Take(&src, "id = ?", strings.TrimSpace(m.SourceID)).Error; err != nil {
		return err
	}
	occurred := m.OccurredAt.UTC()
	if occurred.IsZero() {
		occurred = time.Now().UTC()
	}
	path := filepath.Clean(strings.TrimSpace(m.SourceObjectID))
	if path == "" || path == "." || isTransientSourceFilePath(path, false) {
		return nil
	}
	var existing sourceDocumentStateEntity
	objectKey := sourceObjectKey(path, m.OriginRef)
	err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).
		Where("source_id = ? AND object_key = ?", src.ID, objectKey).
		Take(&existing).Error
	if err == gorm.ErrRecordNotFound && strings.TrimSpace(m.OriginRef) != "" {
		err = tx.Clauses(clause.Locking{Strength: "UPDATE"}).
			Where("source_id = ? AND path = ?", src.ID, path).
			Order("id DESC").
			Take(&existing).Error
	}
	if err != nil && err != gorm.ErrRecordNotFound {
		return err
	}
	hasExisting := err == nil
	if hasExisting && !m.ManualSync && !m.ForceSync && !existing.LastDetectedAt.IsZero() && !occurred.After(existing.LastDetectedAt.UTC()) {
		if log != nil {
			log.Debug("source document state skipped",
				zap.String("reason", "old_timestamp"),
				zap.String("source_id", src.ID),
				zap.String("source_object_id", path),
				zap.Time("event_occurred_at", occurred),
				zap.Time("last_detected_at", existing.LastDetectedAt.UTC()),
			)
		}
		return nil
	}
	doc, hasDoc, err := resolveStateDocumentTx(tx, src.ID, path, m.OriginRef)
	if err != nil {
		return err
	}
	baseline := ""
	if hasExisting {
		baseline = strings.TrimSpace(existing.BaselineVersion)
	}
	if baseline == "" && hasDoc {
		baseline = strings.TrimSpace(doc.CurrentVersionID)
	}
	knowledgeBaseSeen := false
	if hasExisting {
		knowledgeBaseSeen = existing.KnowledgeBaseSeen
	}
	if hasDoc && (strings.TrimSpace(doc.CurrentVersionID) != "" || strings.TrimSpace(doc.CoreDocumentID) != "") {
		knowledgeBaseSeen = true
	}
	exists := normalizeEventType(m.EventType) != "deleted"
	version := ""
	if exists {
		version = "v_" + occurred.Format(time.RFC3339Nano)
		if (m.ManualSync || m.ForceSync) && hasExisting && strings.TrimSpace(existing.SourceVersion) != "" {
			version = strings.TrimSpace(existing.SourceVersion)
		}
	}
	obj := observedSourceObject{
		SourceID:        src.ID,
		TenantID:        src.TenantID,
		ObjectKey:       objectKey,
		Path:            path,
		Name:            filepath.Base(path),
		SourceExists:    exists,
		OriginType:      firstNonEmpty(m.OriginType, src.DefaultOriginType, string(model.OriginTypeLocalFS)),
		OriginPlatform:  firstNonEmpty(m.OriginPlatform, src.DefaultOriginPlatform, "LOCAL"),
		OriginRef:       strings.TrimSpace(m.OriginRef),
		SourceVersion:   version,
		DetectedAt:      occurred,
		BaselineVersion: baseline,
	}
	sourceState, syncState, pendingAction, nextSyncAt := computeSourceDocumentStateTx(tx, src, obj, baseline, knowledgeBaseSeen)
	if (m.ManualSync || m.ForceSync) && pendingAction != pendingActionNone {
		syncState = syncStatePending
		nextSyncAt = nil
	}
	now := time.Now().UTC()
	row := sourceDocumentStateEntity{
		TenantID:          src.TenantID,
		SourceID:          src.ID,
		ObjectKey:         obj.ObjectKey,
		Path:              path,
		Name:              filepath.Base(path),
		SourceExists:      exists,
		OriginType:        obj.OriginType,
		OriginPlatform:    obj.OriginPlatform,
		OriginRef:         obj.OriginRef,
		SourceVersion:     version,
		BaselineVersion:   baseline,
		SourceState:       sourceState,
		SyncState:         syncState,
		PendingAction:     pendingAction,
		NextSyncAt:        nextSyncAt,
		LastDetectedAt:    occurred,
		KnowledgeBaseSeen: knowledgeBaseSeen,
		CreatedAt:         now,
		UpdatedAt:         now,
	}
	if hasDoc {
		row.DocumentID = doc.ID
		row.CoreDocumentID = strings.TrimSpace(doc.CoreDocumentID)
		if strings.TrimSpace(doc.CurrentVersionID) != "" {
			t := doc.UpdatedAt.UTC()
			row.LastSyncedAt = &t
		}
	}
	if sourceState == sourceStateDeleted {
		t := occurred.UTC()
		row.DeletedAtSource = &t
	}
	if sourceState == sourceStateUnchanged && pendingAction == pendingActionNone && !knowledgeBaseSeen && !hasDoc {
		if hasExisting {
			return tx.Delete(&sourceDocumentStateEntity{}, "id = ?", existing.ID).Error
		}
		return nil
	}
	if hasExisting {
		row.ID = existing.ID
		row.CreatedAt = existing.CreatedAt
		if strings.TrimSpace(existing.LastError) != "" && sourceState == existing.SourceState && pendingAction == existing.PendingAction {
			row.LastError = existing.LastError
		}
		updates := map[string]any{
			"tenant_id":           row.TenantID,
			"path":                row.Path,
			"name":                row.Name,
			"source_exists":       row.SourceExists,
			"origin_type":         row.OriginType,
			"origin_platform":     row.OriginPlatform,
			"origin_ref":          row.OriginRef,
			"source_version":      row.SourceVersion,
			"baseline_version":    row.BaselineVersion,
			"source_state":        row.SourceState,
			"sync_state":          row.SyncState,
			"pending_action":      row.PendingAction,
			"document_id":         row.DocumentID,
			"core_document_id":    row.CoreDocumentID,
			"last_detected_at":    row.LastDetectedAt,
			"last_error":          row.LastError,
			"knowledge_base_seen": row.KnowledgeBaseSeen,
			"updated_at":          row.UpdatedAt,
		}
		setNullableTimeColumn(updates, "next_sync_at", row.NextSyncAt)
		setNullableTimeColumn(updates, "last_synced_at", row.LastSyncedAt)
		setNullableTimeColumn(updates, "deleted_at_source", row.DeletedAtSource)
		return tx.Model(&sourceDocumentStateEntity{}).Where("id = ?", existing.ID).Updates(updates).Error
	}
	if err := tx.Create(&row).Error; err != nil && log != nil {
		log.Warn("upsert source document state from mutation failed", zap.String("source_id", src.ID), zap.String("path", path), zap.Error(err))
		return err
	}
	return nil
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
		if m.ManualSync || m.ForceSync {
			when = occurred
		} else if m.ScheduleAt != nil {
			when = m.ScheduleAt.UTC()
		} else if policy == string(model.TriggerPolicyIdleWindow) {
			idle := m.IdleWindowSeconds
			if idle <= 0 {
				idle = 1
			}
			when = occurred.Add(time.Duration(idle) * time.Second)
		}
		nextParse = &when
	}

	doc, err := resolveMutationDocument(tx, m, now, log)
	if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		return err
	}

	existingLast := time.Time{}
	if err == nil && doc.LastModifiedAt != nil {
		existingLast = doc.LastModifiedAt.UTC()
	}
	// For the same file, accept only newer event timestamps.
	// This avoids duplicate task triggers from identical mtimes during full-scan or restart.
	if !m.ManualSync && !m.ForceSync && !existingLast.IsZero() && !occurred.After(existingLast) {
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
		var nextDeleteAt *time.Time
		activeDeleteQueued := false
		if !m.ManualSync && err == nil && strings.EqualFold(strings.TrimSpace(doc.ParseStatus), "DELETED") && doc.NextParseAt == nil && strings.TrimSpace(doc.CoreDocumentID) != "" {
			active, activeErr := hasActiveDeleteTaskTx(tx, doc.ID)
			if activeErr != nil {
				return activeErr
			}
			activeDeleteQueued = active
		}
		if activeDeleteQueued {
			if existingDesired := strings.TrimSpace(doc.DesiredVersionID); existingDesired != "" {
				desiredVersion = existingDesired
			}
		} else {
			nextDeleteAtValue := occurred
			if m.ManualSync || m.ForceSync {
				nextDeleteAtValue = occurred
			} else if m.ScheduleAt != nil {
				nextDeleteAtValue = m.ScheduleAt.UTC()
			} else if policy == string(model.TriggerPolicyIdleWindow) {
				idle := m.IdleWindowSeconds
				if idle <= 0 {
					idle = 1
				}
				nextDeleteAtValue = occurred.Add(time.Duration(idle) * time.Second)
			}
			if !m.ManualSync && err == nil && strings.EqualFold(strings.TrimSpace(doc.ParseStatus), "DELETED") && doc.NextParseAt != nil {
				existingNext := doc.NextParseAt.UTC()
				if existingNext.Before(nextDeleteAtValue) || existingNext.Equal(nextDeleteAtValue) {
					nextDeleteAtValue = existingNext
				}
			}
			nextDeleteAt = &nextDeleteAtValue
		}
		updates := map[string]any{
			"desired_version_id": desiredVersion,
			"last_modified_at":   occurred,
			"next_parse_at":      nextDeleteAt,
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
				NextParseAt:      nextDeleteAt,
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

func hasActiveDeleteTaskTx(tx *gorm.DB, documentID int64) (bool, error) {
	var count int64
	if err := tx.Model(&parseTaskEntity{}).
		Where("document_id = ? AND task_action = ? AND status IN ?", documentID, taskActionDelete, []string{"PENDING", "RETRY_WAITING", "RUNNING", "SUBMITTED"}).
		Count(&count).Error; err != nil {
		return false, err
	}
	return count > 0, nil
}

func resolveMutationDocument(tx *gorm.DB, m DocumentMutation, now time.Time, log *zap.Logger) (documentEntity, error) {
	var doc documentEntity
	err := tx.Where("tenant_id = ? AND source_id = ? AND source_object_id = ?", m.TenantID, m.SourceID, m.SourceObjectID).Take(&doc).Error
	if err == nil {
		return doc, nil
	}
	if !errors.Is(err, gorm.ErrRecordNotFound) {
		return documentEntity{}, err
	}
	if !shouldResolveCloudDocumentByOriginRef(m.OriginType, m.OriginRef) {
		return documentEntity{}, gorm.ErrRecordNotFound
	}

	originRef := strings.TrimSpace(m.OriginRef)
	if err := tx.
		Where(
			"tenant_id = ? AND source_id = ? AND origin_ref = ? AND UPPER(origin_type) = ?",
			m.TenantID,
			m.SourceID,
			originRef,
			string(model.OriginTypeCloudSync),
		).
		Order("updated_at DESC, id DESC").
		Take(&doc).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return documentEntity{}, gorm.ErrRecordNotFound
		}
		return documentEntity{}, err
	}

	if normalizeEventType(m.EventType) == "deleted" {
		return doc, nil
	}
	newPath := strings.TrimSpace(m.SourceObjectID)
	oldPath := strings.TrimSpace(doc.SourceObjectID)
	if newPath == "" || oldPath == "" || newPath == oldPath {
		return doc, nil
	}

	var conflict documentEntity
	conflictErr := tx.Where(
		"tenant_id = ? AND source_id = ? AND source_object_id = ?",
		m.TenantID,
		m.SourceID,
		newPath,
	).Take(&conflict).Error
	if conflictErr != nil && !errors.Is(conflictErr, gorm.ErrRecordNotFound) {
		return documentEntity{}, conflictErr
	}
	if conflictErr == nil && conflict.ID != doc.ID {
		// A record already exists for the same path. Reuse it only when it has the same origin_ref;
		// otherwise abort to avoid contaminating another document's primary identity.
		if strings.TrimSpace(conflict.OriginRef) == originRef &&
			shouldResolveCloudDocumentByOriginRef(conflict.OriginType, conflict.OriginRef) {
			return conflict, nil
		}
		return documentEntity{}, fmt.Errorf(
			"cloud path collision for origin_ref=%s source_id=%s target_path=%s existing_document_id=%d current_document_id=%d",
			originRef,
			m.SourceID,
			newPath,
			conflict.ID,
			doc.ID,
		)
	}

	if err := tx.Model(&documentEntity{}).Where("id = ?", doc.ID).Updates(map[string]any{
		"source_object_id": newPath,
		"updated_at":       now,
	}).Error; err != nil {
		return documentEntity{}, err
	}
	if log != nil {
		log.Info("cloud document path updated by origin_ref",
			zap.Int64("document_id", doc.ID),
			zap.String("source_id", m.SourceID),
			zap.String("origin_ref", originRef),
			zap.String("old_path", oldPath),
			zap.String("new_path", newPath),
		)
	}
	doc.SourceObjectID = newPath
	doc.UpdatedAt = now
	return doc, nil
}

func shouldResolveCloudDocumentByOriginRef(originType, originRef string) bool {
	if strings.TrimSpace(originRef) == "" {
		return false
	}
	return strings.EqualFold(strings.TrimSpace(originType), string(model.OriginTypeCloudSync))
}

func (s *Store) ScheduleDueParses(ctx context.Context, now time.Time) (int, error) {
	created := 0
	err := s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := s.materializeDueSourceDocumentStatesTx(tx, now); err != nil {
			return err
		}
		var docs []documentEntity
		if err := tx.
			Where("next_parse_at IS NOT NULL AND next_parse_at <= ?", now.UTC()).
			Find(&docs).Error; err != nil {
			return err
		}
		for _, doc := range docs {
			if isTransientSourceFilePath(doc.SourceObjectID, false) {
				if err := tx.Model(&documentEntity{}).Where("id = ?", doc.ID).Updates(map[string]any{
					"next_parse_at": nil,
					"updated_at":    now.UTC(),
				}).Error; err != nil {
					return err
				}
				continue
			}
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

			// Merge only unexecuted tasks; executed tasks remain as history.
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
				pendingTask.ID = pendingTaskID
				pendingTask.DocumentID = doc.ID
				if err := updateSourceDocumentStateTaskQueuedTx(tx, pendingTask, now); err != nil {
					return err
				}
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
					// Concurrent inserts may be blocked by the unique index, so fall back to update.
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
						pendingTask.ID = pendingTaskID
						pendingTask.DocumentID = doc.ID
						if err := updateSourceDocumentStateTaskQueuedTx(tx, pendingTask, now); err != nil {
							return err
						}
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
					if err := updateSourceDocumentStateTaskQueuedTx(tx, task, now); err != nil {
						return err
					}
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

func (s *Store) materializeDueSourceDocumentStatesTx(tx *gorm.DB, now time.Time) error {
	var states []sourceDocumentStateEntity
	if err := tx.
		Where("next_sync_at IS NOT NULL AND next_sync_at <= ? AND source_state IN ? AND sync_state IN ?", now.UTC(), []string{sourceStateNew, sourceStateModified, sourceStateDeleted}, []string{syncStateScheduled, syncStatePending, syncStateFailed}).
		Find(&states).Error; err != nil {
		return err
	}
	for _, state := range states {
		if state.IsDir || isTransientSourceFilePath(state.Path, false) {
			continue
		}
		occurred := state.LastDetectedAt.UTC()
		if occurred.IsZero() {
			occurred = now.UTC()
		}
		eventType := "modified"
		if strings.EqualFold(strings.TrimSpace(state.SourceState), sourceStateDeleted) {
			eventType = "deleted"
		}
		mutation := DocumentMutation{
			TenantID:       state.TenantID,
			SourceID:       state.SourceID,
			SourceObjectID: state.Path,
			EventType:      eventType,
			OccurredAt:     occurred,
			ScheduleAt:     &now,
			ForceSync:      true,
			OriginType:     state.OriginType,
			OriginPlatform: state.OriginPlatform,
			OriginRef:      state.OriginRef,
		}
		if err := applyDocumentMutation(tx, mutation, s.log); err != nil {
			return err
		}
		if err := upsertSourceDocumentStateFromMutationTx(tx, mutation, s.log); err != nil {
			return err
		}
	}
	return nil
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
			DocumentID         int64
			SourceID           string
			SourceRootPath     string
			SourceDatasetID    string
			SourceCreateUserID string
			CoreDocumentID     string
			SourceObjectID     string
			DesiredVersionID   string
			AgentID            string
			ListenAddr         string
		}
		if err := s.db.WithContext(ctx).
			Table("documents d").
			Select("d.id as document_id, d.source_id, s.root_path as source_root_path, s.dataset_id as source_dataset_id, s.create_user_id as source_create_user_id, d.core_document_id, d.source_object_id, d.desired_version_id, s.agent_id, a.listen_addr").
			Joins("JOIN sources s ON s.id = d.source_id").
			Joins("LEFT JOIN agents a ON a.agent_id = s.agent_id").
			Where("d.id = ?", task.DocumentID).
			Take(&row).Error; err != nil {
			return nil, err
		}
		if isTransientSourceFilePath(row.SourceObjectID, false) {
			if err := s.MarkTaskSuperseded(ctx, task.ID, "transient editor file is ignored"); err != nil {
				return nil, err
			}
			continue
		}
		result = append(result, PendingTask{
			TaskID:             task.ID,
			TenantID:           task.TenantID,
			DocumentID:         task.DocumentID,
			TaskAction:         normalizeTaskAction(task.TaskAction),
			TargetVersionID:    task.TargetVersionID,
			IdempotencyKey:     strings.TrimSpace(task.IdempotencyKey),
			RetryCount:         task.RetryCount,
			MaxRetryCount:      max(1, task.MaxRetryCount),
			OriginType:         task.OriginType,
			OriginPlatform:     task.OriginPlatform,
			TriggerPolicy:      task.TriggerPolicy,
			SourceID:           row.SourceID,
			SourceRootPath:     row.SourceRootPath,
			SourceDatasetID:    strings.TrimSpace(row.SourceDatasetID),
			SourceCreateUserID: strings.TrimSpace(row.SourceCreateUserID),
			CoreDocumentID:     firstNonEmpty(strings.TrimSpace(task.CoreDocumentID), strings.TrimSpace(row.CoreDocumentID)),
			SourceObjectID:     row.SourceObjectID,
			DesiredVersionID:   row.DesiredVersionID,
			AgentID:            row.AgentID,
			AgentListenAddr:    row.ListenAddr,
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

func (s *Store) ValidateTaskSubmission(ctx context.Context, taskID int64) (TaskSubmissionValidation, error) {
	var row struct {
		TaskID           int64
		DocumentID       int64
		TaskAction       string
		TargetVersionID  string
		TaskStatus       string
		DesiredVersionID string
		ParseStatus      string
		CoreDocumentID   string
	}
	if err := s.db.WithContext(ctx).
		Table("parse_tasks pt").
		Select("pt.id AS task_id, pt.document_id, pt.task_action, pt.target_version_id, pt.status AS task_status, d.desired_version_id, d.parse_status, d.core_document_id").
		Joins("JOIN documents d ON d.id = pt.document_id").
		Where("pt.id = ?", taskID).
		Take(&row).Error; err != nil {
		return TaskSubmissionValidation{}, err
	}
	status := strings.ToUpper(strings.TrimSpace(row.TaskStatus))
	switch status {
	case "RUNNING", "STAGING":
	default:
		return TaskSubmissionValidation{
			Valid:  false,
			Reason: fmt.Sprintf("task status %s is not submittable", row.TaskStatus),
		}, nil
	}
	if normalizeTaskAction(row.TaskAction) != inferTaskActionForSubmission(row.DesiredVersionID, row.ParseStatus, row.CoreDocumentID) {
		return TaskSubmissionValidation{
			Valid:  false,
			Reason: "task_action no longer matches document state",
		}, nil
	}
	if strings.TrimSpace(row.TargetVersionID) != strings.TrimSpace(row.DesiredVersionID) {
		return TaskSubmissionValidation{
			Valid:  false,
			Reason: "target_version_id no longer matches desired_version_id",
		}, nil
	}
	return TaskSubmissionValidation{Valid: true}, nil
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
		if err := tx.Model(&documentEntity{}).Where("id = ?", task.DocumentID).Updates(docUpdates).Error; err != nil {
			return err
		}
		return updateSourceDocumentStateTaskRunningTx(tx, task, at, coreDocumentID)
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
		if err := updateSourceDocumentStateTaskFailedTx(tx, task, now, lastError); err != nil {
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
		if err := tx.Model(&documentEntity{}).Where("id = ?", documentID).Updates(docUpdates).Error; err != nil {
			return err
		}
		var doc documentEntity
		if err := tx.Take(&doc, "id = ?", documentID).Error; err != nil {
			return err
		}
		if err := updateSourceDocumentStateTaskSucceededTx(tx, task, doc, now, targetVersion); err != nil {
			return err
		}
		return s.commitCloudDocumentSnapshotAfterTaskSucceededTx(tx, task, doc, now, targetVersion)
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

func inferTaskActionForSubmission(desiredVersionID, parseStatus, coreDocumentID string) string {
	if strings.EqualFold(strings.TrimSpace(parseStatus), "DELETED") {
		return taskActionDelete
	}
	if strings.TrimSpace(coreDocumentID) != "" {
		return taskActionReparse
	}
	if strings.TrimSpace(desiredVersionID) == "" {
		return ""
	}
	return taskActionCreate
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
	SourceCreateUserID      string
	SourceCreateUserName    string
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
	SourceCreateUserID      string
	SourceCreateUserName    string
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
			s.create_user_id AS source_create_user_id,
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
			s.create_user_id AS source_create_user_id,
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
		Select("pt.id AS task_id, pt.document_id, pt.task_action, pt.target_version_id, pt.core_document_id, pt.status, pt.core_dataset_id, pt.core_task_id, pt.scan_orchestration_status, pt.submit_at, pt.finished_at, pt.updated_at").
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
