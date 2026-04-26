package evolution

import (
	"context"
	"errors"
	"net/http"
	"strings"

	"gorm.io/gorm"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/store"
)

const (
	ManagedMemoryTitle     = "回复风格偏好"
	ManagedPreferenceTitle = "输出结构偏好"
)

type ManagedStateItem struct {
	ResourceID                  string `json:"resource_id"`
	ResourceType                string `json:"resource_type"`
	Title                       string `json:"title"`
	Content                     string `json:"content"`
	ContentSummary              string `json:"content_summary"`
	HasPendingReviewSuggestions bool   `json:"has_pending_review_suggestions"`
	SuggestionStatus            string `json:"suggestion_status"`
}

func ListManagedStates(w http.ResponseWriter, r *http.Request) {
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

	memoryRow, err := LoadSystemMemory(r.Context(), db, userID)
	if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		common.ReplyErr(w, "query managed states failed", http.StatusInternalServerError)
		return
	}
	preferenceRow, err := LoadSystemUserPreference(r.Context(), db, userID)
	if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		common.ReplyErr(w, "query managed states failed", http.StatusInternalServerError)
		return
	}
	suggestionStatuses, err := LoadManagedSuggestionStatuses(r.Context(), db, userID)
	if err != nil {
		common.ReplyErr(w, "query managed states failed", http.StatusInternalServerError)
		return
	}

	items := []ManagedStateItem{
		NewManagedStateItem(ResourceTypeMemory, memoryRow, suggestionStatuses[ResourceTypeMemory]),
		NewManagedStateItem(ResourceTypeUserPreference, preferenceRow, suggestionStatuses[ResourceTypeUserPreference]),
	}
	common.ReplyOK(w, map[string]any{"items": items})
}

func LoadSystemMemory(ctx context.Context, db *gorm.DB, userID string) (*orm.SystemMemory, error) {
	var row orm.SystemMemory
	if err := db.WithContext(ctx).
		Where("user_id = ?", strings.TrimSpace(userID)).
		Order("created_at ASC").
		Take(&row).Error; err != nil {
		return nil, err
	}
	return &row, nil
}

func LoadSystemUserPreference(ctx context.Context, db *gorm.DB, userID string) (*orm.SystemUserPreference, error) {
	var row orm.SystemUserPreference
	if err := db.WithContext(ctx).
		Where("user_id = ?", strings.TrimSpace(userID)).
		Order("created_at ASC").
		Take(&row).Error; err != nil {
		return nil, err
	}
	return &row, nil
}

func NewManagedStateItem(resourceType string, row any, suggestionStatus string) ManagedStateItem {
	suggestionStatus = CanonicalSuggestionStatus(suggestionStatus)
	item := ManagedStateItem{
		ResourceType:                strings.TrimSpace(resourceType),
		Title:                       ManagedStateTitle(resourceType),
		HasPendingReviewSuggestions: suggestionStatus != SuggestionStatusNone,
		SuggestionStatus:            suggestionStatus,
	}
	switch typed := row.(type) {
	case *orm.SystemMemory:
		if typed != nil {
			item.ResourceID = strings.TrimSpace(typed.ID)
			item.Content = typed.Content
			item.ContentSummary = ManagedStateSummary(typed.Content)
		}
	case *orm.SystemUserPreference:
		if typed != nil {
			item.ResourceID = strings.TrimSpace(typed.ID)
			item.Content = typed.Content
			item.ContentSummary = ManagedStateSummary(typed.Content)
		}
	}
	return item
}

func LoadManagedSuggestionStatuses(ctx context.Context, db *gorm.DB, userID string) (map[string]string, error) {
	var rows []struct {
		ResourceType string `gorm:"column:resource_type"`
		Status       string `gorm:"column:status"`
	}
	if err := db.WithContext(ctx).
		Model(&orm.ResourceSuggestion{}).
		Select("resource_type", "status").
		Where("user_id = ? AND status IN ? AND resource_type IN ?",
			strings.TrimSpace(userID),
			VisibleSuggestionStatuses(),
			[]string{ResourceTypeMemory, ResourceTypeUserPreference},
		).
		Find(&rows).Error; err != nil {
		return nil, err
	}

	result := make(map[string]string, len(rows))
	for _, row := range rows {
		resourceType := strings.TrimSpace(row.ResourceType)
		if resourceType == "" {
			continue
		}
		result[resourceType] = MergeSuggestionStatus(result[resourceType], row.Status)
	}
	return result, nil
}

func ManagedSuggestionStatusForResource(ctx context.Context, db *gorm.DB, userID, resourceType string) (string, error) {
	statuses, err := LoadManagedSuggestionStatuses(ctx, db, userID)
	if err != nil {
		return SuggestionStatusNone, err
	}
	return CanonicalSuggestionStatus(statuses[strings.TrimSpace(resourceType)]), nil
}

func ManagedStateTitle(resourceType string) string {
	switch strings.TrimSpace(resourceType) {
	case ResourceTypeMemory:
		return ManagedMemoryTitle
	case ResourceTypeUserPreference:
		return ManagedPreferenceTitle
	default:
		return strings.TrimSpace(resourceType)
	}
}

func ManagedStateSummary(content string) string {
	if fields := strings.Fields(content); len(fields) > 0 {
		return strings.Join(fields, " ")
	}
	return ""
}
