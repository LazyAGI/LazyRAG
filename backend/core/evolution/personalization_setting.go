package evolution

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

type personalizationSettingResponse struct {
	Enabled bool `json:"enabled"`
}

type personalizationSettingRequest struct {
	Enabled *bool `json:"enabled"`
}

func GetPersonalizationSetting(w http.ResponseWriter, r *http.Request) {
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

	enabled, err := LoadUserPersonalizationEnabled(r.Context(), db, userID)
	if err != nil {
		common.ReplyErr(w, "query personalization setting failed", http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, personalizationSettingResponse{Enabled: enabled})
}

func SetPersonalizationSetting(w http.ResponseWriter, r *http.Request) {
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

	var req personalizationSettingRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if req.Enabled == nil {
		common.ReplyErr(w, "enabled required", http.StatusBadRequest)
		return
	}

	enabled, err := UpsertUserPersonalizationEnabled(r.Context(), db, userID, userName, *req.Enabled)
	if err != nil {
		common.ReplyErr(w, "update personalization setting failed", http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, personalizationSettingResponse{Enabled: enabled})
}

func LoadUserPersonalizationEnabled(ctx context.Context, db *gorm.DB, userID string) (bool, error) {
	var row orm.UserPersonalizationSetting
	err := db.WithContext(ctx).
		Where("user_id = ?", strings.TrimSpace(userID)).
		Take(&row).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return true, nil
	}
	if err != nil {
		return false, err
	}
	return row.Enabled, nil
}

func UpsertUserPersonalizationEnabled(ctx context.Context, db *gorm.DB, userID, userName string, enabled bool) (bool, error) {
	userID = strings.TrimSpace(userID)
	userName = strings.TrimSpace(userName)
	now := time.Now()

	var row orm.UserPersonalizationSetting
	err := db.WithContext(ctx).Where("user_id = ?", userID).Take(&row).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		if err := db.WithContext(ctx).Model(&orm.UserPersonalizationSetting{}).Create(map[string]any{
			"user_id":         userID,
			"enabled":         enabled,
			"updated_by":      userID,
			"updated_by_name": userName,
			"created_at":      now,
			"updated_at":      now,
		}).Error; err != nil {
			return false, err
		}
		return enabled, nil
	}
	if err != nil {
		return false, err
	}

	if err := db.WithContext(ctx).Model(&orm.UserPersonalizationSetting{}).
		Where("id = ?", row.ID).
		Updates(map[string]any{
			"enabled":         enabled,
			"updated_by":      userID,
			"updated_by_name": userName,
			"updated_at":      now,
		}).Error; err != nil {
		return false, err
	}
	return enabled, nil
}
