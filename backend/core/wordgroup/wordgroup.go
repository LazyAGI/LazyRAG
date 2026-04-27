package wordgroup

import (
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/log"
	"lazyrag/core/store"

	"github.com/google/uuid"
	"gorm.io/gorm"
)

// CreateWordGroupRequest is the JSON body for POST /word_group.
// 一次提交一个术语及可选的多个别名（aliases）。
type CreateWordGroupRequest struct {
	Term        string   `json:"term"`
	Aliases     []string `json:"aliases"`
	Description string   `json:"description"`
	Lock        bool     `json:"lock"` // 保护态
}

// CreatedAlias is one persisted alias row under a term.
type CreatedAlias struct {
	ID   string `json:"id"`
	Word string `json:"word"`
}

// CheckWordsExistRequest is the JSON body for POST /word_group:checkExists.
type CheckWordsExistRequest struct {
	Term    string   `json:"term"`
	Aliases []string `json:"aliases"`
}

// CheckWordsExistResponse lists which submitted words already appear in words for the request user (any group/kind).
type CheckWordsExistResponse struct {
	Existing []string `json:"existing"`
}

// DeleteWordGroupResponse is returned in APIResponse.Data after delete.
type DeleteWordGroupResponse struct {
	GroupID     string `json:"group_id"`
	DeletedRows int64  `json:"deleted_rows"`
}

// BatchDeleteWordGroupsRequest is the JSON body for POST /word_group:batchDelete.
type BatchDeleteWordGroupsRequest struct {
	GroupIDs []string `json:"group_ids"`
}

// BatchDeleteWordGroupsResponse is returned in APIResponse.Data after batch soft-delete.
type BatchDeleteWordGroupsResponse struct {
	GroupIDs    []string `json:"group_ids"`
	DeletedRows int64    `json:"deleted_rows"`
}

// CreateWordGroupResponse is returned in APIResponse.Data after create.
type CreateWordGroupResponse struct {
	TermID      string         `json:"term_id"`
	Term        string         `json:"term"`
	GroupID     string         `json:"group_id"`
	Aliases     []CreatedAlias `json:"aliases"`
	Description string         `json:"description"`
	Source      string         `json:"source"`
	Reference   string         `json:"reference"`
	Lock        bool           `json:"lock"`
}

// CreateWordGroup persists one term row and zero or more alias rows (same group / metadata).
func CreateWordGroup(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		common.ReplyErr(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body CreateWordGroupRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "invalid body", err), http.StatusBadRequest)
		return
	}
	term := strings.TrimSpace(body.Term)
	groupID := GenerateID()
	desc := strings.TrimSpace(body.Description)
	ref := ""
	src := normalizeSource("")
	aliases := normalizeAliases(body.Aliases)

	if term == "" {
		common.ReplyErr(w, "term is required", http.StatusBadRequest)
		return
	}

	userID := store.UserID(r)
	userName := store.UserName(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	now := time.Now().UTC()
	base := orm.WordBase{
		CreateUserID:   userID,
		CreateUserName: userName,
		CreatedAt:      now,
		UpdatedAt:      now,
	}

	var termID string
	var createdAliases []CreatedAlias

	err := store.DB().Transaction(func(tx *gorm.DB) error {
		termID = GenerateID()
		termRow := orm.Word{
			ID:            termID,
			Word:          term,
			WordKind:      orm.WordKindTerm,
			GroupID:       groupID,
			Description:   desc,
			Source:        src,
			ReferenceInfo: ref,
			Locked:        body.Lock,
			WordBase:      base,
		}
		if err := tx.Create(&termRow).Error; err != nil {
			return err
		}
		for _, a := range aliases {
			aid := GenerateID()
			ar := orm.Word{
				ID:            aid,
				Word:          a,
				WordKind:      orm.WordKindAlias,
				GroupID:       groupID,
				Description:   desc,
				Source:        src,
				ReferenceInfo: ref,
				Locked:        body.Lock,
				WordBase:      base,
			}
			if err := tx.Create(&ar).Error; err != nil {
				return err
			}
			createdAliases = append(createdAliases, CreatedAlias{ID: aid, Word: a})
		}
		return nil
	})
	if err != nil {
		log.Logger.Error().Err(err).Str("term_id", termID).Msg("create word_group rows failed")
		common.ReplyErr(w, "create word group failed", http.StatusInternalServerError)
		return
	}

	common.ReplyOK(w, CreateWordGroupResponse{
		TermID:      termID,
		Term:        term,
		GroupID:     groupID,
		Aliases:     createdAliases,
		Description: desc,
		Source:      src,
		Reference:   ref,
		Lock:        body.Lock,
	})
}

// CheckWordsExist returns words among term + aliases that already exist in the words table for the request user.
func CheckWordsExist(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		common.ReplyErr(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body CheckWordsExistRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "invalid body", err), http.StatusBadRequest)
		return
	}
	candidates := uniqueWordCandidates(body.Term, body.Aliases)
	if len(candidates) == 0 {
		common.ReplyErr(w, "term and aliases are empty", http.StatusBadRequest)
		return
	}
	userID := store.UserID(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	var hits []string
	q := store.DB().Model(&orm.Word{}).
		Where("word IN ? AND create_user_id = ? AND deleted_at IS NULL", candidates, userID).
		Distinct("word").
		Pluck("word", &hits)
	if q.Error != nil {
		log.Logger.Error().Err(q.Error).Msg("check words exist query failed")
		common.ReplyErr(w, "check words exist failed", http.StatusInternalServerError)
		return
	}
	hit := make(map[string]struct{}, len(hits))
	for _, s := range hits {
		hit[s] = struct{}{}
	}
	existing := make([]string, 0, len(hits))
	for _, c := range candidates {
		if _, ok := hit[c]; ok {
			existing = append(existing, c)
		}
	}
	common.ReplyOK(w, CheckWordsExistResponse{Existing: existing})
}

// deleteWordGroupsForUser soft-deletes active word rows for the given group_ids owned by userID.
// It returns distinct group_ids that had at least one active row, and total rows updated.
func deleteWordGroupsForUser(db *gorm.DB, userID string, groupIDs []string) ([]string, int64, error) {
	if len(groupIDs) == 0 {
		return nil, 0, nil
	}
	var hitGroups []string
	if err := db.Model(&orm.Word{}).
		Where("group_id IN ? AND create_user_id = ? AND deleted_at IS NULL", groupIDs, userID).
		Distinct("group_id").
		Pluck("group_id", &hitGroups).Error; err != nil {
		return nil, 0, err
	}
	if len(hitGroups) == 0 {
		return nil, 0, nil
	}
	now := time.Now().UTC()
	tx := db.Model(&orm.Word{}).
		Where("group_id IN ? AND create_user_id = ? AND deleted_at IS NULL", hitGroups, userID).
		Updates(map[string]interface{}{
			"deleted_at": now,
			"updated_at": now,
		})
	if tx.Error != nil {
		return nil, 0, tx.Error
	}
	return hitGroups, tx.RowsAffected, nil
}

// DeleteWordGroup soft-deletes all active words rows for the given group_id owned by the request user.
func DeleteWordGroup(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodDelete {
		common.ReplyErr(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	groupID := strings.TrimSpace(common.PathVar(r, "group_id"))
	if groupID == "" {
		common.ReplyErr(w, "missing group_id", http.StatusBadRequest)
		return
	}
	userID := store.UserID(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	db := store.DB()
	hitGroups, rows, err := deleteWordGroupsForUser(db, userID, []string{groupID})
	if err != nil {
		log.Logger.Error().Err(err).Str("group_id", groupID).Msg("delete word_group failed")
		common.ReplyErr(w, "delete word group failed", http.StatusInternalServerError)
		return
	}
	if len(hitGroups) == 0 {
		common.ReplyErr(w, "word group not found", http.StatusNotFound)
		return
	}
	common.ReplyOK(w, DeleteWordGroupResponse{GroupID: groupID, DeletedRows: rows})
}

// BatchDeleteWordGroups soft-deletes active word rows for each requested group_id owned by the request user.
func BatchDeleteWordGroups(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		common.ReplyErr(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var body BatchDeleteWordGroupsRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "invalid body", err), http.StatusBadRequest)
		return
	}
	uniqueIDs := make([]string, 0, len(body.GroupIDs))
	seen := make(map[string]struct{}, len(body.GroupIDs))
	for _, id := range body.GroupIDs {
		id = strings.TrimSpace(id)
		if id == "" {
			continue
		}
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		uniqueIDs = append(uniqueIDs, id)
	}
	if len(uniqueIDs) == 0 {
		common.ReplyErr(w, "group_ids required", http.StatusBadRequest)
		return
	}

	userID := store.UserID(r)
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	db := store.DB()
	hitGroups, rows, err := deleteWordGroupsForUser(db, userID, uniqueIDs)
	if err != nil {
		log.Logger.Error().Err(err).Msg("batch delete word_group failed")
		common.ReplyErr(w, "batch delete word group failed", http.StatusInternalServerError)
		return
	}
	if len(hitGroups) == 0 {
		common.ReplyErr(w, "word group not found", http.StatusNotFound)
		return
	}
	common.ReplyOK(w, BatchDeleteWordGroupsResponse{GroupIDs: hitGroups, DeletedRows: rows})
}

func uniqueWordCandidates(term string, aliases []string) []string {
	term = strings.TrimSpace(term)
	var out []string
	seen := make(map[string]struct{})
	if term != "" {
		out = append(out, term)
		seen[term] = struct{}{}
	}
	for _, a := range normalizeAliases(aliases) {
		if _, ok := seen[a]; ok {
			continue
		}
		out = append(out, a)
		seen[a] = struct{}{}
	}
	return out
}

func normalizeAliases(raw []string) []string {
	var out []string
	for _, s := range raw {
		s = strings.TrimSpace(s)
		if s == "" {
			continue
		}
		out = append(out, s)
	}
	return out
}

func normalizeSource(s string) string {
	s = strings.TrimSpace(strings.ToLower(s))
	switch s {
	case "", "user", "用户":
		return "user"
	case "ai", "系统":
		return "ai"
	default:
		return ""
	}
}

// GenerateID returns a random 32-char hex id (UUID v4, no dashes). Each call is independent.
func GenerateID() string {
	u := uuid.New()
	return hex.EncodeToString(u[:])
}
