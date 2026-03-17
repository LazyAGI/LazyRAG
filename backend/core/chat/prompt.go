package chat

import (
	"encoding/json"
	"net/http"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"lazyrag/core/common/orm"
	corestore "lazyrag/core/store"

	"github.com/gorilla/mux"
)

const (
	promptNameMaxLen    = 100
	promptContentMaxLen = 800
)

func promptNameFromPath(r *http.Request) string {
	raw := mux.Vars(r)["name"]
	raw = strings.TrimPrefix(raw, "prompts/")
	raw = strings.TrimPrefix(raw, "/")
	return raw
}

// writePromptJSON 直接输出 JSON（不包 code/message/data 壳），与 neutrino ragservice HTTP 网关保持一致。
func writePromptJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	if v == nil {
		_, _ = w.Write([]byte("{}"))
		return
	}
	_ = json.NewEncoder(w).Encode(v)
}

// CreatePrompt 对应 POST /api/v1/prompts
func CreatePrompt(w http.ResponseWriter, r *http.Request) {
	var body struct {
		DisplayName string `json:"display_name"`
		Content     string `json:"content"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid body", http.StatusBadRequest)
		return
	}
	displayName := strings.TrimSpace(body.DisplayName)
	content := body.Content
	if utf8.RuneCountInString(displayName) > promptNameMaxLen {
		http.Error(w, "name too long", http.StatusBadRequest)
		return
	}
	if utf8.RuneCountInString(content) > promptContentMaxLen {
		http.Error(w, "content too long", http.StatusBadRequest)
		return
	}
	if displayName == "" || strings.TrimSpace(content) == "" {
		http.Error(w, "display_name and content required", http.StatusBadRequest)
		return
	}

	userID := corestore.UserID(r)
	userName := corestore.UserName(r)
	if userID == "" {
		http.Error(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	now := time.Now().UTC()
	p := orm.Prompt{
		ID:      newID("p_"),
		Name:    displayName,
		Content: content,
		BaseModel: orm.BaseModel{
			CreateUserID:   userID,
			CreateUserName: userName,
			CreatedAt:      now,
			UpdatedAt:      now,
		},
	}
	if err := corestore.DB().Create(&p).Error; err != nil {
		http.Error(w, "prompt existed", http.StatusConflict)
		return
	}

	writePromptJSON(w, http.StatusOK, map[string]any{
		"name":         "prompts/" + p.ID,
		"id":           p.ID,
		"content":      p.Content,
		"display_name": p.Name,
		"is_default":   false,
	})
}

// UpdatePrompt 对应 PATCH /api/v1/prompts/{name}
func UpdatePrompt(w http.ResponseWriter, r *http.Request) {
	promptID := promptNameFromPath(r)
	if promptID == "" {
		http.Error(w, "invalid prompt name", http.StatusBadRequest)
		return
	}
	var body struct {
		DisplayName string `json:"display_name"`
		Content     string `json:"content"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		http.Error(w, "invalid body", http.StatusBadRequest)
		return
	}
	displayName := strings.TrimSpace(body.DisplayName)
	content := body.Content
	if displayName == "" && content == "" {
		http.Error(w, "display_name/content required", http.StatusBadRequest)
		return
	}
	if displayName != "" && utf8.RuneCountInString(displayName) > promptNameMaxLen {
		http.Error(w, "name too long", http.StatusBadRequest)
		return
	}
	if content != "" && utf8.RuneCountInString(content) > promptContentMaxLen {
		http.Error(w, "content too long", http.StatusBadRequest)
		return
	}

	userID := corestore.UserID(r)
	if userID == "" {
		http.Error(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}

	var p orm.Prompt
	if err := corestore.DB().Where("id = ? AND create_user_id = ?", promptID, userID).First(&p).Error; err != nil {
		http.Error(w, "prompt not found", http.StatusNotFound)
		return
	}

	updates := map[string]any{"updated_at": time.Now().UTC()}
	if content != "" {
		updates["content"] = content
	}
	if displayName != "" {
		updates["name"] = displayName
	}
	if err := corestore.DB().Model(&orm.Prompt{}).Where("id = ? AND create_user_id = ?", promptID, userID).Updates(updates).Error; err != nil {
		http.Error(w, "update failed", http.StatusInternalServerError)
		return
	}
	_ = corestore.DB().Where("id = ? AND create_user_id = ?", promptID, userID).First(&p).Error

	var dpCount int64
	_ = corestore.DB().Model(&orm.DefaultPrompt{}).
		Where("create_user_id = ? AND prompt_id = ?", userID, promptID).
		Count(&dpCount).Error

	writePromptJSON(w, http.StatusOK, map[string]any{
		"name":         "prompts/" + p.ID,
		"id":           p.ID,
		"content":      p.Content,
		"display_name": p.Name,
		"is_default":   dpCount > 0,
	})
}

// DeletePrompt 对应 DELETE /api/v1/prompts/{name}
func DeletePrompt(w http.ResponseWriter, r *http.Request) {
	promptID := promptNameFromPath(r)
	if promptID == "" {
		http.Error(w, "invalid prompt name", http.StatusBadRequest)
		return
	}
	userID := corestore.UserID(r)
	if userID == "" {
		http.Error(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	_ = corestore.DB().Where("create_user_id = ? AND prompt_id = ?", userID, promptID).Delete(&orm.DefaultPrompt{}).Error
	if err := corestore.DB().Where("id = ? AND create_user_id = ?", promptID, userID).Delete(&orm.Prompt{}).Error; err != nil {
		http.Error(w, "delete failed", http.StatusInternalServerError)
		return
	}
	// 与 neurtrino 一致：200 + 空 JSON
	writePromptJSON(w, http.StatusOK, nil)
}

// GetPrompt 对应 GET /api/v1/prompts/{name}
func GetPrompt(w http.ResponseWriter, r *http.Request) {
	promptID := promptNameFromPath(r)
	if promptID == "" {
		http.Error(w, "invalid prompt name", http.StatusBadRequest)
		return
	}
	userID := corestore.UserID(r)
	if userID == "" {
		http.Error(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	var p orm.Prompt
	if err := corestore.DB().Where("id = ? AND create_user_id = ?", promptID, userID).First(&p).Error; err != nil {
		http.Error(w, "prompt not found", http.StatusNotFound)
		return
	}
	var dpCount int64
	_ = corestore.DB().Model(&orm.DefaultPrompt{}).
		Where("create_user_id = ? AND prompt_id = ?", userID, promptID).
		Count(&dpCount).Error

	writePromptJSON(w, http.StatusOK, map[string]any{
		"name":         "prompts/" + p.ID,
		"id":           p.ID,
		"content":      p.Content,
		"display_name": p.Name,
		"is_default":   dpCount > 0,
	})
}

// ListPrompts 对应 GET /api/v1/prompts（支持 page_size、page_token）
func ListPrompts(w http.ResponseWriter, r *http.Request) {
	userID := corestore.UserID(r)
	if userID == "" {
		http.Error(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	pageSize := 50
	if s := r.URL.Query().Get("page_size"); s != "" {
		if n, err := strconv.Atoi(s); err == nil && n > 0 && n <= 1000 {
			pageSize = n
		}
	}
	start := 0
	if tok := strings.TrimSpace(r.URL.Query().Get("page_token")); tok != "" {
		if n, err := strconv.Atoi(tok); err == nil && n >= 0 {
			start = n
		}
	}

	var dps []orm.DefaultPrompt
	_ = corestore.DB().Where("create_user_id = ?", userID).Find(&dps).Error
	defaultIDs := map[string]bool{}
	for _, dp := range dps {
		defaultIDs[dp.PromptID] = true
	}

	var ps []orm.Prompt
	if err := corestore.DB().Where("create_user_id = ?", userID).Order("created_at desc").Find(&ps).Error; err != nil {
		http.Error(w, "list failed", http.StatusInternalServerError)
		return
	}
	total := len(ps)

	outAll := make([]map[string]any, 0, total)
	for _, p := range ps {
		if defaultIDs[p.ID] {
			outAll = append(outAll, map[string]any{
				"name":         "prompts/" + p.ID,
				"id":           p.ID,
				"content":      p.Content,
				"display_name": p.Name,
				"is_default":   true,
			})
		}
	}
	for _, p := range ps {
		if !defaultIDs[p.ID] {
			outAll = append(outAll, map[string]any{
				"name":         "prompts/" + p.ID,
				"id":           p.ID,
				"content":      p.Content,
				"display_name": p.Name,
				"is_default":   false,
			})
		}
	}

	if start >= len(outAll) {
		writePromptJSON(w, http.StatusOK, map[string]any{
			"prompts":         []any{},
			"next_page_token": "",
			"total":           int64(total),
		})
		return
	}
	end := start + pageSize
	if end > len(outAll) {
		end = len(outAll)
	}
	next := ""
	if start+pageSize < total {
		next = strconv.Itoa(start + pageSize)
	}
	writePromptJSON(w, http.StatusOK, map[string]any{
		"prompts":         outAll[start:end],
		"next_page_token": next,
		"total":           int64(total),
	})
}

// SetDefaultPrompt 对应 POST /api/v1/prompts/{name}:setDefault
func SetDefaultPrompt(w http.ResponseWriter, r *http.Request) {
	promptID := promptNameFromPath(r)
	if promptID == "" {
		http.Error(w, "invalid prompt name", http.StatusBadRequest)
		return
	}
	userID := corestore.UserID(r)
	userName := corestore.UserName(r)
	if userID == "" {
		http.Error(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	var p orm.Prompt
	if err := corestore.DB().Where("id = ? AND create_user_id = ?", promptID, userID).First(&p).Error; err != nil {
		http.Error(w, "prompt not found", http.StatusNotFound)
		return
	}
	now := time.Now().UTC()
	dp := orm.DefaultPrompt{
		PromptID:   promptID,
		PromptName: p.Name,
		BaseModel: orm.BaseModel{
			CreateUserID:   userID,
			CreateUserName: userName,
			CreatedAt:      now,
			UpdatedAt:      now,
		},
	}
	_ = corestore.DB().Create(&dp).Error
	writePromptJSON(w, http.StatusOK, nil)
}

// UnsetDefaultPrompt 对应 POST /api/v1/prompts/{name}:unsetDefault
func UnsetDefaultPrompt(w http.ResponseWriter, r *http.Request) {
	promptID := promptNameFromPath(r)
	if promptID == "" {
		http.Error(w, "invalid prompt name", http.StatusBadRequest)
		return
	}
	userID := corestore.UserID(r)
	if userID == "" {
		http.Error(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	_ = corestore.DB().Where("create_user_id = ? AND prompt_id = ?", userID, promptID).Delete(&orm.DefaultPrompt{}).Error
	writePromptJSON(w, http.StatusOK, nil)
}

