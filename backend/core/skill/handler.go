package skill

import (
	"encoding/json"
	"net/http"
	"strings"

	"gorm.io/gorm"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/evolution"
	appLog "lazyrag/core/log"
	"lazyrag/core/store"
)

type suggestionRequest struct {
	SessionID   string                        `json:"session_id"`
	Category    string                        `json:"category"`
	SkillName   string                        `json:"skill_name"`
	Suggestions []evolution.SuggestionPayload `json:"suggestions"`
}

type createRequest struct {
	SessionID string `json:"session_id"`
	Category  string `json:"category"`
	SkillName string `json:"skill_name"`
	Content   string `json:"content"`
}

type removeRequest struct {
	SessionID string `json:"session_id"`
	Category  string `json:"category"`
	SkillName string `json:"skill_name"`
}

func payloadForLog(v any) string {
	b, err := json.Marshal(v)
	if err != nil {
		return ""
	}
	return string(b)
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
	req.Category = strings.TrimSpace(req.Category)
	req.SkillName = strings.TrimSpace(req.SkillName)
	appLog.Logger.Info().
		Str("route", "/skill/suggestion").
		Str("session_id", req.SessionID).
		Str("category", req.Category).
		Str("skill_name", req.SkillName).
		Int("suggestion_count", len(req.Suggestions)).
		Msg("internal skill mutation request received")
	if req.SessionID == "" || req.Category == "" || req.SkillName == "" {
		appLog.Logger.Warn().
			Str("route", "/skill/suggestion").
			Str("session_id", req.SessionID).
			Str("category", req.Category).
			Str("skill_name", req.SkillName).
			Msg("internal skill suggestion request rejected: missing required fields")
		common.ReplyErr(w, "session_id/category/skill_name required", http.StatusBadRequest)
		return
	}
	if len(req.Suggestions) == 0 || len(req.Suggestions) > 5 {
		appLog.Logger.Warn().
			Str("route", "/skill/suggestion").
			Str("session_id", req.SessionID).
			Int("suggestion_count", len(req.Suggestions)).
			Msg("internal skill suggestion request rejected: invalid suggestion count")
		common.ReplyErr(w, "suggestions length must be between 1 and 5", http.StatusBadRequest)
		return
	}
	for _, item := range req.Suggestions {
		if strings.TrimSpace(item.Title) == "" || strings.TrimSpace(item.Content) == "" {
			common.ReplyErr(w, "suggestion title/content required", http.StatusBadRequest)
			return
		}
	}

	userID, _, err := evolution.ResolveSessionUser(r.Context(), db, req.SessionID)
	if err != nil || strings.TrimSpace(userID) == "" {
		appLog.Logger.Warn().
			Err(err).
			Str("route", "/skill/suggestion").
			Str("session_id", req.SessionID).
			Msg("internal skill suggestion request rejected: unable to resolve session user")
		common.ReplyErr(w, "unable to resolve session user", http.StatusBadRequest)
		return
	}

	state, err := evolution.LoadParentSkillState(r.Context(), db, userID, req.Category, req.SkillName)
	if err != nil {
		if err == gorm.ErrRecordNotFound {
			common.ReplyErr(w, "skill not found", http.StatusNotFound)
			return
		}
		common.ReplyErr(w, "query skill failed", http.StatusInternalServerError)
		return
	}
	snapshot, err := evolution.FindSnapshot(r.Context(), db, req.SessionID, evolution.ResourceTypeSkill, state.RelativePath)
	if err != nil {
		common.ReplyErr(w, "session snapshot not found", http.StatusNotFound)
		return
	}

	status := evolution.SuggestionStatusPendingReview
	invalidReason := ""
	if state.ContentHash != snapshot.SnapshotHash {
		status = evolution.SuggestionStatusInvalid
		invalidReason = "snapshot hash mismatch"
	}

	rows := make([]orm.ResourceSuggestion, 0, len(req.Suggestions))
	result := make([]evolution.RecordedSuggestion, 0, len(req.Suggestions))
	for _, item := range req.Suggestions {
		row := evolution.BuildSuggestionRecord(userID, evolution.ResourceTypeSkill, state.RelativePath, evolution.SuggestionActionModify, req.SessionID, status)
		row.Category = req.Category
		row.ParentSkillName = strings.TrimSpace(state.Resource.ParentSkillName)
		if row.ParentSkillName == "" {
			row.ParentSkillName = strings.TrimSpace(state.Resource.SkillName)
		}
		row.SkillName = strings.TrimSpace(state.Resource.SkillName)
		row.FileExt = firstNonEmpty(strings.TrimSpace(state.Resource.FileExt), "md")
		row.RelativePath = state.RelativePath
		row.SnapshotHash = snapshot.SnapshotHash
		row.Title = strings.TrimSpace(item.Title)
		row.Content = strings.TrimSpace(item.Content)
		row.Reason = strings.TrimSpace(item.Reason)
		row.InvalidReason = invalidReason
		rows = append(rows, row)
		result = append(result, evolution.RecordedSuggestion{
			ID:            row.ID,
			Status:        row.Status,
			InvalidReason: row.InvalidReason,
		})
	}
	if err := db.WithContext(r.Context()).Create(&rows).Error; err != nil {
		appLog.Logger.Error().
			Err(err).
			Str("route", "/skill/suggestion").
			Str("session_id", req.SessionID).
			Str("user_id", userID).
			Str("category", req.Category).
			Str("skill_name", req.SkillName).
			Msg("internal skill suggestion request failed to persist")
		common.ReplyErr(w, "create suggestions failed", http.StatusInternalServerError)
		return
	}
	appLog.Logger.Info().
		Str("route", "/skill/suggestion").
		Str("session_id", req.SessionID).
		Str("user_id", userID).
		Str("category", req.Category).
		Str("skill_name", req.SkillName).
		Int("created_count", len(rows)).
		Msg("internal skill suggestion request persisted")
	common.ReplyOK(w, map[string]any{"items": result})
}

func Create(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}

	var req createRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	req.SessionID = strings.TrimSpace(req.SessionID)
	req.Category = strings.TrimSpace(req.Category)
	req.SkillName = strings.TrimSpace(req.SkillName)
	appLog.Logger.Info().
		Str("route", "/skill/create").
		Str("session_id", req.SessionID).
		Str("category", req.Category).
		Str("skill_name", req.SkillName).
		Msg("internal skill create request received")
	if req.SessionID == "" || req.Category == "" || req.SkillName == "" || strings.TrimSpace(req.Content) == "" {
		appLog.Logger.Warn().
			Str("route", "/skill/create").
			Str("session_id", req.SessionID).
			Str("category", req.Category).
			Str("skill_name", req.SkillName).
			Msg("internal skill create request rejected: missing required fields")
		common.ReplyErr(w, "session_id/category/skill_name/content required", http.StatusBadRequest)
		return
	}
	if err := validatePathSegment(req.SkillName); err != nil {
		common.ReplyErr(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validatePathSegment(req.Category); err != nil {
		common.ReplyErr(w, err.Error(), http.StatusBadRequest)
		return
	}

	userID, userName, err := evolution.ResolveSessionUser(r.Context(), db, req.SessionID)
	if err != nil || strings.TrimSpace(userID) == "" {
		appLog.Logger.Warn().
			Err(err).
			Str("route", "/skill/create").
			Str("session_id", req.SessionID).
			Msg("internal skill create request rejected: unable to resolve session user")
		common.ReplyErr(w, "unable to resolve session user", http.StatusBadRequest)
		return
	}

	description, err := validateParentSkillContent(req.SkillName, "", req.Content)
	if err != nil {
		replySkillError(w, err)
		return
	}

	createReq := createSkillRequest{
		Name:        req.SkillName,
		Description: description,
		Category:    req.Category,
		Content:     req.Content,
	}
	if err := createParentSkillWithContent(r.Context(), db, userID, userName, createReq, req.Content, description); err != nil {
		replySkillError(w, err)
		return
	}

	relativePath := parentRelativePath(req.Category, req.SkillName)
	var row orm.SkillResource
	if err := db.WithContext(r.Context()).Where("owner_user_id = ? AND relative_path = ?", userID, relativePath).Take(&row).Error; err != nil {
		common.ReplyErr(w, "query skill failed", http.StatusInternalServerError)
		return
	}
	item, err := getSkillDetail(r.Context(), db, userID, row.ID)
	if err != nil {
		appLog.Logger.Error().
			Err(err).
			Str("route", "/skill/create").
			Str("session_id", req.SessionID).
			Str("user_id", userID).
			Str("category", req.Category).
			Str("skill_name", req.SkillName).
			Msg("internal skill create succeeded but failed to load detail")
		common.ReplyErr(w, "query skill failed", http.StatusInternalServerError)
		return
	}
	appLog.Logger.Info().
		Str("route", "/skill/create").
		Str("session_id", req.SessionID).
		Str("user_id", userID).
		Str("category", req.Category).
		Str("skill_name", req.SkillName).
		Str("skill_id", row.ID).
		Msg("internal skill create request created skill directly")
	common.ReplyOK(w, item)
}

func Remove(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}

	var req removeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	req.SessionID = strings.TrimSpace(req.SessionID)
	req.Category = strings.TrimSpace(req.Category)
	req.SkillName = strings.TrimSpace(req.SkillName)
	appLog.Logger.Info().
		Str("route", "/skill/remove").
		Str("session_id", req.SessionID).
		Str("category", req.Category).
		Str("skill_name", req.SkillName).
		Str("payload", payloadForLog(req)).
		Msg("internal skill remove request received")
	if req.SessionID == "" || req.Category == "" || req.SkillName == "" {
		appLog.Logger.Warn().
			Str("route", "/skill/remove").
			Str("session_id", req.SessionID).
			Str("category", req.Category).
			Str("skill_name", req.SkillName).
			Msg("internal skill remove request rejected: missing required fields")
		common.ReplyErr(w, "session_id/category/skill_name required", http.StatusBadRequest)
		return
	}

	userID, _, err := evolution.ResolveSessionUser(r.Context(), db, req.SessionID)
	if err != nil || strings.TrimSpace(userID) == "" {
		appLog.Logger.Warn().
			Err(err).
			Str("route", "/skill/remove").
			Str("session_id", req.SessionID).
			Msg("internal skill remove request rejected: unable to resolve session user")
		common.ReplyErr(w, "unable to resolve session user", http.StatusBadRequest)
		return
	}

	state, err := evolution.LoadParentSkillState(r.Context(), db, userID, req.Category, req.SkillName)
	if err != nil {
		if err == gorm.ErrRecordNotFound {
			common.ReplyErr(w, "skill not found", http.StatusNotFound)
			return
		}
		common.ReplyErr(w, "query skill failed", http.StatusInternalServerError)
		return
	}
	snapshot, err := evolution.FindSnapshot(r.Context(), db, req.SessionID, evolution.ResourceTypeSkill, state.RelativePath)
	if err != nil {
		appLog.Logger.Warn().
			Err(err).
			Str("route", "/skill/remove").
			Str("session_id", req.SessionID).
			Str("user_id", userID).
			Str("category", req.Category).
			Str("skill_name", req.SkillName).
			Msg("internal skill remove request rejected: session snapshot not found")
		common.ReplyErr(w, "session snapshot not found", http.StatusNotFound)
		return
	}
	if state.ContentHash != snapshot.SnapshotHash {
		appLog.Logger.Warn().
			Str("route", "/skill/remove").
			Str("session_id", req.SessionID).
			Str("user_id", userID).
			Str("category", req.Category).
			Str("skill_name", req.SkillName).
			Str("current_hash", state.ContentHash).
			Str("snapshot_hash", snapshot.SnapshotHash).
			Msg("internal skill remove request rejected: snapshot hash mismatch")
		common.ReplyErr(w, "skill snapshot hash mismatch", http.StatusConflict)
		return
	}
	if err := deleteSkill(r.Context(), db, userID, state.Resource.ID); err != nil {
		appLog.Logger.Error().
			Err(err).
			Str("route", "/skill/remove").
			Str("session_id", req.SessionID).
			Str("user_id", userID).
			Str("category", req.Category).
			Str("skill_name", req.SkillName).
			Str("skill_id", state.Resource.ID).
			Msg("internal skill remove request failed to delete skill directly")
		replySkillError(w, err)
		return
	}
	appLog.Logger.Info().
		Str("route", "/skill/remove").
		Str("session_id", req.SessionID).
		Str("user_id", userID).
		Str("category", req.Category).
		Str("skill_name", req.SkillName).
		Str("skill_id", state.Resource.ID).
		Msg("internal skill remove request deleted skill directly")
	common.ReplyOK(w, map[string]any{"deleted": true})
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
