package wordgroup

import (
	"net/http"
	"strconv"
	"strings"
	"time"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/log"
	"lazyrag/core/store"
)

// DeleteWordGroupConflictResponse mirrors DeleteWordGroupResponse for symmetry.
type DeleteWordGroupConflictResponse struct {
	ID          string `json:"id"`
	DeletedRows int64  `json:"deleted_rows"`
}

// WordGroupConflictResponse is one item returned by GET /word_group_conflict.
// group_ids is parsed back from the stored JSON-serialized string.
type WordGroupConflictResponse struct {
	ID          string    `json:"id"`
	Reason      string    `json:"reason"`
	Word        string    `json:"word"`
	Description string    `json:"description"`
	GroupIDs    []string  `json:"group_ids"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// ListWordGroupConflictsResponse mirrors the existing word-group list pagination shape.
type ListWordGroupConflictsResponse struct {
	Items         []WordGroupConflictResponse `json:"items"`
	TotalSize     int32                       `json:"total_size"`
	NextPageToken string                      `json:"next_page_token"`
}

// ListWordGroupConflicts returns the requesting user's pending conflicts ordered by updated_at DESC.
// Hits idx_word_group_conflict_user_updated (partial composite index).
func ListWordGroupConflicts(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		common.ReplyErr(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	userID := store.UserID(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	q := r.URL.Query()
	pageToken := strings.TrimSpace(q.Get("page_token"))
	pageSizeStr := strings.TrimSpace(q.Get("page_size"))

	pageSize := 20
	if pageSizeStr != "" {
		if v, err := strconv.Atoi(pageSizeStr); err == nil && v > 0 {
			pageSize = v
		}
	}
	if pageSize > 100 {
		pageSize = 100
	}

	offset := 0
	if pageToken != "" {
		if v, err := parseListPageToken(pageToken); err == nil && v >= 0 {
			offset = v
		}
	}

	db := store.DB()
	scope := db.Model(&orm.WordGroupConflict{}).
		Where("create_user_id = ? AND deleted_at IS NULL", userID)

	var total int64
	if err := scope.Count(&total).Error; err != nil {
		log.Logger.Error().Err(err).Msg("count word_group_conflicts failed")
		common.ReplyErr(w, "list word group conflicts failed", http.StatusInternalServerError)
		return
	}

	var rows []orm.WordGroupConflict
	if err := scope.Order("updated_at DESC").
		Offset(offset).Limit(pageSize).
		Find(&rows).Error; err != nil {
		log.Logger.Error().Err(err).Msg("list word_group_conflicts failed")
		common.ReplyErr(w, "list word group conflicts failed", http.StatusInternalServerError)
		return
	}

	items := make([]WordGroupConflictResponse, 0, len(rows))
	for i := range rows {
		groupIDs, _ := parseJSONStringSliceField(rows[i].GroupIDs)
		if groupIDs == nil {
			groupIDs = []string{}
		}
		items = append(items, WordGroupConflictResponse{
			ID:          rows[i].ID,
			Reason:      rows[i].Reason,
			Word:        rows[i].Word,
			Description: rows[i].Description,
			GroupIDs:    groupIDs,
			CreatedAt:   rows[i].CreatedAt,
			UpdatedAt:   rows[i].UpdatedAt,
		})
	}

	end := offset + len(items)
	nextToken := ""
	if end < int(total) {
		nextToken = encodeListPageToken(end, pageSize, int(total))
	}

	common.ReplyOK(w, ListWordGroupConflictsResponse{
		Items:         items,
		TotalSize:     int32(total),
		NextPageToken: nextToken,
	})
}

// DeleteWordGroupConflict soft-deletes a single conflict row owned by the request user.
// Hits the row by primary key (id) scoped to create_user_id; returns 404 if not found.
func DeleteWordGroupConflict(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		common.ReplyErr(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	id := strings.TrimSpace(common.PathVar(r, "id"))
	if id == "" {
		common.ReplyErr(w, "missing id", http.StatusBadRequest)
		return
	}
	userID := store.UserID(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	now := time.Now().UTC()
	res := store.DB().Model(&orm.WordGroupConflict{}).
		Where("id = ? AND create_user_id = ? AND deleted_at IS NULL", id, userID).
		Updates(map[string]any{
			"deleted_at": now,
			"updated_at": now,
		})
	if err := res.Error; err != nil {
		log.Logger.Error().Err(err).Str("id", id).Msg("delete word_group_conflict failed")
		common.ReplyErr(w, "delete word group conflict failed", http.StatusInternalServerError)
		return
	}
	if res.RowsAffected == 0 {
		common.ReplyErr(w, "word group conflict not found", http.StatusNotFound)
		return
	}
	common.ReplyOK(w, DeleteWordGroupConflictResponse{ID: id, DeletedRows: res.RowsAffected})
}
