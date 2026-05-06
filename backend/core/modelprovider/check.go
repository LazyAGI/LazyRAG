package modelprovider

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"lazyrag/core/common"
	"lazyrag/core/log"
	"lazyrag/core/store"
)

const modelProviderCheckTimeout = 90 * time.Second

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
	Success bool            `json:"success"`
	Message string          `json:"message"`
	Model   string          `json:"model,omitempty"`
	Source  string          `json:"source,omitempty"`
	URL     string          `json:"url,omitempty"`
	Result  json.RawMessage `json:"result,omitempty"`
}

// CheckModelProviderData is the only field in core envelope data for this handler.
type CheckModelProviderData struct {
	Success bool `json:"success"`
}

// CheckModelProvider proxies to the algorithm service /api/model/check for connectivity validation.
func CheckModelProvider(w http.ResponseWriter, r *http.Request) {
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

	upstream := common.JoinURL(common.AlgoServiceEndpoint(), "/api/model/check")
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
		common.ReplyErr(w, err.Error(), http.StatusBadGateway)
		return
	}
	common.ReplyOK(w, CheckModelProviderData{Success: algo.Success})
}
