package skill

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"sort"
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

var (
	errDraftPreviewParentOnly = errors.New("only parent skill supports draft preview")
	errDraftPreviewNotFound   = errors.New("skill draft not found")
)

func List(w http.ResponseWriter, r *http.Request) {
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

	var parents []orm.SkillResource
	if err := db.WithContext(r.Context()).
		Where("owner_user_id = ? AND node_type = ?", userID, evolution.SkillNodeTypeParent).
		Order("updated_at DESC").
		Find(&parents).Error; err != nil {
		common.ReplyErr(w, "query skills failed", http.StatusInternalServerError)
		return
	}
	var children []orm.SkillResource
	if err := db.WithContext(r.Context()).
		Where("owner_user_id = ? AND node_type = ?", userID, evolution.SkillNodeTypeChild).
		Order("created_at ASC").
		Find(&children).Error; err != nil {
		common.ReplyErr(w, "query skills failed", http.StatusInternalServerError)
		return
	}
	suggestionStatusesByKey, err := loadSuggestionStatusesByKey(r.Context(), db, userID, parents)
	if err != nil {
		common.ReplyErr(w, "query skills failed", http.StatusInternalServerError)
		return
	}

	childMap := make(map[string][]orm.SkillResource)
	for _, child := range children {
		key := child.Category + "/" + child.ParentSkillName
		childMap[key] = append(childMap[key], child)
	}

	keyword := strings.TrimSpace(r.URL.Query().Get("keyword"))
	category := strings.TrimSpace(r.URL.Query().Get("category"))
	filterTags := compactStrings(r.URL.Query()["tags"])
	filtered := make([]map[string]any, 0, len(parents))
	for _, parent := range parents {
		if keyword != "" && !strings.Contains(strings.ToLower(parent.SkillName), strings.ToLower(keyword)) && !strings.Contains(strings.ToLower(parent.Description), strings.ToLower(keyword)) {
			continue
		}
		if category != "" && parent.Category != category {
			continue
		}
		parentTags := parseTags(parent.Tags)
		if len(filterTags) > 0 && !containsAllTags(parentTags, filterTags) {
			continue
		}
		key := parent.Category + "/" + parent.SkillName
		filtered = append(filtered, parentListResponse(parent, childMap[key], suggestionStatusesByKey[skillSuggestionResourceKey(parent)]))
	}

	page := parsePositiveInt(r.URL.Query().Get("page"), 1)
	pageSize := parsePositiveInt(r.URL.Query().Get("page_size"), 20)
	if pageSize > 100 {
		pageSize = 100
	}
	total := len(filtered)
	start := (page - 1) * pageSize
	if start > total {
		start = total
	}
	end := start + pageSize
	if end > total {
		end = total
	}
	common.ReplyOK(w, map[string]any{
		"items":     filtered[start:end],
		"page":      page,
		"page_size": pageSize,
		"total":     total,
	})
}

func Get(w http.ResponseWriter, r *http.Request) {
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
	skillID := common.PathVar(r, "skill_id")
	if skillID == "" {
		common.ReplyErr(w, "missing skill_id", http.StatusBadRequest)
		return
	}
	item, err := getSkillDetail(r.Context(), db, userID, skillID)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			common.ReplyErr(w, "skill not found", http.StatusNotFound)
			return
		}
		common.ReplyErr(w, "query skill failed", http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, item)
}

func CreateManaged(w http.ResponseWriter, r *http.Request) {
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
	var req createSkillRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	req.Name = strings.TrimSpace(req.Name)
	req.Description = strings.TrimSpace(req.Description)
	req.Category = strings.TrimSpace(req.Category)
	req.ParentSkillName = strings.TrimSpace(req.ParentSkillName)
	req.Content = strings.TrimSpace(req.Content)
	appLog.Logger.Info().
		Str("route", "POST /api/core/skills").
		Str("user_id", userID).
		Str("category", req.Category).
		Str("name", req.Name).
		Str("parent_skill_name", req.ParentSkillName).
		Int("children_count", len(req.Children)).
		Msg("direct skill management create requested")
	if req.Name == "" || req.Category == "" || req.Content == "" {
		common.ReplyErr(w, "name/category/content required", http.StatusBadRequest)
		return
	}
	if err := validatePathSegment(req.Name); err != nil {
		common.ReplyErr(w, err.Error(), http.StatusBadRequest)
		return
	}
	if err := validatePathSegment(req.Category); err != nil {
		common.ReplyErr(w, err.Error(), http.StatusBadRequest)
		return
	}

	if req.ParentSkillName == "" {
		if err := createParentSkill(r.Context(), db, userID, userName, req); err != nil {
			replySkillError(w, err)
			return
		}
	} else {
		if err := validatePathSegment(req.ParentSkillName); err != nil {
			common.ReplyErr(w, err.Error(), http.StatusBadRequest)
			return
		}
		if len(req.Children) > 0 {
			common.ReplyErr(w, "children is not allowed when creating child skill", http.StatusBadRequest)
			return
		}
		if err := createChildSkill(r.Context(), db, userID, userName, req); err != nil {
			replySkillError(w, err)
			return
		}
	}

	relativePath := parentRelativePath(req.Category, req.Name)
	if req.ParentSkillName != "" {
		relativePath = childRelativePath(req.Category, req.ParentSkillName, req.Name, req.FileExt)
	}
	var row orm.SkillResource
	if err := db.WithContext(r.Context()).Where("owner_user_id = ? AND relative_path = ?", userID, relativePath).Take(&row).Error; err != nil {
		common.ReplyErr(w, "query skill failed", http.StatusInternalServerError)
		return
	}
	item, err := getSkillDetail(r.Context(), db, userID, row.ID)
	if err != nil {
		common.ReplyErr(w, "query skill failed", http.StatusInternalServerError)
		return
	}
	appLog.Logger.Warn().
		Str("route", "POST /api/core/skills").
		Str("user_id", userID).
		Str("skill_id", row.ID).
		Str("category", req.Category).
		Str("name", req.Name).
		Str("parent_skill_name", req.ParentSkillName).
		Msg("direct skill management create executed")
	common.ReplyOK(w, item)
}

func UpdateManaged(w http.ResponseWriter, r *http.Request) {
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
	skillID := common.PathVar(r, "skill_id")
	if skillID == "" {
		common.ReplyErr(w, "missing skill_id", http.StatusBadRequest)
		return
	}
	var req updateSkillRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	appLog.Logger.Warn().
		Str("route", "PATCH /api/core/skills/{skill_id}").
		Str("user_id", userID).
		Str("skill_id", skillID).
		Msg("direct skill management update requested")
	if err := updateSkill(r.Context(), db, userID, userName, skillID, req); err != nil {
		replySkillError(w, err)
		return
	}
	item, err := getSkillDetail(r.Context(), db, userID, skillID)
	if err != nil {
		common.ReplyErr(w, "query skill failed", http.StatusInternalServerError)
		return
	}
	appLog.Logger.Warn().
		Str("route", "PATCH /api/core/skills/{skill_id}").
		Str("user_id", userID).
		Str("skill_id", skillID).
		Msg("direct skill management update executed")
	common.ReplyOK(w, item)
}

func DeleteManaged(w http.ResponseWriter, r *http.Request) {
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
	skillID := common.PathVar(r, "skill_id")
	if skillID == "" {
		common.ReplyErr(w, "missing skill_id", http.StatusBadRequest)
		return
	}
	appLog.Logger.Warn().
		Str("route", "DELETE /api/core/skills/{skill_id}").
		Str("user_id", userID).
		Str("skill_id", skillID).
		Msg("direct skill management delete requested")
	if err := deleteSkill(r.Context(), db, userID, skillID); err != nil {
		replySkillError(w, err)
		return
	}
	appLog.Logger.Warn().
		Str("route", "DELETE /api/core/skills/{skill_id}").
		Str("user_id", userID).
		Str("skill_id", skillID).
		Msg("direct skill management delete executed")
	common.ReplyOK(w, map[string]any{"deleted": true})
}

func Generate(w http.ResponseWriter, r *http.Request) {
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
	skillID := common.PathVar(r, "skill_id")
	if skillID == "" {
		common.ReplyErr(w, "missing skill_id", http.StatusBadRequest)
		return
	}
	var req generateSkillRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	req.SuggestionIDs = compactStrings(req.SuggestionIDs)
	req.UserInstruct = strings.TrimSpace(req.UserInstruct)
	if req.UserInstruct == "" {
		common.ReplyErr(w, "user_instruct required", http.StatusBadRequest)
		return
	}

	var row orm.SkillResource
	if err := db.WithContext(r.Context()).Where("id = ? AND owner_user_id = ?", skillID, userID).Take(&row).Error; err != nil {
		common.ReplyErr(w, "skill not found", http.StatusNotFound)
		return
	}
	if row.NodeType != evolution.SkillNodeTypeParent {
		common.ReplyErr(w, "only parent skill supports generate", http.StatusBadRequest)
		return
	}

	content, err := storedSkillContent(row)
	if err != nil {
		common.ReplyErr(w, "read skill content failed", http.StatusInternalServerError)
		return
	}
	suggestions, err := evolution.LoadApprovedSuggestions(r.Context(), db, userID, evolution.ResourceTypeSkill, row.RelativePath, req.SuggestionIDs)
	if err != nil {
		common.ReplyErr(w, "query suggestions failed", http.StatusInternalServerError)
		return
	}
	if len(suggestions) == 0 {
		common.ReplyErr(w, "no accepted suggestions found", http.StatusBadRequest)
		return
	}

	outdated := false
	resolver := evolution.NewSuggestionOutdatedResolver(db)
	for _, suggestion := range suggestions {
		isOutdated, err := resolver.Resolve(r.Context(), suggestion)
		if err != nil {
			common.ReplyErr(w, "check suggestion outdated failed", http.StatusInternalServerError)
			return
		}
		if isOutdated {
			outdated = true
			break
		}
	}

	generated, err := algo.GenerateSkill(r.Context(), algo.SkillGenerateRequest{
		Category:     row.Category,
		SkillName:    row.SkillName,
		Content:      content,
		Suggestions:  toAlgoSuggestions(suggestions),
		UserInstruct: req.UserInstruct,
	})
	if err != nil {
		common.ReplyErr(w, "skill generate failed: "+err.Error(), http.StatusBadGateway)
		return
	}
	if _, err := validateParentSkillContent(row.SkillName, row.Description, generated); err != nil {
		common.ReplyErr(w, "generated skill content invalid: "+err.Error(), http.StatusBadGateway)
		return
	}

	now := time.Now()
	update := map[string]any{
		"draft_source_version": row.Version,
		"draft_content":        generated,
		"draft_status":         "pending_confirm",
		"draft_updated_at":     now,
		"update_status":        "pending_confirm",
		"updated_at":           now,
		"ext":                  evolution.WithDraftSuggestionIDs(row.Ext, suggestionIDs(suggestions)),
	}
	if err := db.WithContext(r.Context()).Model(&orm.SkillResource{}).Where("id = ?", row.ID).Updates(update).Error; err != nil {
		common.ReplyErr(w, "update skill draft failed", http.StatusInternalServerError)
		return
	}
	_ = db.WithContext(r.Context()).Model(&orm.SkillResource{}).
		Where("owner_user_id = ? AND node_type = ? AND category = ? AND parent_skill_name = ?", userID, evolution.SkillNodeTypeChild, row.Category, row.SkillName).
		Updates(map[string]any{"update_status": "pending_confirm", "updated_at": now}).Error
	common.ReplyOK(w, generateSkillResponse{
		DraftStatus:        "pending_confirm",
		DraftSourceVersion: row.Version,
		DraftPath:          "",
		Outdated:           outdated,
	})
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
	skillID := common.PathVar(r, "skill_id")
	if skillID == "" {
		common.ReplyErr(w, "missing skill_id", http.StatusBadRequest)
		return
	}

	item, err := buildDraftPreviewResponse(r.Context(), db, userID, skillID)
	if err != nil {
		switch {
		case errors.Is(err, gorm.ErrRecordNotFound):
			common.ReplyErr(w, "skill not found", http.StatusNotFound)
		case errors.Is(err, errDraftPreviewParentOnly):
			common.ReplyErr(w, err.Error(), http.StatusBadRequest)
		case errors.Is(err, errDraftPreviewNotFound):
			common.ReplyErr(w, err.Error(), http.StatusNotFound)
		default:
			common.ReplyErr(w, err.Error(), http.StatusInternalServerError)
		}
		return
	}
	common.ReplyOK(w, item)
}

func Confirm(w http.ResponseWriter, r *http.Request) {
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
	skillID := common.PathVar(r, "skill_id")
	if skillID == "" {
		common.ReplyErr(w, "missing skill_id", http.StatusBadRequest)
		return
	}
	var row orm.SkillResource
	if err := db.WithContext(r.Context()).Where("id = ? AND owner_user_id = ?", skillID, userID).Take(&row).Error; err != nil {
		common.ReplyErr(w, "skill not found", http.StatusNotFound)
		return
	}
	if row.NodeType != evolution.SkillNodeTypeParent {
		common.ReplyErr(w, "only parent skill supports confirm", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(row.DraftStatus) != "pending_confirm" {
		common.ReplyErr(w, "skill draft not found", http.StatusNotFound)
		return
	}
	if row.Version != row.DraftSourceVersion {
		common.ReplyErr(w, "skill draft version conflict", http.StatusConflict)
		return
	}
	content := row.DraftContent
	if strings.TrimSpace(content) == "" {
		common.ReplyErr(w, "read skill draft failed", http.StatusInternalServerError)
		return
	}
	hash := evolution.HashContent(content)
	now := time.Now()
	ids := evolution.DraftSuggestionIDs(row.Ext)
	update := map[string]any{
		"content_hash":         hash,
		"content":              content,
		"content_size":         skillContentSize(content),
		"mime_type":            mimeTypeForExt(row.FileExt),
		"version":              row.Version + 1,
		"draft_content":        "",
		"draft_source_version": 0,
		"draft_status":         "",
		"draft_updated_at":     nil,
		"update_status":        evolution.UpdateStatusUpToDate,
		"updated_at":           now,
		"ext":                  evolution.WithDraftSuggestionIDs(row.Ext, nil),
	}
	if err := db.WithContext(r.Context()).Model(&orm.SkillResource{}).Where("id = ? AND version = ?", row.ID, row.Version).Updates(update).Error; err != nil {
		common.ReplyErr(w, "confirm skill draft failed", http.StatusInternalServerError)
		return
	}
	_ = db.WithContext(r.Context()).Model(&orm.SkillResource{}).
		Where("owner_user_id = ? AND node_type = ? AND category = ? AND parent_skill_name = ?", userID, evolution.SkillNodeTypeChild, row.Category, row.SkillName).
		Updates(map[string]any{"update_status": evolution.UpdateStatusUpToDate, "updated_at": now}).Error
	if err := evolution.UpdateSuggestionStatus(r.Context(), db, ids, evolution.SuggestionStatusApplied); err != nil {
		common.ReplyErr(w, "update suggestion status failed", http.StatusInternalServerError)
		return
	}
	item, err := getSkillDetail(r.Context(), db, userID, row.ID)
	if err != nil {
		common.ReplyErr(w, "query skill failed", http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, item)
}

func Discard(w http.ResponseWriter, r *http.Request) {
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
	skillID := common.PathVar(r, "skill_id")
	if skillID == "" {
		common.ReplyErr(w, "missing skill_id", http.StatusBadRequest)
		return
	}
	var row orm.SkillResource
	if err := db.WithContext(r.Context()).Where("id = ? AND owner_user_id = ?", skillID, userID).Take(&row).Error; err != nil {
		common.ReplyErr(w, "skill not found", http.StatusNotFound)
		return
	}
	if row.NodeType != evolution.SkillNodeTypeParent {
		common.ReplyErr(w, "only parent skill supports discard", http.StatusBadRequest)
		return
	}
	if strings.TrimSpace(row.DraftStatus) != "pending_confirm" {
		common.ReplyErr(w, "skill draft not found", http.StatusNotFound)
		return
	}
	ids := evolution.DraftSuggestionIDs(row.Ext)
	now := time.Now()
	update := map[string]any{
		"draft_source_version": 0,
		"draft_content":        "",
		"draft_status":         "",
		"draft_updated_at":     nil,
		"update_status":        evolution.UpdateStatusUpToDate,
		"updated_at":           now,
		"ext":                  evolution.WithDraftSuggestionIDs(row.Ext, nil),
	}
	if err := db.WithContext(r.Context()).Model(&orm.SkillResource{}).Where("id = ?", row.ID).Updates(update).Error; err != nil {
		common.ReplyErr(w, "discard skill draft failed", http.StatusInternalServerError)
		return
	}
	_ = db.WithContext(r.Context()).Model(&orm.SkillResource{}).
		Where("owner_user_id = ? AND node_type = ? AND category = ? AND parent_skill_name = ?", userID, evolution.SkillNodeTypeChild, row.Category, row.SkillName).
		Updates(map[string]any{"update_status": evolution.UpdateStatusUpToDate, "updated_at": now}).Error
	if err := evolution.UpdateSuggestionStatus(r.Context(), db, ids, evolution.SuggestionStatusDiscarded); err != nil {
		common.ReplyErr(w, "update suggestion status failed", http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, map[string]any{"discarded": true})
}

func getSkillDetail(ctx context.Context, db *gorm.DB, userID, skillID string) (map[string]any, error) {
	var row orm.SkillResource
	if err := db.WithContext(ctx).Where("id = ? AND owner_user_id = ?", skillID, userID).Take(&row).Error; err != nil {
		return nil, err
	}
	suggestionStatusesByKey, err := loadSuggestionStatusesByKey(ctx, db, userID, []orm.SkillResource{row})
	if err != nil {
		return nil, err
	}
	suggestionStatus := evolution.CanonicalSuggestionStatus(suggestionStatusesByKey[skillSuggestionResourceKey(row)])
	content, err := storedSkillContent(row)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	item := map[string]any{
		"skill_id":                       row.ID,
		"name":                           row.SkillName,
		"description":                    row.Description,
		"category":                       row.Category,
		"tags":                           parseTags(row.Tags),
		"is_locked":                      row.IsLocked,
		"is_enabled":                     row.IsEnabled,
		"update_status":                  row.UpdateStatus,
		"has_pending_review_suggestions": suggestionStatus != evolution.SuggestionStatusNone,
		"suggestion_status":              suggestionStatus,
		"node_type":                      row.NodeType,
		"parent_skill_name":              row.ParentSkillName,
		"content":                        content,
		"file_ext":                       row.FileExt,
	}
	if row.NodeType == evolution.SkillNodeTypeParent {
		var children []orm.SkillResource
		if err := db.WithContext(ctx).
			Where("owner_user_id = ? AND node_type = ? AND category = ? AND parent_skill_name = ?", userID, evolution.SkillNodeTypeChild, row.Category, row.SkillName).
			Order("created_at ASC").
			Find(&children).Error; err != nil {
			return nil, err
		}
		childItems := make([]map[string]any, 0, len(children))
		for _, child := range children {
			childContent, _ := storedSkillContent(child)
			childItems = append(childItems, map[string]any{
				"skill_id":                       child.ID,
				"name":                           child.SkillName,
				"description":                    child.Description,
				"file_ext":                       child.FileExt,
				"is_locked":                      child.IsLocked,
				"is_enabled":                     row.IsEnabled,
				"update_status":                  row.UpdateStatus,
				"has_pending_review_suggestions": suggestionStatus != evolution.SuggestionStatusNone,
				"suggestion_status":              suggestionStatus,
				"node_type":                      child.NodeType,
				"parent_skill_name":              child.ParentSkillName,
				"content":                        childContent,
			})
		}
		item["children"] = childItems
	} else {
		item["children"] = []any{}
	}
	return item, nil
}

func buildDraftPreviewResponse(ctx context.Context, db *gorm.DB, userID, skillID string) (draftPreviewResponse, error) {
	var row orm.SkillResource
	if err := db.WithContext(ctx).Where("id = ? AND owner_user_id = ?", skillID, userID).Take(&row).Error; err != nil {
		return draftPreviewResponse{}, err
	}
	if row.NodeType != evolution.SkillNodeTypeParent {
		return draftPreviewResponse{}, errDraftPreviewParentOnly
	}
	if strings.TrimSpace(row.DraftStatus) != "pending_confirm" {
		return draftPreviewResponse{}, errDraftPreviewNotFound
	}

	currentContent, err := storedSkillContent(row)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return draftPreviewResponse{}, err
	}

	draftContent := row.DraftContent
	if strings.TrimSpace(draftContent) == "" {
		return draftPreviewResponse{}, errors.New("read skill draft failed")
	}

	diff, err := buildContentDiff(currentContent, draftContent)
	if err != nil {
		return draftPreviewResponse{}, err
	}

	outdated, err := draftSuggestionsOutdated(ctx, db, row)
	if err != nil {
		return draftPreviewResponse{}, err
	}

	return draftPreviewResponse{
		SkillID:            row.ID,
		DraftStatus:        row.DraftStatus,
		DraftSourceVersion: row.DraftSourceVersion,
		CurrentContent:     currentContent,
		DraftContent:       draftContent,
		Diff:               diff,
		Outdated:           outdated,
	}, nil
}

func draftSuggestionsOutdated(ctx context.Context, db *gorm.DB, row orm.SkillResource) (bool, error) {
	ids := evolution.DraftSuggestionIDs(row.Ext)
	if len(ids) == 0 {
		return false, nil
	}

	suggestions, err := evolution.LoadApprovedSuggestions(ctx, db, row.OwnerUserID, evolution.ResourceTypeSkill, row.RelativePath, ids)
	if err != nil {
		return false, err
	}

	resolver := evolution.NewSuggestionOutdatedResolver(db)
	for _, suggestion := range suggestions {
		isOutdated, err := resolver.Resolve(ctx, suggestion)
		if err != nil {
			return false, err
		}
		if isOutdated {
			return true, nil
		}
	}
	return false, nil
}

func createParentSkill(ctx context.Context, db *gorm.DB, userID, userName string, req createSkillRequest) error {
	fullContent, description, err := buildParentSkillContent(req.Name, req.Description, req.Content)
	if err != nil {
		return err
	}
	return createParentSkillWithContent(ctx, db, userID, userName, req, fullContent, description)
}

func createParentSkillWithContent(ctx context.Context, db *gorm.DB, userID, userName string, req createSkillRequest, fullContent, description string) error {
	relPath := parentRelativePath(req.Category, req.Name)
	var count int64
	if err := db.WithContext(ctx).Model(&orm.SkillResource{}).Where("owner_user_id = ? AND relative_path = ?", userID, relPath).Count(&count).Error; err != nil {
		return err
	}
	if count > 0 {
		return gorm.ErrDuplicatedKey
	}
	for _, child := range req.Children {
		if err := validatePathSegment(child.Name); err != nil {
			return err
		}
	}

	now := time.Now()
	enabled := true
	if req.IsEnabled != nil {
		enabled = *req.IsEnabled
	}
	parent := orm.SkillResource{
		ID:              evolution.BuildSuggestionRecord("", "", "", "", "", "").ID,
		OwnerUserID:     userID,
		OwnerUserName:   userName,
		Category:        req.Category,
		ParentSkillName: "",
		SkillName:       req.Name,
		NodeType:        evolution.SkillNodeTypeParent,
		Description:     description,
		Tags:            tagsJSON(req.Tags),
		FileExt:         "md",
		RelativePath:    relPath,
		Content:         fullContent,
		ContentSize:     skillContentSize(fullContent),
		MimeType:        mimeTypeForExt("md"),
		ContentHash:     evolution.HashContent(fullContent),
		Version:         1,
		IsLocked:        req.IsLocked,
		IsEnabled:       enabled,
		UpdateStatus:    evolution.UpdateStatusUpToDate,
		CreateUserID:    userID,
		CreateUserName:  userName,
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	children := make([]orm.SkillResource, 0, len(req.Children))
	for _, child := range req.Children {
		ext := normalizeExt(child.FileExt)
		rel := childRelativePath(req.Category, req.Name, child.Name, ext)
		children = append(children, orm.SkillResource{
			ID:              evolution.BuildSuggestionRecord("", "", "", "", "", "").ID,
			OwnerUserID:     userID,
			OwnerUserName:   userName,
			Category:        req.Category,
			ParentSkillName: req.Name,
			SkillName:       child.Name,
			NodeType:        evolution.SkillNodeTypeChild,
			Description:     "",
			FileExt:         ext,
			RelativePath:    rel,
			Content:         child.Content,
			ContentSize:     skillContentSize(child.Content),
			MimeType:        mimeTypeForExt(ext),
			ContentHash:     evolution.HashContent(child.Content),
			Version:         1,
			IsLocked:        child.IsLocked,
			IsEnabled:       enabled,
			UpdateStatus:    evolution.UpdateStatusUpToDate,
			CreateUserID:    userID,
			CreateUserName:  userName,
			CreatedAt:       now,
			UpdatedAt:       now,
		})
	}
	if err := db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Create(&parent).Error; err != nil {
			return err
		}
		if len(children) > 0 {
			if err := tx.Create(&children).Error; err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		return err
	}
	return nil
}

func createChildSkill(ctx context.Context, db *gorm.DB, userID, userName string, req createSkillRequest) error {
	var parent orm.SkillResource
	if err := db.WithContext(ctx).
		Where("owner_user_id = ? AND node_type = ? AND category = ? AND skill_name = ?", userID, evolution.SkillNodeTypeParent, req.Category, req.ParentSkillName).
		Take(&parent).Error; err != nil {
		return err
	}
	ext := normalizeExt(req.FileExt)
	relPath := childRelativePath(req.Category, req.ParentSkillName, req.Name, ext)
	var count int64
	if err := db.WithContext(ctx).Model(&orm.SkillResource{}).Where("owner_user_id = ? AND relative_path = ?", userID, relPath).Count(&count).Error; err != nil {
		return err
	}
	if count > 0 {
		return gorm.ErrDuplicatedKey
	}
	now := time.Now()
	row := orm.SkillResource{
		ID:              evolution.BuildSuggestionRecord("", "", "", "", "", "").ID,
		OwnerUserID:     userID,
		OwnerUserName:   userName,
		Category:        req.Category,
		ParentSkillName: req.ParentSkillName,
		SkillName:       req.Name,
		NodeType:        evolution.SkillNodeTypeChild,
		Description:     "",
		FileExt:         ext,
		RelativePath:    relPath,
		Content:         req.Content,
		ContentSize:     skillContentSize(req.Content),
		MimeType:        mimeTypeForExt(ext),
		ContentHash:     evolution.HashContent(req.Content),
		Version:         1,
		IsLocked:        req.IsLocked,
		IsEnabled:       parent.IsEnabled,
		UpdateStatus:    parent.UpdateStatus,
		CreateUserID:    userID,
		CreateUserName:  userName,
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	if err := db.WithContext(ctx).Create(&row).Error; err != nil {
		return err
	}
	return nil
}

func updateSkill(ctx context.Context, db *gorm.DB, userID, userName, skillID string, req updateSkillRequest) error {
	var row orm.SkillResource
	if err := db.WithContext(ctx).Where("id = ? AND owner_user_id = ?", skillID, userID).Take(&row).Error; err != nil {
		return err
	}
	if row.NodeType == evolution.SkillNodeTypeParent {
		return updateParentSkill(ctx, db, userID, userName, &row, req)
	}
	return updateChildSkill(ctx, db, userID, &row, req)
}

func deleteSkill(ctx context.Context, db *gorm.DB, userID, skillID string) error {
	var row orm.SkillResource
	if err := db.WithContext(ctx).Where("id = ? AND owner_user_id = ?", skillID, userID).Take(&row).Error; err != nil {
		return err
	}
	if row.NodeType == evolution.SkillNodeTypeParent {
		return deleteParentSkill(ctx, db, userID, &row)
	}
	return deleteChildSkill(ctx, db, &row)
}

func deleteParentSkill(ctx context.Context, db *gorm.DB, userID string, row *orm.SkillResource) error {
	if err := db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("owner_user_id = ? AND node_type = ? AND category = ? AND parent_skill_name = ?", userID, evolution.SkillNodeTypeChild, row.Category, row.SkillName).Delete(&orm.SkillResource{}).Error; err != nil {
			return err
		}
		return tx.Where("id = ? AND owner_user_id = ?", row.ID, userID).Delete(&orm.SkillResource{}).Error
	}); err != nil {
		return err
	}
	return nil
}

func deleteChildSkill(ctx context.Context, db *gorm.DB, row *orm.SkillResource) error {
	if err := db.WithContext(ctx).Where("id = ? AND owner_user_id = ?", row.ID, row.OwnerUserID).Delete(&orm.SkillResource{}).Error; err != nil {
		return err
	}
	return nil
}

func updateParentSkill(ctx context.Context, db *gorm.DB, userID, userName string, row *orm.SkillResource, req updateSkillRequest) error {
	if strings.TrimSpace(row.DraftStatus) == "pending_confirm" {
		return errors.New("parent skill has pending_confirm draft")
	}
	currentContent, err := storedSkillContent(*row)
	if err != nil {
		return err
	}
	currentBody, err := parentSkillBody(currentContent)
	if err != nil {
		return err
	}
	oldCategory := row.Category
	oldName := row.SkillName
	newName := row.SkillName
	if req.Name != nil {
		newName = strings.TrimSpace(*req.Name)
		if err := validatePathSegment(newName); err != nil {
			return err
		}
	}
	newCategory := row.Category
	if req.Category != nil {
		newCategory = strings.TrimSpace(*req.Category)
		if err := validatePathSegment(newCategory); err != nil {
			return err
		}
	}
	newBody := currentBody
	if req.Content != nil {
		newBody = strings.TrimSpace(*req.Content)
	}
	newDescription := row.Description
	if req.Description != nil {
		newDescription = strings.TrimSpace(*req.Description)
	}
	newContent, resolvedDescription, err := buildParentSkillContent(newName, newDescription, newBody)
	if err != nil {
		return err
	}
	newDescription = resolvedDescription
	if oldCategory != newCategory || oldName != newName {
		var count int64
		newRelativePath := parentRelativePath(newCategory, newName)
		if err := db.WithContext(ctx).
			Model(&orm.SkillResource{}).
			Where("owner_user_id = ? AND relative_path = ? AND id <> ?", userID, newRelativePath, row.ID).
			Count(&count).Error; err != nil {
			return err
		}
		if count > 0 {
			return gorm.ErrDuplicatedKey
		}
	}
	row.RelativePath = parentRelativePath(newCategory, newName)

	now := time.Now()
	update := map[string]any{
		"skill_name":    newName,
		"description":   newDescription,
		"category":      newCategory,
		"tags":          row.Tags,
		"relative_path": row.RelativePath,
		"content":       newContent,
		"content_size":  skillContentSize(newContent),
		"mime_type":     mimeTypeForExt("md"),
		"content_hash":  evolution.HashContent(newContent),
		"updated_at":    now,
	}
	if req.Tags != nil {
		update["tags"] = tagsJSON(*req.Tags)
	}
	if req.IsLocked != nil {
		update["is_locked"] = *req.IsLocked
	}
	if req.IsEnabled != nil {
		update["is_enabled"] = *req.IsEnabled
	}
	if err := db.WithContext(ctx).Model(&orm.SkillResource{}).Where("id = ?", row.ID).Updates(update).Error; err != nil {
		return err
	}

	var children []orm.SkillResource
	if err := db.WithContext(ctx).
		Where("owner_user_id = ? AND node_type = ? AND category = ? AND parent_skill_name = ?", userID, evolution.SkillNodeTypeChild, oldCategory, oldName).
		Find(&children).Error; err != nil {
		return err
	}
	for _, child := range children {
		childRelative := childRelativePath(newCategory, newName, child.SkillName, child.FileExt)
		updateChild := map[string]any{
			"category":          newCategory,
			"parent_skill_name": newName,
			"relative_path":     childRelative,
			"updated_at":        now,
		}
		if req.IsEnabled != nil {
			updateChild["is_enabled"] = *req.IsEnabled
		}
		if err := db.WithContext(ctx).Model(&orm.SkillResource{}).Where("id = ?", child.ID).Updates(updateChild).Error; err != nil {
			return err
		}
	}
	return nil
}

func updateChildSkill(ctx context.Context, db *gorm.DB, userID string, row *orm.SkillResource, req updateSkillRequest) error {
	if req.Name != nil {
		return errors.New("child skill name is immutable")
	}
	if req.Category != nil || req.Tags != nil || req.IsEnabled != nil || req.Description != nil {
		return errors.New("child skill only supports content/file_ext/is_locked updates")
	}
	currentContent, err := storedSkillContent(*row)
	if err != nil {
		return err
	}
	newContent := currentContent
	if req.Content != nil {
		newContent = *req.Content
	}
	newExt := row.FileExt
	if req.FileExt != nil {
		newExt = normalizeExt(*req.FileExt)
	}
	newRelative := row.RelativePath
	if newExt != row.FileExt {
		newRelative = childRelativePath(row.Category, row.ParentSkillName, row.SkillName, newExt)
	}
	update := map[string]any{
		"file_ext":      newExt,
		"relative_path": newRelative,
		"content":       newContent,
		"content_size":  skillContentSize(newContent),
		"mime_type":     mimeTypeForExt(newExt),
		"content_hash":  evolution.HashContent(newContent),
		"updated_at":    time.Now(),
	}
	if req.IsLocked != nil {
		update["is_locked"] = *req.IsLocked
	}
	return db.WithContext(ctx).Model(&orm.SkillResource{}).Where("id = ?", row.ID).Updates(update).Error
}

func parentListResponse(parent orm.SkillResource, children []orm.SkillResource, suggestionStatus string) map[string]any {
	suggestionStatus = evolution.CanonicalSuggestionStatus(suggestionStatus)
	childItems := make([]map[string]any, 0, len(children))
	sort.Slice(children, func(i, j int) bool { return children[i].CreatedAt.Before(children[j].CreatedAt) })
	for _, child := range children {
		childItems = append(childItems, map[string]any{
			"skill_id":                       child.ID,
			"name":                           child.SkillName,
			"description":                    child.Description,
			"file_ext":                       child.FileExt,
			"is_locked":                      child.IsLocked,
			"is_enabled":                     parent.IsEnabled,
			"update_status":                  parent.UpdateStatus,
			"has_pending_review_suggestions": suggestionStatus != evolution.SuggestionStatusNone,
			"suggestion_status":              suggestionStatus,
			"node_type":                      child.NodeType,
		})
	}
	return map[string]any{
		"skill_id":                       parent.ID,
		"name":                           parent.SkillName,
		"description":                    parent.Description,
		"category":                       parent.Category,
		"tags":                           parseTags(parent.Tags),
		"is_locked":                      parent.IsLocked,
		"is_enabled":                     parent.IsEnabled,
		"update_status":                  parent.UpdateStatus,
		"has_pending_review_suggestions": suggestionStatus != evolution.SuggestionStatusNone,
		"suggestion_status":              suggestionStatus,
		"node_type":                      parent.NodeType,
		"children":                       childItems,
	}
}

func loadSuggestionStatusesByKey(ctx context.Context, db *gorm.DB, userID string, skillRows []orm.SkillResource) (map[string]string, error) {
	targetKeys := make(map[string]struct{}, len(skillRows))
	targetsByCategoryAndParent := make(map[string][]string, len(skillRows))
	keys := make([]string, 0, len(skillRows))
	categories := make([]string, 0, len(skillRows))
	for _, row := range skillRows {
		key := skillSuggestionResourceKey(row)
		if key == "" {
			continue
		}
		targetKeys[key] = struct{}{}
		keys = append(keys, key)
		category := strings.TrimSpace(row.Category)
		parentName := firstNonEmpty(strings.TrimSpace(row.ParentSkillName), strings.TrimSpace(row.SkillName))
		if category != "" && parentName != "" {
			targetsByCategoryAndParent[skillSuggestionCategoryParentKey(category, parentName)] = append(targetsByCategoryAndParent[skillSuggestionCategoryParentKey(category, parentName)], key)
			categories = append(categories, category)
		}
	}
	keys = compactStrings(keys)
	categories = compactStrings(categories)
	if len(keys) == 0 {
		return map[string]string{}, nil
	}

	var rows []struct {
		ResourceKey     string `gorm:"column:resource_key"`
		RelativePath    string `gorm:"column:relative_path"`
		Category        string `gorm:"column:category"`
		ParentSkillName string `gorm:"column:parent_skill_name"`
		SkillName       string `gorm:"column:skill_name"`
		Status          string `gorm:"column:status"`
	}
	query := db.WithContext(ctx).
		Model(&orm.ResourceSuggestion{}).
		Select("resource_key", "relative_path", "category", "parent_skill_name", "skill_name", "status").
		Where("user_id = ? AND resource_type = ? AND status IN ?",
			strings.TrimSpace(userID),
			evolution.ResourceTypeSkill,
			evolution.VisibleSuggestionStatuses(),
		)
	if len(categories) > 0 {
		query = query.Where("(resource_key IN ? OR relative_path IN ? OR category IN ?)", keys, keys, categories)
	} else {
		query = query.Where("(resource_key IN ? OR relative_path IN ?)", keys, keys)
	}
	if err := query.Find(&rows).Error; err != nil {
		return nil, err
	}

	result := make(map[string]string, len(rows))
	for _, row := range rows {
		key := filepath.ToSlash(strings.TrimSpace(row.ResourceKey))
		if key == "" {
			key = filepath.ToSlash(strings.TrimSpace(row.RelativePath))
		}
		if _, ok := targetKeys[key]; ok {
			result[key] = evolution.MergeSuggestionStatus(result[key], row.Status)
			continue
		}
		category := strings.TrimSpace(row.Category)
		parentName := firstNonEmpty(strings.TrimSpace(row.ParentSkillName), strings.TrimSpace(row.SkillName))
		if category == "" || parentName == "" {
			continue
		}
		for _, targetKey := range targetsByCategoryAndParent[skillSuggestionCategoryParentKey(category, parentName)] {
			result[targetKey] = evolution.MergeSuggestionStatus(result[targetKey], row.Status)
		}
	}
	return result, nil
}

func skillSuggestionResourceKeys(rows []orm.SkillResource) []string {
	keys := make([]string, 0, len(rows))
	for _, row := range rows {
		key := skillSuggestionResourceKey(row)
		if key == "" {
			continue
		}
		keys = append(keys, key)
	}
	return compactStrings(keys)
}

func skillSuggestionResourceKey(row orm.SkillResource) string {
	return evolution.SkillSuggestionResourceKey(row)
}

func skillSuggestionCategoryParentKey(category, parentName string) string {
	return strings.TrimSpace(category) + "\x00" + strings.TrimSpace(parentName)
}

func containsAllTags(have, need []string) bool {
	if len(need) == 0 {
		return true
	}
	set := make(map[string]struct{}, len(have))
	for _, item := range have {
		set[strings.TrimSpace(item)] = struct{}{}
	}
	for _, item := range need {
		if _, ok := set[strings.TrimSpace(item)]; !ok {
			return false
		}
	}
	return true
}

func parsePositiveInt(raw string, fallback int) int {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return fallback
	}
	var value int
	_, err := fmt.Sscanf(raw, "%d", &value)
	if err != nil || value < 1 {
		return fallback
	}
	return value
}

func compactStrings(values []string) []string {
	out := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
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
		out = append(out, algo.Suggestion{Title: row.Title, Content: row.Content, Reason: row.Reason})
	}
	return out
}

func replySkillError(w http.ResponseWriter, err error) {
	switch {
	case err == nil:
		return
	case errors.Is(err, gorm.ErrRecordNotFound):
		common.ReplyErr(w, "skill not found", http.StatusNotFound)
	case errors.Is(err, gorm.ErrDuplicatedKey):
		common.ReplyErr(w, "skill already exists", http.StatusConflict)
	default:
		message := strings.TrimSpace(err.Error())
		status := http.StatusBadRequest
		if strings.Contains(message, "failed") || strings.Contains(message, "invalid") || strings.Contains(message, "required") || strings.Contains(message, "immutable") || strings.Contains(message, "supports") || strings.Contains(message, "pending_confirm") {
			status = http.StatusBadRequest
		} else {
			status = http.StatusInternalServerError
		}
		common.ReplyErr(w, message, status)
	}
}
