package modelprovider

import (
	"context"
	"net/http"
	"strings"
	"time"

	"gorm.io/gorm"

	"lazymind/core/common"
	"lazymind/core/common/orm"
	"lazymind/core/store"
)

type listItem struct {
	ID                     string `json:"id"`
	DefaultModelProviderID string `json:"default_model_provider_id"`
	Name                   string `json:"name"`
	Description            string `json:"description"`
	BaseURL                string `json:"base_url"`
}

type listResponse struct {
	Providers []listItem `json:"providers"`
}

// ListUserProviders returns the current user's model providers. When the list
// is empty, all DefaultModelProvider rows are copied into user_model_providers.
// Optional query param: keyword — substring match on name (SQL LIKE).
func ListUserProviders(w http.ResponseWriter, r *http.Request) {
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

	userName := strings.TrimSpace(store.UserName(r))
	if err := seedUserProvidersIfEmpty(r.Context(), db, userID, userName); err != nil {
		common.ReplyErr(w, "sync model providers failed", http.StatusInternalServerError)
		return
	}

	keyword := strings.TrimSpace(r.URL.Query().Get("keyword"))
	q := db.WithContext(r.Context()).Model(&orm.UserModelProvider{}).
		Where("create_user_id = ? AND deleted_at IS NULL", userID)
	if keyword != "" {
		q = q.Where("name LIKE ?", "%"+keyword+"%")
	}

	var rows []orm.UserModelProvider
	if err := q.Order("name DESC").Find(&rows).Error; err != nil {
		common.ReplyErr(w, "list model providers failed", http.StatusInternalServerError)
		return
	}

	out := make([]listItem, 0, len(rows))
	for i := range rows {
		row := rows[i]
		out = append(out, listItem{
			ID:                     row.ID,
			DefaultModelProviderID: row.DefaultModelProviderID,
			Name:                   row.Name,
			Description:            row.Description,
			BaseURL:                row.BaseURL,
		})
	}
	common.ReplyOK(w, listResponse{Providers: out})
}

// seedUserGroupsFromAdmin copies all groups (and their models) from the system-admin user to the
// target user, but only when the target user has no groups yet. The admin user is identified by
// finding the user whose groups have create_user_name matching the admin username stored in the
// ACL service. This is a best-effort operation: if no admin groups exist, we silently skip.
func seedUserGroupsFromAdmin(ctx context.Context, db *gorm.DB, userID, userName string) error {
	// Fast path: user already has groups — nothing to do.
	var existing int64
	if err := db.WithContext(ctx).Model(&orm.UserModelProviderGroup{}).
		Where("create_user_id = ? AND deleted_at IS NULL", userID).
		Count(&existing).Error; err != nil {
		return err
	}
	if existing > 0 {
		return nil
	}

	// Find the admin user by looking for the user who owns groups with create_user_name = 'admin'.
	// We use a subquery to find the admin's user_id from their groups.
	type adminInfo struct {
		AdminID   string
		AdminName string
	}
	var admin adminInfo
	err := db.WithContext(ctx).Raw(`
		SELECT create_user_id AS admin_id, create_user_name AS admin_name
		FROM user_model_provider_groups
		WHERE deleted_at IS NULL
		  AND create_user_id != ?
		  AND create_user_name = 'admin'
		LIMIT 1
	`, userID).Scan(&admin).Error
	if err != nil || admin.AdminID == "" {
		// Fallback: try any user with groups who is not the current user.
		err = db.WithContext(ctx).Raw(`
			SELECT create_user_id AS admin_id, create_user_name AS admin_name
			FROM user_model_provider_groups
			WHERE deleted_at IS NULL
			  AND create_user_id != ?
			LIMIT 1
		`, userID).Scan(&admin).Error
		if err != nil || admin.AdminID == "" {
			return nil // No admin groups found; skip silently.
		}
	}
	adminID := admin.AdminID

	// Load admin's groups and their models.
	var adminGroups []orm.UserModelProviderGroup
	if err := db.WithContext(ctx).
		Where("create_user_id = ? AND deleted_at IS NULL", adminID).
		Find(&adminGroups).Error; err != nil {
		return err
	}
	if len(adminGroups) == 0 {
		return nil
	}

	// Build a map from admin's provider ID → user's provider ID (matched by default_model_provider_id).
	var adminProviders []orm.UserModelProvider
	if err := db.WithContext(ctx).
		Where("create_user_id = ? AND deleted_at IS NULL", adminID).
		Find(&adminProviders).Error; err != nil {
		return err
	}
	var userProviders []orm.UserModelProvider
	if err := db.WithContext(ctx).
		Where("create_user_id = ? AND deleted_at IS NULL", userID).
		Find(&userProviders).Error; err != nil {
		return err
	}
	// Map default_model_provider_id → user's UserModelProvider.ID
	userProviderByDefault := make(map[string]string, len(userProviders))
	for _, p := range userProviders {
		userProviderByDefault[p.DefaultModelProviderID] = p.ID
	}
	// Map admin's UserModelProvider.ID → default_model_provider_id
	adminProviderDefault := make(map[string]string, len(adminProviders))
	for _, p := range adminProviders {
		adminProviderDefault[p.ID] = p.DefaultModelProviderID
	}

	now := time.Now()
	return db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		for _, ag := range adminGroups {
			defaultProviderID := adminProviderDefault[ag.UserModelProviderID]
			userProviderID := userProviderByDefault[defaultProviderID]
			if userProviderID == "" {
				continue // No matching provider for this user; skip.
			}

			newGroupID := common.GenerateID()
			newGroup := orm.UserModelProviderGroup{
				ID:                  newGroupID,
				UserModelProviderID: userProviderID,
				Name:                ag.Name,
				BaseURL:             ag.BaseURL,
				APIKey:              ag.APIKey,
				IsVerified:          ag.IsVerified,
				BaseModel: orm.BaseModel{
					CreateUserID:   userID,
					CreateUserName: userName,
					CreatedAt:      now,
					UpdatedAt:      now,
				},
			}
			if err := tx.Create(&newGroup).Error; err != nil {
				return err
			}

			// Copy models for this group.
			var adminModels []orm.UserModelProviderGroupModel
			if err := tx.Where("user_model_provider_group_id = ? AND deleted_at IS NULL", ag.ID).
				Find(&adminModels).Error; err != nil {
				return err
			}
			for _, am := range adminModels {
				newModel := orm.UserModelProviderGroupModel{
					ID:                       common.GenerateID(),
					UserModelProviderID:      userProviderID,
					UserModelProviderGroupID: newGroupID,
					ProviderName:             am.ProviderName,
					Name:                     am.Name,
					ModelType:                am.ModelType,
					BaseURL:                  am.BaseURL,
					IsDefault:                am.IsDefault,
					BaseModel: orm.BaseModel{
						CreateUserID:   userID,
						CreateUserName: userName,
						CreatedAt:      now,
						UpdatedAt:      now,
					},
				}
				if err := tx.Create(&newModel).Error; err != nil {
					return err
				}
			}
		}
		return nil
	})
}

// ListUserProvidersWithGroups returns user_model_providers rows that have at least one non-deleted
// user_model_provider_groups row for the current user (distinct parent ids from groups, then load providers).
func ListUserProvidersWithGroups(w http.ResponseWriter, r *http.Request) {
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
	userName := strings.TrimSpace(store.UserName(r))

	// Seed groups from admin on first visit (best-effort, non-fatal).
	if err := seedUserGroupsFromAdmin(r.Context(), db, userID, userName); err != nil {
		// Log but don't fail the request — user can still add groups manually.
		_ = err
	}

	var providerIDs []string
	if err := db.WithContext(r.Context()).Model(&orm.UserModelProviderGroup{}).
		Where("create_user_id = ? AND deleted_at IS NULL", userID).
		Distinct("user_model_provider_id").
		Pluck("user_model_provider_id", &providerIDs).Error; err != nil {
		common.ReplyErr(w, "list group parent ids failed", http.StatusInternalServerError)
		return
	}
	if len(providerIDs) == 0 {
		common.ReplyOK(w, listResponse{Providers: []listItem{}})
		return
	}

	var rows []orm.UserModelProvider
	if err := db.WithContext(r.Context()).
		Where("id IN ? AND create_user_id = ? AND deleted_at IS NULL", providerIDs, userID).
		Order("name ASC").
		Find(&rows).Error; err != nil {
		common.ReplyErr(w, "list model providers failed", http.StatusInternalServerError)
		return
	}

	out := make([]listItem, 0, len(rows))
	for i := range rows {
		row := rows[i]
		out = append(out, listItem{
			ID:                     row.ID,
			DefaultModelProviderID: row.DefaultModelProviderID,
			Name:                   row.Name,
			Description:            row.Description,
			BaseURL:                row.BaseURL,
		})
	}
	common.ReplyOK(w, listResponse{Providers: out})
}

func seedUserProvidersIfEmpty(ctx context.Context, db *gorm.DB, userID, userName string) error {
	return db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		var n int64
		if err := tx.Model(&orm.UserModelProvider{}).
			Where("create_user_id = ? AND deleted_at IS NULL", userID).
			Count(&n).Error; err != nil {
			return err
		}
		if n > 0 {
			return nil
		}

		var defs []orm.DefaultModelProvider
		if err := tx.Find(&defs).Error; err != nil {
			return err
		}
		if len(defs) == 0 {
			return nil
		}

		now := time.Now()
		batch := make([]orm.UserModelProvider, len(defs))
		for i := range defs {
			d := defs[i]
			batch[i] = orm.UserModelProvider{
				ID:                     common.GenerateID(),
				DefaultModelProviderID: d.ID,
				Name:                   d.Name,
				Description:            d.Description,
				BaseURL:                d.BaseURL,
				BaseModel: orm.BaseModel{
					CreateUserID:   userID,
					CreateUserName: userName,
					CreatedAt:      now,
					UpdatedAt:      now,
					DeletedAt:      nil,
				},
			}
		}
		return tx.Create(&batch).Error
	})
}
