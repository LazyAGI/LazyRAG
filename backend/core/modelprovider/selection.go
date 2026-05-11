package modelprovider

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"gorm.io/gorm"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/store"
)

// Allowed keys match frontend modelTypeMap (selection slot types).
var allowedSelectionModelTypes = map[string]struct{}{
	"llm-evo":              {},
	"llm-chat":             {},
	"VLM":                  {},
	"text2image":           {},
	"embedding":            {},
	"tts":                  {},
	"image_editing":        {},
	"stt":                  {},
	"rerank":               {},
	"multimodal_embedding": {},
}

type selectedModelUpsertItem struct {
	ModelType string `json:"model_type"`
	ModelID   string `json:"model_id"`
}

type setSelectedModelsRequest struct {
	Selections []selectedModelUpsertItem `json:"selections"`
}

type selectedModelItem struct {
	ModelType                string `json:"model_type"`
	ModelID                  string `json:"model_id"`
	UserModelProviderID      string `json:"user_model_provider_id"`
	UserModelProviderGroupID string `json:"user_model_provider_group_id"`
	Name                     string `json:"name"`
	ProviderName             string `json:"provider_name"`
	GroupName                string `json:"group_name"`
	BaseURL                  string `json:"base_url"`
}

type selectedModelsResponse struct {
	Selections []selectedModelItem `json:"selections"`
}

// GetSelectedModels returns selected model rows for the current user.
func GetSelectedModels(w http.ResponseWriter, r *http.Request) {
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
	out, err := loadSelectedModels(r.Context(), db, userID)
	if err != nil {
		common.ReplyErr(w, "query selected models failed", http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, selectedModelsResponse{Selections: out})
}

// SetSelectedModels saves selected model rows by model_type for the current user.
func SetSelectedModels(w http.ResponseWriter, r *http.Request) {
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

	var req setSelectedModelsRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if len(req.Selections) == 0 {
		common.ReplyErr(w, "selections required", http.StatusBadRequest)
		return
	}

	modelIDSet := make(map[string]struct{}, len(req.Selections))
	selectionByType := make(map[string]string, len(req.Selections))
	modelIDs := make([]string, 0, len(req.Selections))
	for _, item := range req.Selections {
		modelType := strings.TrimSpace(item.ModelType)
		modelID := strings.TrimSpace(item.ModelID)
		if modelType == "" {
			common.ReplyErr(w, "model_type is required", http.StatusBadRequest)
			return
		}
		if _, ok := allowedSelectionModelTypes[modelType]; !ok {
			common.ReplyErr(w, "invalid model_type", http.StatusBadRequest)
			return
		}
		if _, exists := selectionByType[modelType]; exists {
			common.ReplyErr(w, "duplicate model_type in selections", http.StatusBadRequest)
			return
		}
		selectionByType[modelType] = modelID
		if modelID == "" {
			continue
		}
		if _, exists := modelIDSet[modelID]; !exists {
			modelIDSet[modelID] = struct{}{}
			modelIDs = append(modelIDs, modelID)
		}
	}

	var models []orm.UserModelProviderGroupModel
	if len(modelIDs) > 0 {
		if err := db.WithContext(r.Context()).
			Where("id IN ? AND create_user_id = ? AND deleted_at IS NULL", modelIDs, userID).
			Find(&models).Error; err != nil {
			common.ReplyErr(w, "query models failed", http.StatusInternalServerError)
			return
		}
	}
	modelByID := make(map[string]orm.UserModelProviderGroupModel, len(models))
	for _, m := range models {
		modelByID[m.ID] = m
	}
	for _, modelID := range selectionByType {
		if modelID == "" {
			continue
		}
		if _, ok := modelByID[modelID]; !ok {
			common.ReplyErr(w, "model not found", http.StatusBadRequest)
			return
		}
	}

	now := time.Now()
	if err := db.WithContext(r.Context()).Transaction(func(tx *gorm.DB) error {
		for modelType, modelID := range selectionByType {
			if modelID == "" {
				if err := tx.Where("user_id = ? AND model_type = ?", userID, modelType).
					Delete(&orm.UserSelectedModel{}).Error; err != nil {
					return err
				}
				continue
			}
			var row orm.UserSelectedModel
			err := tx.Where("user_id = ? AND model_type = ?", userID, modelType).Take(&row).Error
			if errors.Is(err, gorm.ErrRecordNotFound) {
				if err := tx.Model(&orm.UserSelectedModel{}).Create(map[string]any{
					"user_id":                            userID,
					"model_type":                         modelType,
					"user_model_provider_group_model_id": modelID,
					"user_name":                          userName,
					"created_at":                         now,
					"updated_at":                         now,
				}).Error; err != nil {
					return err
				}
				continue
			}
			if err != nil {
				return err
			}
			if err := tx.Model(&orm.UserSelectedModel{}).
				Where("id = ?", row.ID).
				Updates(map[string]any{
					"user_model_provider_group_model_id": modelID,
					"user_name":                          userName,
					"updated_at":                         now,
				}).Error; err != nil {
				return err
			}
		}
		return nil
	}); err != nil {
		common.ReplyErr(w, "save selected models failed", http.StatusInternalServerError)
		return
	}

	out, err := loadSelectedModels(r.Context(), db, userID)
	if err != nil {
		common.ReplyErr(w, "query selected models failed", http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, selectedModelsResponse{Selections: out})
}

func loadSelectedModels(ctx context.Context, db *gorm.DB, userID string) ([]selectedModelItem, error) {
	out := make([]selectedModelItem, 0)
	err := db.WithContext(ctx).
		Table("user_selected_models usm").
		Select(
			"usm.model_type, "+
				"usm.user_model_provider_group_model_id AS model_id, "+
				"m.user_model_provider_id, "+
				"m.user_model_provider_group_id, "+
				"m.name, "+
				"m.provider_name, "+
				"g.name AS group_name, "+
				"m.base_url",
		).
		Joins(
			"JOIN user_model_provider_group_models m ON "+
				"m.id = usm.user_model_provider_group_model_id AND "+
				"m.create_user_id = usm.user_id AND "+
				"m.deleted_at IS NULL",
		).
		Joins(
			"JOIN user_model_provider_groups g ON "+
				"g.id = m.user_model_provider_group_id AND "+
				"g.create_user_id = usm.user_id AND "+
				"g.deleted_at IS NULL",
		).
		Where("usm.user_id = ?", strings.TrimSpace(userID)).
		Order("usm.model_type ASC").
		Scan(&out).Error
	return out, err
}
