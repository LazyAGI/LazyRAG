package modelprovider

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/gorilla/mux"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/log"
	"lazyrag/core/store"
)

const modelProviderCheckTimeout = 5 * time.Minute

type checkModelProviderRequest struct {
	ProviderName string `json:"provider_name"`
	BaseURL      string `json:"base_url"`
	APIKey       string `json:"api_key"`
}

// algoModelCheckBody matches the algorithm POST /api/model/check JSON contract (lazyllm.OnlineModule).
type algoModelCheckBody struct {
	Model  string `json:"model,omitempty"`
	Source string `json:"source"`
	URL    string `json:"url"`
	APIKey string `json:"api_key"`
}

// modelCheckResponse mirrors the algorithm /api/model/check JSON (internal parse only).
type modelCheckResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
	Model   string `json:"model,omitempty"`
	Source  string `json:"source,omitempty"`
	URL     string `json:"url,omitempty"`
}

// CheckModelProviderData keeps only connectivity result for API response.
type CheckModelProviderData struct {
	Success bool `json:"success"`
}

// CheckGroup proxies to the algorithm service /api/model/check for connectivity validation.
func CheckGroup(w http.ResponseWriter, r *http.Request) {
	var req checkModelProviderRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	source := strings.TrimSpace(req.ProviderName)
	urlStr := strings.TrimSpace(req.BaseURL)
	apiKey := strings.TrimSpace(req.APIKey)
	if source == "" || urlStr == "" || apiKey == "" {
		common.ReplyErr(w, "provider_name, base_url, and api_key are required", http.StatusBadRequest)
		return
	}

	userID := strings.TrimSpace(store.UserID(r))
	if userID == "" {
		common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		return
	}
	parentID := strings.TrimSpace(mux.Vars(r)["model_provider_id"])
	groupID := strings.TrimSpace(mux.Vars(r)["group_id"])
	if parentID == "" || groupID == "" {
		common.ReplyErr(w, "missing model_provider_id or group_id", http.StatusBadRequest)
		return
	}
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}

	upstream := common.JoinURL(common.ChatServiceEndpoint(), "/api/model/check")
	body := algoModelCheckBody{
		Source: source,
		URL:    urlStr,
		APIKey: apiKey,
	}
	checkStart := time.Now()

	var algo modelCheckResponse
	if err := common.ApiPost(r.Context(), upstream, body, nil, &algo, modelProviderCheckTimeout); err != nil {
		log.Logger.Error().
			Err(err).
			Str("upstream", upstream).
			Str("provider_name", source).
			Str("base_url", urlStr).
			Str("user_id", userID).
			Dur("timeout", modelProviderCheckTimeout).
			Dur("elapsed", time.Since(checkStart)).
			Msg("model provider check failed")
		common.ReplyErrWithData(w, err.Error(), algo, http.StatusBadGateway)
		return
	}
	if algo.Success {
		now := time.Now()
		tx := db.WithContext(r.Context()).
			Model(&orm.UserModelProviderGroup{}).
			Where("id = ? AND user_model_provider_id = ? AND create_user_id = ? AND deleted_at IS NULL", groupID, parentID, userID).
			Updates(map[string]interface{}{
				"is_verified": true,
				"updated_at":  now,
			})
		if tx.Error != nil {
			common.ReplyErr(w, "update group verify status failed", http.StatusInternalServerError)
			return
		}
		if tx.RowsAffected == 0 {
			common.ReplyErr(w, "group not found", http.StatusNotFound)
			return
		}
	}
	common.ReplyOK(w, CheckModelProviderData{Success: algo.Success})
}
