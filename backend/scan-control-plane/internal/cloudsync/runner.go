package cloudsync

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"go.uber.org/zap"

	"github.com/lazyrag/scan_control_plane/internal/cloudsync/authclient"
	"github.com/lazyrag/scan_control_plane/internal/cloudsync/mirror"
	"github.com/lazyrag/scan_control_plane/internal/cloudsync/provider"
	"github.com/lazyrag/scan_control_plane/internal/cloudsync/provider/feishu"
	"github.com/lazyrag/scan_control_plane/internal/config"
	"github.com/lazyrag/scan_control_plane/internal/model"
	"github.com/lazyrag/scan_control_plane/internal/sourcelayout"
	"github.com/lazyrag/scan_control_plane/internal/store"
)

type Store interface {
	ClaimDueCloudSources(ctx context.Context, lockOwner string, now time.Time, limit int, lockTTL time.Duration) ([]store.CloudSyncClaim, error)
	ClaimCloudSourceByID(ctx context.Context, sourceID, lockOwner string, now time.Time, lockTTL time.Duration) (store.CloudSyncClaim, error)
	ReleaseCloudSyncLock(ctx context.Context, sourceID string, now time.Time) error
	StartCloudSyncRun(ctx context.Context, sourceID, triggerType, requestedRunID string, startedAt time.Time) (model.CloudSyncRun, error)
	FinishCloudSyncRun(ctx context.Context, sourceID string, finalize store.CloudSyncRunFinalize) error
	ListCloudObjectIndex(ctx context.Context, sourceID string) ([]store.CloudObjectIndexRecord, error)
	UpsertCloudObjectIndexBatch(ctx context.Context, sourceID, provider string, records []store.CloudObjectIndexRecord, now time.Time) error
	MarkCloudObjectsDeleted(ctx context.Context, sourceID string, externalObjectIDs []string, now time.Time) error
	EmitCloudFileEvents(ctx context.Context, events []model.FileEvent) error
}

type triggerRequest struct {
	sourceID string
	runID    string
}

type Runner struct {
	cfg       config.CloudSyncConfig
	store     Store
	auth      *authclient.Client
	providers map[string]provider.Provider
	log       *zap.Logger
	owner     string
	sem       chan struct{}
	triggerCh chan triggerRequest
}

func New(cfg config.CloudSyncConfig, st Store, log *zap.Logger) *Runner {
	if st == nil {
		return nil
	}
	if log == nil {
		log = zap.NewNop()
	}
	if cfg.MaxConcurrent <= 0 {
		cfg.MaxConcurrent = 1
	}
	return &Runner{
		cfg:   cfg,
		store: st,
		auth: authclient.New(
			cfg.AuthServiceBaseURL,
			cfg.AuthServiceInternalToken,
			cfg.HTTPTimeout,
		),
		providers: map[string]provider.Provider{
			"feishu": feishu.NewWithLogger(cfg.HTTPTimeout, log),
		},
		log:       log,
		owner:     fmt.Sprintf("cloudsync-%d", time.Now().UnixNano()),
		sem:       make(chan struct{}, cfg.MaxConcurrent),
		triggerCh: make(chan triggerRequest, cfg.MaxConcurrent*4),
	}
}

func (r *Runner) Trigger(sourceID, runID string) bool {
	if r == nil {
		return false
	}
	req := triggerRequest{
		sourceID: strings.TrimSpace(sourceID),
		runID:    strings.TrimSpace(runID),
	}
	if req.sourceID == "" {
		return false
	}
	select {
	case r.triggerCh <- req:
		return true
	default:
		return false
	}
}

func (r *Runner) Run(ctx context.Context) {
	if r == nil {
		return
	}
	if !r.cfg.Enabled {
		r.log.Info("cloud sync runner disabled")
		return
	}
	if tempDir := strings.TrimSpace(r.cfg.TempDir); tempDir != "" {
		if err := mirror.EnsureDir(tempDir); err != nil {
			r.log.Warn("ensure cloud sync temp dir failed", zap.String("temp_dir", tempDir), zap.Error(err))
		}
	}
	ticker := time.NewTicker(r.cfg.Tick)
	defer ticker.Stop()
	// startup sweep
	r.claimAndDispatch(ctx, time.Now().UTC())
	for {
		select {
		case <-ctx.Done():
			return
		case req := <-r.triggerCh:
			r.handleTrigger(ctx, req)
		case now := <-ticker.C:
			r.claimAndDispatch(ctx, now.UTC())
		}
	}
}

func (r *Runner) handleTrigger(ctx context.Context, req triggerRequest) {
	now := time.Now().UTC()
	claim, err := r.store.ClaimCloudSourceByID(ctx, req.sourceID, r.owner, now, r.cfg.LockTTL)
	if err != nil {
		if err == store.ErrCloudSyncLocked {
			r.log.Warn("cloud sync trigger skipped due to lock",
				zap.String("source_id", req.sourceID),
				zap.Error(err),
			)
			return
		}
		r.log.Error("claim cloud source by id failed",
			zap.String("source_id", req.sourceID),
			zap.Error(err),
		)
		return
	}
	if strings.TrimSpace(req.runID) != "" {
		claim.ExistingRunID = strings.TrimSpace(req.runID)
	}
	r.dispatch(ctx, claim, "manual")
}

func (r *Runner) claimAndDispatch(ctx context.Context, now time.Time) {
	available := cap(r.sem) - len(r.sem)
	if available <= 0 {
		return
	}
	limit := available
	if r.cfg.MaxConcurrent > 0 && limit > r.cfg.MaxConcurrent {
		limit = r.cfg.MaxConcurrent
	}
	claims, err := r.store.ClaimDueCloudSources(ctx, r.owner, now, limit, r.cfg.LockTTL)
	if err != nil {
		r.log.Error("claim due cloud sources failed", zap.Error(err))
		return
	}
	for _, claim := range claims {
		r.dispatch(ctx, claim, "scheduled")
	}
}

func (r *Runner) dispatch(ctx context.Context, claim store.CloudSyncClaim, triggerType string) {
	select {
	case r.sem <- struct{}{}:
	default:
		return
	}
	go func() {
		defer func() { <-r.sem }()
		r.executeOnce(ctx, claim, triggerType)
	}()
}

func (r *Runner) executeOnce(ctx context.Context, claim store.CloudSyncClaim, triggerType string) {
	startedAt := time.Now().UTC()
	run, err := r.store.StartCloudSyncRun(ctx, claim.SourceID, triggerType, claim.ExistingRunID, startedAt)
	if err != nil {
		r.log.Error("start cloud sync run failed",
			zap.String("source_id", claim.SourceID),
			zap.Error(err),
		)
		_ = r.store.ReleaseCloudSyncLock(ctx, claim.SourceID, time.Now().UTC())
		return
	}

	finalize := store.CloudSyncRunFinalize{
		RunID:      run.RunID,
		Status:     "FAILED",
		FinishedAt: time.Now().UTC(),
	}
	defer func() {
		finalize.FinishedAt = time.Now().UTC()
		if err := r.store.FinishCloudSyncRun(ctx, claim.SourceID, finalize); err != nil {
			r.log.Error("finish cloud sync run failed",
				zap.String("source_id", claim.SourceID),
				zap.String("run_id", run.RunID),
				zap.Error(err),
			)
		}
		r.log.Info("cloud sync run finalized",
			zap.String("source_id", claim.SourceID),
			zap.String("run_id", run.RunID),
			zap.String("provider", claim.Provider),
			zap.String("trigger_type", triggerType),
			zap.String("status", finalize.Status),
			zap.String("error_code", strings.TrimSpace(finalize.ErrorCode)),
			zap.Int("remote_total", finalize.RemoteTotal),
			zap.Int("created_count", finalize.CreatedCount),
			zap.Int("updated_count", finalize.UpdatedCount),
			zap.Int("deleted_count", finalize.DeletedCount),
			zap.Int("skipped_count", finalize.SkippedCount),
			zap.Int("failed_count", finalize.FailedCount),
			zap.Duration("duration", finalize.FinishedAt.Sub(startedAt)),
		)
	}()

	var tokenResp authclient.TokenResponse
	err = r.withRetry(ctx, "acquire_access_token", func() error {
		var innerErr error
		tokenResp, innerErr = r.auth.GetAccessToken(ctx, claim.AuthConnectionID)
		return innerErr
	})
	if err != nil {
		finalize.ErrorCode = "AUTH_TOKEN_FAILED"
		finalize.ErrorMessage = err.Error()
		return
	}
	accessToken := strings.TrimSpace(tokenResp.AccessToken)
	if accessToken == "" {
		finalize.ErrorCode = "AUTH_TOKEN_EMPTY"
		finalize.ErrorMessage = "auth token response missing access_token"
		return
	}
	expiresAt := ""
	if tokenResp.ExpiresAt != nil && !tokenResp.ExpiresAt.IsZero() {
		expiresAt = tokenResp.ExpiresAt.UTC().Format(time.RFC3339)
	}
	r.log.Info("cloud sync access token acquired",
		zap.String("source_id", claim.SourceID),
		zap.String("run_id", run.RunID),
		zap.String("provider", claim.Provider),
		zap.String("auth_connection_id", strings.TrimSpace(claim.AuthConnectionID)),
		zap.String("token_provider", strings.TrimSpace(tokenResp.Provider)),
		zap.String("token_status", strings.TrimSpace(tokenResp.Status)),
		zap.Int("access_token_len", len(accessToken)),
		zap.String("access_token_expires_at", expiresAt),
	)
	impl, ok := r.providers[strings.ToLower(strings.TrimSpace(claim.Provider))]
	if !ok || impl == nil {
		finalize.ErrorCode = "PROVIDER_UNSUPPORTED"
		finalize.ErrorMessage = fmt.Sprintf("unsupported cloud provider: %s", claim.Provider)
		return
	}
	sourceRoot := filepath.Clean(strings.TrimSpace(claim.RootPath))
	if sourceRoot == "" || sourceRoot == "." {
		finalize.ErrorCode = "SOURCE_ROOT_EMPTY"
		finalize.ErrorMessage = "cloud source root_path is empty"
		return
	}
	mirrorRoot := sourcelayout.CloudMirrorRoot(sourceRoot)
	parseRoot := sourcelayout.CloudParseRoot(sourceRoot)
	if err := mirror.EnsureDir(mirrorRoot); err != nil {
		finalize.ErrorCode = "MIRROR_ROOT_INIT_FAILED"
		finalize.ErrorMessage = err.Error()
		return
	}
	if err := mirror.EnsureDir(parseRoot); err != nil {
		finalize.ErrorCode = "PARSE_ROOT_INIT_FAILED"
		finalize.ErrorMessage = err.Error()
		return
	}
	r.log.Info("cloud sync layout roots ready",
		zap.String("source_id", claim.SourceID),
		zap.String("run_id", run.RunID),
		zap.String("source_root", sourceRoot),
		zap.String("mirror_root", mirrorRoot),
		zap.String("parse_root", parseRoot),
	)

	var objects []provider.RemoteObject
	err = r.withRetry(ctx, "list_remote_objects", func() error {
		var innerErr error
		objects, innerErr = impl.ListObjects(ctx, provider.ListRequest{
			AccessToken:     accessToken,
			TargetType:      claim.TargetType,
			TargetRef:       claim.TargetRef,
			ProviderOptions: claim.ProviderOptions,
		})
		return innerErr
	})
	if err != nil {
		finalize.ErrorCode = "REMOTE_LIST_FAILED"
		finalize.ErrorMessage = err.Error()
		return
	}
	remoteObjectDetails, remoteObjectsOmitted := describeRemoteObjectsForLog(objects, 500)
	r.log.Info("cloud sync remote list fetched",
		zap.String("source_id", claim.SourceID),
		zap.String("run_id", run.RunID),
		zap.String("provider", claim.Provider),
		zap.String("target_type", strings.TrimSpace(claim.TargetType)),
		zap.String("target_ref", strings.TrimSpace(claim.TargetRef)),
		zap.Int("remote_objects_total", len(objects)),
		zap.Int("remote_objects_omitted", remoteObjectsOmitted),
		zap.Strings("remote_objects", remoteObjectDetails),
		zap.Strings("include_patterns", claim.IncludePatterns),
		zap.Strings("exclude_patterns", claim.ExcludePatterns),
	)
	if len(objects) == 0 {
		r.log.Warn("cloud sync remote list is empty",
			zap.String("source_id", claim.SourceID),
			zap.String("run_id", run.RunID),
			zap.String("provider", claim.Provider),
			zap.String("target_type", strings.TrimSpace(claim.TargetType)),
			zap.String("target_ref", strings.TrimSpace(claim.TargetRef)),
		)
	}
	sort.Slice(objects, func(i, j int) bool { return objects[i].ExternalObjectID < objects[j].ExternalObjectID })
	filtered := make([]provider.RemoteObject, 0, len(objects))
	filteredByPattern := 0
	keptByDirPassthrough := 0
	keptByIncludePattern := 0
	keptByNoIncludeRules := 0
	droppedByIncludeMiss := 0
	droppedByExcludeMatch := 0
	filteredPatternSamples := make([]string, 0, 4)
	passedPatternSamples := make([]string, 0, 4)
	decisionSamples := make([]string, 0, 12)
	for _, obj := range objects {
		decision := includeObjectDecision(obj, claim.IncludePatterns, claim.ExcludePatterns)
		decisionSamples = appendFilterDecisionSample(decisionSamples, obj, decision, 12)
		if decision.Include {
			filtered = append(filtered, obj)
			passedPatternSamples = appendRemoteObjectSample(passedPatternSamples, obj, 4)
			switch decision.Reason {
			case "directory_passthrough":
				keptByDirPassthrough++
			case "included_by_pattern":
				keptByIncludePattern++
			default:
				keptByNoIncludeRules++
			}
			continue
		}
		filteredByPattern++
		filteredPatternSamples = appendRemoteObjectSample(filteredPatternSamples, obj, 4)
		switch decision.Reason {
		case "include_not_matched":
			droppedByIncludeMiss++
		case "excluded_by_pattern":
			droppedByExcludeMatch++
		}
	}
	finalize.RemoteTotal = len(filtered)
	r.log.Info("cloud sync filter summary",
		zap.String("source_id", claim.SourceID),
		zap.String("run_id", run.RunID),
		zap.Int("remote_total", len(objects)),
		zap.Int("after_pattern_filter", len(filtered)),
		zap.Int("filtered_by_pattern", filteredByPattern),
		zap.Int("kept_by_directory_passthrough", keptByDirPassthrough),
		zap.Int("kept_by_include_pattern", keptByIncludePattern),
		zap.Int("kept_without_include_rules", keptByNoIncludeRules),
		zap.Int("dropped_by_include_not_matched", droppedByIncludeMiss),
		zap.Int("dropped_by_exclude_matched", droppedByExcludeMatch),
		zap.Strings("sample_filtered_by_pattern", filteredPatternSamples),
		zap.Strings("sample_passed_pattern", passedPatternSamples),
		zap.Strings("sample_filter_decisions", decisionSamples),
	)
	if len(objects) > 0 && len(filtered) == 0 {
		r.log.Warn("cloud sync all remote objects filtered out",
			zap.String("source_id", claim.SourceID),
			zap.String("run_id", run.RunID),
			zap.Strings("include_patterns", claim.IncludePatterns),
			zap.Strings("exclude_patterns", claim.ExcludePatterns),
			zap.Strings("sample_filtered_by_pattern", filteredPatternSamples),
		)
	}
	requestedScopePaths := normalizeManualScopePaths(run.RequestedPaths, claim.SourceID, mirrorRoot)
	manualScopeEnabled := len(requestedScopePaths) > 0
	if manualScopeEnabled {
		r.log.Info("cloud sync manual path scope enabled",
			zap.String("source_id", claim.SourceID),
			zap.String("run_id", run.RunID),
			zap.Int("requested_paths_count", len(requestedScopePaths)),
			zap.Strings("requested_paths", requestedScopePaths),
		)
	}

	existing, err := r.store.ListCloudObjectIndex(ctx, claim.SourceID)
	if err != nil {
		finalize.ErrorCode = "INDEX_LOAD_FAILED"
		finalize.ErrorMessage = err.Error()
		return
	}
	existingByID := make(map[string]store.CloudObjectIndexRecord, len(existing))
	pathOwner := make(map[string]string, len(existing))
	for _, item := range existing {
		id := strings.TrimSpace(item.ExternalObjectID)
		if id == "" {
			continue
		}
		existingByID[id] = item
		if !item.IsDeleted {
			rel := strings.TrimSpace(item.LocalRelPath)
			if rel != "" {
				pathOwner[rel] = id
			}
		}
	}

	now := time.Now().UTC()
	seenIDs := make(map[string]struct{}, len(filtered))
	upserts := make([]store.CloudObjectIndexRecord, 0, len(filtered))
	deleteIDs := make([]string, 0, len(existing))
	events := make([]model.FileEvent, 0, len(filtered))
	var errorMessages []string
	skippedByManualScope := 0

	for idx, obj := range filtered {
		objectID := strings.TrimSpace(obj.ExternalObjectID)
		if objectID == "" {
			finalize.FailedCount++
			errorMessages = appendError(errorMessages, "empty external_object_id")
			continue
		}
		seenIDs[objectID] = struct{}{}
		kind := normalizeKind(obj.ExternalKind, obj.ProviderMeta)
		isDir := isDirKind(kind)

		localRel := sanitizeRelativePath(obj.ExternalPath, obj.ExternalName, objectID, kind)
		localRel = resolvePathCollision(localRel, objectID, pathOwner)
		localAbs := filepath.Clean(filepath.Join(filepath.Clean(mirrorRoot), filepath.FromSlash(localRel)))
		if !isPathUnderRoot(localAbs, mirrorRoot) {
			finalize.FailedCount++
			errorMessages = appendError(errorMessages, fmt.Sprintf("sanitized path escapes root for object %s", objectID))
			continue
		}
		if manualScopeEnabled && !pathInRequestedScope(localAbs, requestedScopePaths) {
			skippedByManualScope++
			continue
		}

		var (
			checksum string
			size     int64
		)
		if isDir {
			if err := mirror.EnsureDir(localAbs); err != nil {
				finalize.FailedCount++
				errorMessages = appendError(errorMessages, fmt.Sprintf("mkdir failed for %s: %v", localAbs, err))
				continue
			}
		} else {
			if claim.MaxObjectSizeBytes > 0 && obj.SizeBytes > 0 && obj.SizeBytes > claim.MaxObjectSizeBytes {
				finalize.SkippedCount++
				continue
			}
			var content []byte
			err := r.withRetry(ctx, "download_object", func() error {
				var innerErr error
				content, innerErr = impl.DownloadObject(ctx, accessToken, obj)
				return innerErr
			})
			if err != nil {
				finalize.FailedCount++
				errorMessages = appendError(errorMessages, fmt.Sprintf("download failed for %s: %v", objectID, err))
				continue
			}
			size = int64(len(content))
			if obj.SizeBytes > 0 {
				size = obj.SizeBytes
			}
			checksum = sha256Hex(content)

			prev, hasPrev := existingByID[objectID]
			shouldWrite := true
			if hasPrev && !prev.IsDeleted {
				if strings.EqualFold(strings.TrimSpace(prev.Checksum), checksum) && filepath.Clean(strings.TrimSpace(prev.LocalAbsPath)) == localAbs {
					shouldWrite = false
				}
			}
			if shouldWrite {
				if hasPrev && !prev.IsDeleted {
					oldPath := filepath.Clean(strings.TrimSpace(prev.LocalAbsPath))
					if oldPath != "" && oldPath != localAbs && isPathUnderRoot(oldPath, sourceRoot) {
						_ = mirror.DeletePath(oldPath, false)
					}
				}
				if err := mirror.WriteFileAtomic(localAbs, content); err != nil {
					finalize.FailedCount++
					errorMessages = appendError(errorMessages, fmt.Sprintf("write mirror file failed for %s: %v", objectID, err))
					continue
				}
				r.log.Info("cloud sync mirror file written",
					zap.String("source_id", claim.SourceID),
					zap.String("run_id", run.RunID),
					zap.String("object_id", objectID),
					zap.String("local_abs_path", localAbs),
					zap.Int64("size_bytes", size),
				)
			}
		}

		existingItem, hasExisting := existingByID[objectID]
		isChanged := !hasExisting || existingItem.IsDeleted ||
			!strings.EqualFold(strings.TrimSpace(existingItem.ExternalVersion), strings.TrimSpace(obj.ExternalVersion)) ||
			!strings.EqualFold(strings.TrimSpace(existingItem.ExternalPath), strings.TrimSpace(obj.ExternalPath)) ||
			!strings.EqualFold(strings.TrimSpace(existingItem.LocalRelPath), strings.TrimSpace(localRel)) ||
			!strings.EqualFold(filepath.Clean(strings.TrimSpace(existingItem.LocalAbsPath)), filepath.Clean(localAbs)) ||
			!strings.EqualFold(strings.TrimSpace(existingItem.ExternalKind), strings.TrimSpace(kind)) ||
			!strings.EqualFold(strings.TrimSpace(existingItem.Checksum), strings.TrimSpace(checksum)) ||
			existingItem.SizeBytes != size

		if !isChanged {
			finalize.SkippedCount++
		} else if !hasExisting || existingItem.IsDeleted {
			finalize.CreatedCount++
		} else {
			finalize.UpdatedCount++
		}

		upserts = append(upserts, store.CloudObjectIndexRecord{
			SourceID:           claim.SourceID,
			Provider:           claim.Provider,
			ExternalObjectID:   objectID,
			ExternalParentID:   strings.TrimSpace(obj.ExternalParentID),
			ExternalPath:       strings.TrimSpace(obj.ExternalPath),
			ExternalName:       strings.TrimSpace(obj.ExternalName),
			ExternalKind:       kind,
			ExternalVersion:    strings.TrimSpace(obj.ExternalVersion),
			ExternalModifiedAt: obj.ExternalModifiedAt,
			LocalRelPath:       strings.TrimSpace(localRel),
			LocalAbsPath:       localAbs,
			Checksum:           strings.TrimSpace(checksum),
			SizeBytes:          size,
			IsDeleted:          false,
			LastSyncedAt:       &now,
			ProviderMeta:       obj.ProviderMeta,
		})
		pathOwner[localRel] = objectID

		if isDir || !isChanged {
			continue
		}
		eventType := "modified"
		if !hasExisting || existingItem.IsDeleted {
			eventType = "created"
		}
		events = append(events, model.FileEvent{
			SourceID:       claim.SourceID,
			EventType:      eventType,
			Path:           localAbs,
			IsDir:          false,
			OccurredAt:     now.Add(time.Duration(idx) * time.Nanosecond),
			OriginType:     string(model.OriginTypeCloudSync),
			OriginPlatform: strings.ToUpper(strings.TrimSpace(claim.Provider)),
			OriginRef:      objectID,
		})
	}
	if !manualScopeEnabled {
		for _, existingItem := range existing {
			if existingItem.IsDeleted {
				continue
			}
			id := strings.TrimSpace(existingItem.ExternalObjectID)
			if id == "" {
				continue
			}
			if _, ok := seenIDs[id]; ok {
				continue
			}
			deleteIDs = append(deleteIDs, id)
			finalize.DeletedCount++
			if isDirKind(existingItem.ExternalKind) {
				_ = mirror.DeletePath(strings.TrimSpace(existingItem.LocalAbsPath), true)
				continue
			}
			_ = mirror.DeletePath(strings.TrimSpace(existingItem.LocalAbsPath), false)
			events = append(events, model.FileEvent{
				SourceID:       claim.SourceID,
				EventType:      "deleted",
				Path:           strings.TrimSpace(existingItem.LocalAbsPath),
				IsDir:          false,
				OccurredAt:     now.Add(time.Duration(len(events)) * time.Nanosecond),
				OriginType:     string(model.OriginTypeCloudSync),
				OriginPlatform: strings.ToUpper(strings.TrimSpace(claim.Provider)),
				OriginRef:      id,
			})
		}
	} else {
		r.log.Info("cloud sync delete sweep skipped by manual scope",
			zap.String("source_id", claim.SourceID),
			zap.String("run_id", run.RunID),
			zap.Int("skipped_by_manual_scope", skippedByManualScope),
		)
	}

	if err := r.store.UpsertCloudObjectIndexBatch(ctx, claim.SourceID, claim.Provider, upserts, now); err != nil {
		finalize.ErrorCode = "INDEX_UPSERT_FAILED"
		finalize.ErrorMessage = err.Error()
		return
	}
	if err := r.store.MarkCloudObjectsDeleted(ctx, claim.SourceID, deleteIDs, now); err != nil {
		finalize.ErrorCode = "INDEX_DELETE_MARK_FAILED"
		finalize.ErrorMessage = err.Error()
		return
	}
	if err := r.store.EmitCloudFileEvents(ctx, events); err != nil {
		finalize.ErrorCode = "EMIT_EVENTS_FAILED"
		finalize.ErrorMessage = err.Error()
		return
	}
	r.log.Info("cloud sync persistence summary",
		zap.String("source_id", claim.SourceID),
		zap.String("run_id", run.RunID),
		zap.Int("upsert_records", len(upserts)),
		zap.Int("deleted_records", len(deleteIDs)),
		zap.Int("emitted_events", len(events)),
		zap.Int("skipped_by_manual_scope", skippedByManualScope),
	)

	if finalize.FailedCount > 0 {
		finalize.Status = "PARTIAL_SUCCESS"
		finalize.ErrorCode = "OBJECT_PARTIAL_FAILED"
		finalize.ErrorMessage = strings.Join(errorMessages, "; ")
		return
	}
	finalize.Status = "SUCCEEDED"
	finalize.ErrorCode = ""
	finalize.ErrorMessage = ""
}

func includeObjectDecision(obj provider.RemoteObject, includes, excludes []string) objectFilterDecision {
	kind := normalizeKind(obj.ExternalKind, obj.ProviderMeta)
	candidates := objectMatchCandidates(obj)
	decision := objectFilterDecision{
		Kind:       kind,
		Candidates: candidates,
	}
	if isDirKind(kind) {
		if ok, pattern, candidate := matchesAnyPattern(excludes, candidates...); ok {
			decision.Reason = "excluded_by_pattern"
			decision.MatchedPattern = pattern
			decision.MatchedCandidate = candidate
			return decision
		}
		decision.Include = true
		decision.Reason = "directory_passthrough"
		return decision
	}
	if len(includes) > 0 {
		if ok, pattern, candidate := matchesAnyPattern(includes, candidates...); !ok {
			decision.Reason = "include_not_matched"
			return decision
		} else {
			decision.Reason = "included_by_pattern"
			decision.MatchedPattern = pattern
			decision.MatchedCandidate = candidate
		}
	}
	if ok, pattern, candidate := matchesAnyPattern(excludes, candidates...); ok {
		decision.Reason = "excluded_by_pattern"
		decision.MatchedPattern = pattern
		decision.MatchedCandidate = candidate
		return decision
	}
	decision.Include = true
	if decision.Reason == "" {
		decision.Reason = "included_no_include_rules"
	}
	return decision
}

func matchesPattern(pattern string, candidates ...string) bool {
	ok, _ := matchPatternCandidate(pattern, candidates...)
	return ok
}

func matchPatternCandidate(pattern string, candidates ...string) (bool, string) {
	pattern = strings.TrimSpace(pattern)
	if pattern == "" {
		return false, ""
	}
	altPattern := ""
	if strings.HasPrefix(pattern, "**/") {
		altPattern = strings.TrimPrefix(pattern, "**/")
	}
	for _, raw := range candidates {
		p := strings.Trim(strings.ReplaceAll(strings.TrimSpace(raw), "\\", "/"), "/")
		if p == "" {
			continue
		}
		if ok, _ := path.Match(pattern, p); ok {
			return true, p
		}
		if ok, _ := path.Match(pattern, path.Base(p)); ok {
			return true, p
		}
		if strings.HasPrefix(pattern, "**/") {
			if ok, _ := path.Match(strings.TrimPrefix(pattern, "**/"), path.Base(p)); ok {
				return true, p
			}
		}
		if altPattern != "" {
			if ok, _ := path.Match(altPattern, p); ok {
				return true, p
			}
			if ok, _ := path.Match(altPattern, path.Base(p)); ok {
				return true, p
			}
		}
	}
	return false, ""
}

func matchesAnyPattern(patterns []string, candidates ...string) (bool, string, string) {
	for _, rawPattern := range patterns {
		pattern := strings.TrimSpace(rawPattern)
		if pattern == "" {
			continue
		}
		if ok, candidate := matchPatternCandidate(pattern, candidates...); ok {
			return true, pattern, candidate
		}
	}
	return false, "", ""
}

func objectMatchCandidates(obj provider.RemoteObject) []string {
	kind := normalizeKind(obj.ExternalKind, obj.ProviderMeta)
	remotePath := strings.Trim(strings.ReplaceAll(strings.TrimSpace(obj.ExternalPath), "\\", "/"), "/")
	remoteName := strings.Trim(strings.ReplaceAll(strings.TrimSpace(obj.ExternalName), "\\", "/"), "/")

	ordered := make([]string, 0, 12)
	seen := make(map[string]struct{}, 12)
	appendUnique := func(v string) {
		v = strings.Trim(strings.ReplaceAll(strings.TrimSpace(v), "\\", "/"), "/")
		if v == "" {
			return
		}
		if _, ok := seen[v]; ok {
			return
		}
		seen[v] = struct{}{}
		ordered = append(ordered, v)
	}

	appendUnique(remotePath)
	appendUnique(path.Base(remotePath))
	appendUnique(remoteName)
	appendUnique(path.Base(remoteName))

	primary := remotePath
	if primary == "" {
		primary = remoteName
	}
	ext := strings.ToLower(strings.TrimSpace(path.Ext(primary)))
	if ext != "" {
		appendUnique("ext:" + strings.TrimPrefix(ext, "."))
	}

	for _, suffix := range kindMatchSuffixes(kind) {
		if suffix == "" {
			continue
		}
		suffix = strings.ToLower(strings.TrimSpace(suffix))
		if primary != "" && path.Ext(primary) == "" {
			appendUnique(primary + suffix)
			appendUnique(path.Base(primary + suffix))
		}
		if remoteName != "" && path.Ext(remoteName) == "" {
			appendUnique(remoteName + suffix)
			appendUnique(path.Base(remoteName + suffix))
		}
		appendUnique("ext:" + strings.TrimPrefix(suffix, "."))
	}

	if kind != "" {
		appendUnique("kind:" + kind)
	}
	if kind == "file" && ext != "" {
		appendUnique("kind:" + strings.TrimPrefix(ext, "."))
	}
	return ordered
}

func kindMatchSuffixes(kind string) []string {
	switch strings.ToLower(strings.TrimSpace(kind)) {
	case "docx":
		return []string{".docx"}
	case "doc":
		return []string{".doc"}
	case "sheet":
		return []string{".xlsx", ".xls"}
	case "slides":
		return []string{".pptx", ".ppt"}
	case "pdf":
		return []string{".pdf"}
	default:
		return nil
	}
}

func normalizeKind(kind string, meta map[string]any) string {
	kind = strings.ToLower(strings.TrimSpace(kind))
	if kind != "" {
		return kind
	}
	objType := strings.ToLower(strings.TrimSpace(stringOption(meta, "obj_type")))
	if objType != "" {
		return objType
	}
	return "file"
}

func isDirKind(kind string) bool {
	switch strings.ToLower(strings.TrimSpace(kind)) {
	case "folder", "directory", "dir", "wiki", "space":
		return true
	default:
		return false
	}
}

func sanitizeRelativePath(externalPath, externalName, objectID, kind string) string {
	rel := strings.TrimSpace(externalPath)
	if rel == "" {
		rel = strings.TrimSpace(externalName)
	}
	rel = strings.ReplaceAll(rel, "\\", "/")
	if rel == "" {
		rel = objectID
	}
	rel = strings.TrimPrefix(path.Clean("/"+rel), "/")
	if rel == "" || rel == "." || strings.HasPrefix(rel, "../") || rel == ".." {
		rel = sanitizeName(firstNonEmptyString(externalName, objectID))
	}
	if !isDirKind(kind) && path.Ext(rel) == "" {
		switch strings.ToLower(strings.TrimSpace(kind)) {
		case "doc", "docx":
			rel += ".md"
		}
	}
	return rel
}

func resolvePathCollision(relPath, objectID string, owner map[string]string) string {
	relPath = strings.Trim(strings.TrimSpace(relPath), "/")
	if relPath == "" {
		relPath = objectID
	}
	if owner == nil {
		return relPath
	}
	currentOwner := strings.TrimSpace(owner[relPath])
	if currentOwner == "" || currentOwner == strings.TrimSpace(objectID) {
		return relPath
	}
	dir := path.Dir(relPath)
	base := path.Base(relPath)
	ext := path.Ext(base)
	name := strings.TrimSuffix(base, ext)
	suffix := shortHash(objectID)
	candidate := path.Join(dir, name+"_"+suffix+ext)
	if dir == "." || dir == "/" {
		candidate = name + "_" + suffix + ext
	}
	i := 1
	for {
		ownerID := strings.TrimSpace(owner[candidate])
		if ownerID == "" || ownerID == strings.TrimSpace(objectID) {
			return candidate
		}
		candidate = path.Join(dir, fmt.Sprintf("%s_%s_%d%s", name, suffix, i, ext))
		if dir == "." || dir == "/" {
			candidate = fmt.Sprintf("%s_%s_%d%s", name, suffix, i, ext)
		}
		i++
	}
}

func isPathUnderRoot(p, root string) bool {
	p = filepath.Clean(strings.TrimSpace(p))
	root = filepath.Clean(strings.TrimSpace(root))
	if p == "" || root == "" || p == "." || root == "." {
		return false
	}
	if root == string(filepath.Separator) {
		return strings.HasPrefix(p, string(filepath.Separator))
	}
	return p == root || strings.HasPrefix(p, root+string(filepath.Separator))
}

func sha256Hex(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func shortHash(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:4])
}

func appendError(errs []string, msg string) []string {
	msg = strings.TrimSpace(msg)
	if msg == "" {
		return errs
	}
	if len(errs) >= 5 {
		return errs
	}
	return append(errs, msg)
}

func normalizeManualScopePaths(rawPaths []string, sourceID, mirrorRoot string) []string {
	if len(rawPaths) == 0 {
		return nil
	}
	mirrorRoot = filepath.Clean(strings.TrimSpace(mirrorRoot))
	if mirrorRoot == "" || mirrorRoot == "." {
		return nil
	}
	unique := make(map[string]struct{}, len(rawPaths))
	out := make([]string, 0, len(rawPaths))
	for _, raw := range rawPaths {
		path := strings.TrimSpace(raw)
		if path == "" {
			continue
		}
		path = sourcelayout.ResolveCloudPublicPath(path, sourceID, mirrorRoot)
		path = filepath.Clean(path)
		if path == "" || path == "." || !isPathUnderRoot(path, mirrorRoot) {
			continue
		}
		if _, ok := unique[path]; ok {
			continue
		}
		unique[path] = struct{}{}
		out = append(out, path)
	}
	return out
}

func pathInRequestedScope(target string, scopePaths []string) bool {
	target = filepath.Clean(strings.TrimSpace(target))
	if target == "" || target == "." {
		return false
	}
	for _, scope := range scopePaths {
		scope = filepath.Clean(strings.TrimSpace(scope))
		if scope == "" || scope == "." {
			continue
		}
		if target == scope || strings.HasPrefix(target, scope+string(filepath.Separator)) {
			return true
		}
	}
	return false
}

func appendRemoteObjectSample(samples []string, obj provider.RemoteObject, limit int) []string {
	if limit <= 0 || len(samples) >= limit {
		return samples
	}
	samples = append(samples, remoteObjectLogLine(obj))
	return samples
}

type objectFilterDecision struct {
	Include          bool
	Reason           string
	MatchedPattern   string
	MatchedCandidate string
	Kind             string
	Candidates       []string
}

func appendFilterDecisionSample(samples []string, obj provider.RemoteObject, decision objectFilterDecision, limit int) []string {
	if limit <= 0 || len(samples) >= limit {
		return samples
	}
	const maxCandidates = 8
	used := decision.Candidates
	if len(used) > maxCandidates {
		used = used[:maxCandidates]
	}
	samples = append(samples, fmt.Sprintf(
		"id=%s decision=%s include=%t kind=%s matched_pattern=%s matched_candidate=%s candidates=%s",
		strings.TrimSpace(obj.ExternalObjectID),
		strings.TrimSpace(decision.Reason),
		decision.Include,
		strings.TrimSpace(decision.Kind),
		strings.TrimSpace(decision.MatchedPattern),
		strings.TrimSpace(decision.MatchedCandidate),
		strings.Join(used, "|"),
	))
	return samples
}

func describeRemoteObjectsForLog(objects []provider.RemoteObject, limit int) ([]string, int) {
	if limit <= 0 {
		limit = 200
	}
	if len(objects) == 0 {
		return []string{}, 0
	}
	count := len(objects)
	used := count
	if used > limit {
		used = limit
	}
	out := make([]string, 0, used)
	for i := 0; i < used; i++ {
		out = append(out, remoteObjectLogLine(objects[i]))
	}
	return out, count - used
}

func remoteObjectLogLine(obj provider.RemoteObject) string {
	return fmt.Sprintf(
		"id=%s parent=%s name=%s kind=%s path=%s version=%s size=%d",
		strings.TrimSpace(obj.ExternalObjectID),
		strings.TrimSpace(obj.ExternalParentID),
		strings.TrimSpace(obj.ExternalName),
		strings.TrimSpace(obj.ExternalKind),
		strings.TrimSpace(obj.ExternalPath),
		strings.TrimSpace(obj.ExternalVersion),
		obj.SizeBytes,
	)
}

func (r *Runner) withRetry(ctx context.Context, opName string, fn func() error) error {
	attempts := r.cfg.RetryMaxAttempts
	if attempts <= 0 {
		attempts = 1
	}
	base := r.cfg.RetryBaseBackoff
	if base <= 0 {
		base = time.Second
	}
	maxBackoff := r.cfg.RetryMaxBackoff
	if maxBackoff <= 0 {
		maxBackoff = 30 * time.Second
	}
	var lastErr error
	for i := 1; i <= attempts; i++ {
		if err := fn(); err == nil {
			return nil
		} else {
			lastErr = err
		}
		if i >= attempts {
			break
		}
		backoff := base << (i - 1)
		if backoff > maxBackoff {
			backoff = maxBackoff
		}
		r.log.Warn("cloud sync operation retry",
			zap.String("op", opName),
			zap.Int("attempt", i),
			zap.Int("max_attempts", attempts),
			zap.Duration("backoff", backoff),
			zap.Error(lastErr),
		)
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(backoff):
		}
	}
	return lastErr
}

func stringOption(m map[string]any, key string) string {
	if len(m) == 0 {
		return ""
	}
	v, ok := m[key]
	if !ok || v == nil {
		return ""
	}
	switch x := v.(type) {
	case string:
		return strings.TrimSpace(x)
	default:
		return strings.TrimSpace(fmt.Sprintf("%v", v))
	}
}

func sanitizeName(v string) string {
	v = strings.TrimSpace(v)
	if v == "" {
		return "unnamed"
	}
	v = strings.ReplaceAll(v, "/", "_")
	v = strings.ReplaceAll(v, "\\", "_")
	v = strings.ReplaceAll(v, "\n", "_")
	v = strings.ReplaceAll(v, "\r", "_")
	return v
}

func firstNonEmptyString(values ...string) string {
	for _, item := range values {
		if strings.TrimSpace(item) != "" {
			return strings.TrimSpace(item)
		}
	}
	return ""
}
