package preference

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"gorm.io/gorm"

	"lazyrag/core/algo"
	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/evolution"
	appLog "lazyrag/core/log"
	"lazyrag/core/store"
)

type suggestionRequest struct {
	SessionID   string                        `json:"session_id"`
	Suggestions []evolution.SuggestionPayload `json:"suggestions"`
}

type generateRequest struct {
	SuggestionIDs []string `json:"suggestion_ids"`
	UserInstruct  string   `json:"user_instruct"`
}

type upsertRequest struct {
	Content *string `json:"content"`
}

type draftPreviewResponse struct {
	DraftStatus        string `json:"draft_status"`
	DraftSourceVersion int64  `json:"draft_source_version"`
	CurrentContent     string `json:"current_content"`
	DraftContent       string `json:"draft_content"`
	Diff               string `json:"diff"`
}

func Upsert(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}
	userID := strings.TrimSpace(store.UserID(r))
	userName := strings.TrimSpace(store.UserName(r))
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	var req upsertRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if req.Content == nil {
		common.ReplyErr(w, "content required", http.StatusBadRequest)
		return
	}

	existing, err := evolution.LoadSystemUserPreference(r.Context(), db, userID)
	if err != nil && err != gorm.ErrRecordNotFound {
		common.ReplyErr(w, "query user_preference failed", http.StatusInternalServerError)
		return
	}
	if existing != nil && strings.TrimSpace(existing.DraftStatus) == "pending_confirm" {
		common.ReplyErr(w, "user_preference draft already pending_confirm", http.StatusConflict)
		return
	}

	now := time.Now()
	content := *req.Content
	if existing == nil {
		row := orm.SystemUserPreference{
			ID:            evolution.NewID(),
			UserID:        userID,
			Content:       content,
			ContentHash:   evolution.HashContent(content),
			Version:       1,
			UpdatedBy:     userID,
			UpdatedByName: userName,
			CreatedAt:     now,
			UpdatedAt:     now,
		}
		if err := db.WithContext(r.Context()).Create(&row).Error; err != nil {
			common.ReplyErr(w, "create user_preference failed", http.StatusInternalServerError)
			return
		}
		suggestionStatus, err := evolution.ManagedSuggestionStatusForResource(r.Context(), db, userID, evolution.ResourceTypeUserPreference)
		if err != nil {
			common.ReplyErr(w, "query user_preference failed", http.StatusInternalServerError)
			return
		}
		common.ReplyOK(w, evolution.NewManagedStateItem(evolution.ResourceTypeUserPreference, &row, suggestionStatus))
		return
	}

	update := map[string]any{
		"content":         content,
		"content_hash":    evolution.HashContent(content),
		"version":         existing.Version + 1,
		"updated_by":      userID,
		"updated_by_name": userName,
		"updated_at":      now,
	}
	if err := db.WithContext(r.Context()).Model(&orm.SystemUserPreference{}).Where("id = ? AND version = ?", existing.ID, existing.Version).Updates(update).Error; err != nil {
		common.ReplyErr(w, "update user_preference failed", http.StatusInternalServerError)
		return
	}
	existing.Content = content
	existing.ContentHash = evolution.HashContent(content)
	existing.Version++
	existing.UpdatedBy = userID
	existing.UpdatedByName = userName
	existing.UpdatedAt = now
	suggestionStatus, err := evolution.ManagedSuggestionStatusForResource(r.Context(), db, userID, evolution.ResourceTypeUserPreference)
	if err != nil {
		common.ReplyErr(w, "query user_preference failed", http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, evolution.NewManagedStateItem(evolution.ResourceTypeUserPreference, existing, suggestionStatus))
}

func DraftPreview(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}

	userID := strings.TrimSpace(store.UserID(r))
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	row, err := evolution.LoadSystemUserPreference(r.Context(), db, userID)
	if err == gorm.ErrRecordNotFound {
		common.ReplyErr(w, "user_preference not found", http.StatusNotFound)
		return
	}
	if err != nil {
		common.ReplyErr(w, "query user_preference failed", http.StatusInternalServerError)
		return
	}
	if strings.TrimSpace(row.DraftStatus) != "pending_confirm" {
		common.ReplyErr(w, "user_preference draft not found", http.StatusNotFound)
		return
	}

	diff, err := evolution.BuildContentDiff(row.Content, row.DraftContent)
	if err != nil {
		common.ReplyErr(w, "build user_preference diff failed", http.StatusInternalServerError)
		return
	}

	common.ReplyOK(w, draftPreviewResponse{
		DraftStatus:        row.DraftStatus,
		DraftSourceVersion: row.DraftSourceVersion,
		CurrentContent:     row.Content,
		DraftContent:       row.DraftContent,
		Diff:               diff,
	})
}

func Suggestion(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}

	var req suggestionRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	req.SessionID = strings.TrimSpace(req.SessionID)
	appLog.Logger.Info().
		Str("route", "/user_preference/suggestion").
		Str("session_id", req.SessionID).
		Int("suggestion_count", len(req.Suggestions)).
		Msg("internal user preference mutation request received")
	if req.SessionID == "" {
		common.ReplyErr(w, "session_id required", http.StatusBadRequest)
		return
	}
	if len(req.Suggestions) == 0 || len(req.Suggestions) > 5 {
		common.ReplyErr(w, "suggestions length must be between 1 and 5", http.StatusBadRequest)
		return
	}
	for _, item := range req.Suggestions {
		if strings.TrimSpace(item.Title) == "" || strings.TrimSpace(item.Content) == "" {
			common.ReplyErr(w, "suggestion title/content required", http.StatusBadRequest)
			return
		}
	}

	userID, userName, err := evolution.ResolveSessionUser(r.Context(), db, req.SessionID)
	if err != nil || strings.TrimSpace(userID) == "" {
		appLog.Logger.Warn().
			Err(err).
			Str("route", "/user_preference/suggestion").
			Str("session_id", req.SessionID).
			Msg("internal user preference suggestion request rejected: unable to resolve session user")
		common.ReplyErr(w, "unable to resolve session user", http.StatusBadRequest)
		return
	}
	resource, err := evolution.EnsureSystemUserPreference(r.Context(), db, userID, userName)
	if err != nil {
		common.ReplyErr(w, "query user_preference failed", http.StatusInternalServerError)
		return
	}
	resourceKey := evolution.SystemResourceKey(evolution.ResourceTypeUserPreference)
	snapshot, err := evolution.FindSnapshot(r.Context(), db, req.SessionID, evolution.ResourceTypeUserPreference, resourceKey)
	if err != nil {
		common.ReplyErr(w, "session snapshot not found", http.StatusNotFound)
		return
	}

	status := evolution.SuggestionStatusPendingReview
	invalidReason := ""
	currentHash := firstNonEmpty(strings.TrimSpace(resource.ContentHash), evolution.HashContent(resource.Content))
	if currentHash != snapshot.SnapshotHash {
		status = evolution.SuggestionStatusInvalid
		invalidReason = "snapshot hash mismatch"
	}

	rows := make([]orm.ResourceSuggestion, 0, len(req.Suggestions))
	resp := make([]evolution.RecordedSuggestion, 0, len(req.Suggestions))
	for _, item := range req.Suggestions {
		row := evolution.BuildSuggestionRecord(userID, evolution.ResourceTypeUserPreference, resourceKey, evolution.SuggestionActionModify, req.SessionID, status)
		row.SnapshotHash = snapshot.SnapshotHash
		row.Title = strings.TrimSpace(item.Title)
		row.Content = strings.TrimSpace(item.Content)
		row.Reason = strings.TrimSpace(item.Reason)
		row.InvalidReason = invalidReason
		rows = append(rows, row)
		resp = append(resp, evolution.RecordedSuggestion{
			ID:            row.ID,
			Status:        row.Status,
			InvalidReason: row.InvalidReason,
		})
	}
	if err := db.WithContext(r.Context()).Create(&rows).Error; err != nil {
		appLog.Logger.Error().
			Err(err).
			Str("route", "/user_preference/suggestion").
			Str("session_id", req.SessionID).
			Str("user_id", userID).
			Msg("internal user preference suggestion request failed to persist")
		common.ReplyErr(w, "create suggestions failed", http.StatusInternalServerError)
		return
	}
	appLog.Logger.Info().
		Str("route", "/user_preference/suggestion").
		Str("session_id", req.SessionID).
		Str("user_id", userID).
		Int("created_count", len(rows)).
		Msg("internal user preference suggestion request persisted")
	common.ReplyOK(w, map[string]any{"items": resp})
}

func Generate(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}
	userID := strings.TrimSpace(store.UserID(r))
	userName := strings.TrimSpace(store.UserName(r))
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	var req generateRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	req.SuggestionIDs = compactIDs(req.SuggestionIDs)
	req.UserInstruct = strings.TrimSpace(req.UserInstruct)
	if req.UserInstruct == "" {
		common.ReplyErr(w, "user_instruct required", http.StatusBadRequest)
		return
	}

	row, err := evolution.EnsureSystemUserPreference(r.Context(), db, userID, userName)
	if err != nil {
		common.ReplyErr(w, "query user_preference failed", http.StatusInternalServerError)
		return
	}

	suggestions, err := evolution.LoadApprovedSuggestions(r.Context(), db, userID, evolution.ResourceTypeUserPreference, evolution.SystemResourceKey(evolution.ResourceTypeUserPreference), req.SuggestionIDs)
	if err != nil {
		common.ReplyErr(w, "query suggestions failed", http.StatusInternalServerError)
		return
	}
	if len(suggestions) == 0 {
		common.ReplyErr(w, "no accepted suggestions found", http.StatusBadRequest)
		return
	}

	generated, err := algo.GenerateUserPreference(r.Context(), algo.MemoryGenerateRequest{
		Content:      row.Content,
		Suggestions:  toAlgoSuggestions(suggestions),
		UserInstruct: req.UserInstruct,
	})
	if err != nil {
		common.ReplyErr(w, "user_preference generate failed: "+err.Error(), http.StatusBadGateway)
		return
	}

	now := time.Now()
	ids := suggestionIDs(suggestions)
	update := map[string]any{
		"draft_content":        generated,
		"draft_source_version": row.Version,
		"draft_status":         "pending_confirm",
		"draft_updated_at":     now,
		"updated_by":           userID,
		"updated_by_name":      userName,
		"updated_at":           now,
		"ext":                  evolution.WithDraftSuggestionIDs(row.Ext, ids),
	}
	if err := db.WithContext(r.Context()).Model(&orm.SystemUserPreference{}).Where("id = ?", row.ID).Updates(update).Error; err != nil {
		common.ReplyErr(w, "update user_preference draft failed", http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, map[string]any{
		"draft_status":         "pending_confirm",
		"draft_source_version": row.Version,
		"draft_content":        generated,
		"suggestion_ids":       ids,
	})
}

func Confirm(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}
	userID := strings.TrimSpace(store.UserID(r))
	userName := strings.TrimSpace(store.UserName(r))
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	row, err := evolution.EnsureSystemUserPreference(r.Context(), db, userID, userName)
	if err != nil {
		common.ReplyErr(w, "query user_preference failed", http.StatusInternalServerError)
		return
	}
	if strings.TrimSpace(row.DraftStatus) != "pending_confirm" {
		common.ReplyErr(w, "user_preference draft not found", http.StatusNotFound)
		return
	}
	if row.Version != row.DraftSourceVersion {
		common.ReplyErr(w, "user_preference draft version conflict", http.StatusConflict)
		return
	}

	ids := evolution.DraftSuggestionIDs(row.Ext)
	now := time.Now()
	newContent := row.DraftContent
	update := map[string]any{
		"content":              newContent,
		"content_hash":         evolution.HashContent(newContent),
		"version":              row.Version + 1,
		"draft_content":        "",
		"draft_source_version": 0,
		"draft_status":         "",
		"draft_updated_at":     nil,
		"updated_by":           userID,
		"updated_by_name":      userName,
		"updated_at":           now,
		"ext":                  evolution.WithDraftSuggestionIDs(row.Ext, nil),
	}
	if err := db.WithContext(r.Context()).Model(&orm.SystemUserPreference{}).Where("id = ? AND version = ?", row.ID, row.Version).Updates(update).Error; err != nil {
		common.ReplyErr(w, "confirm user_preference draft failed", http.StatusInternalServerError)
		return
	}
	if err := evolution.UpdateSuggestionStatus(r.Context(), db, ids, evolution.SuggestionStatusApplied); err != nil {
		common.ReplyErr(w, "update suggestion status failed", http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, map[string]any{
		"content": newContent,
		"version": row.Version + 1,
	})
}

func Discard(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}
	userID := strings.TrimSpace(store.UserID(r))
	userName := strings.TrimSpace(store.UserName(r))
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	row, err := evolution.EnsureSystemUserPreference(r.Context(), db, userID, userName)
	if err != nil {
		common.ReplyErr(w, "query user_preference failed", http.StatusInternalServerError)
		return
	}
	if strings.TrimSpace(row.DraftStatus) != "pending_confirm" {
		common.ReplyErr(w, "user_preference draft not found", http.StatusNotFound)
		return
	}

	ids := evolution.DraftSuggestionIDs(row.Ext)
	now := time.Now()
	update := map[string]any{
		"draft_content":        "",
		"draft_source_version": 0,
		"draft_status":         "",
		"draft_updated_at":     nil,
		"updated_by":           userID,
		"updated_by_name":      userName,
		"updated_at":           now,
		"ext":                  evolution.WithDraftSuggestionIDs(row.Ext, nil),
	}
	if err := db.WithContext(r.Context()).Model(&orm.SystemUserPreference{}).Where("id = ?", row.ID).Updates(update).Error; err != nil {
		common.ReplyErr(w, "discard user_preference draft failed", http.StatusInternalServerError)
		return
	}
	if err := evolution.UpdateSuggestionStatus(r.Context(), db, ids, evolution.SuggestionStatusDiscarded); err != nil {
		common.ReplyErr(w, "update suggestion status failed", http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, map[string]any{"discarded": true})
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func compactIDs(ids []string) []string {
	seen := make(map[string]struct{}, len(ids))
	out := make([]string, 0, len(ids))
	for _, id := range ids {
		id = strings.TrimSpace(id)
		if id == "" {
			continue
		}
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		out = append(out, id)
	}
	return out
}

func suggestionIDs(rows []orm.ResourceSuggestion) []string {
	out := make([]string, 0, len(rows))
	for _, row := range rows {
		if strings.TrimSpace(row.ID) != "" {
			out = append(out, strings.TrimSpace(row.ID))
		}
	}
	return out
}

func toAlgoSuggestions(rows []orm.ResourceSuggestion) []algo.Suggestion {
	out := make([]algo.Suggestion, 0, len(rows))
	for _, row := range rows {
		out = append(out, algo.Suggestion{
			Title:   row.Title,
			Content: row.Content,
			Reason:  row.Reason,
		})
	}
	return out
}
