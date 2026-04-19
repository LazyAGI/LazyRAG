package store

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"time"

	"go.uber.org/zap"
	"gorm.io/gorm"
	"gorm.io/gorm/clause"

	"github.com/lazyrag/scan_control_plane/internal/model"
)

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
