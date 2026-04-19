package authclient

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const internalTokenHeader = "X-LazyRAG-Internal-Token"

type TokenResponse struct {
	ConnectionID string     `json:"connection_id"`
	Provider     string     `json:"provider"`
	AccessToken  string     `json:"access_token"`
	TokenType    string     `json:"token_type"`
	ExpiresAt    *time.Time `json:"expires_at"`
	Status       string     `json:"status"`
}

type Client struct {
	baseURL       string
	internalToken string
	httpClient    *http.Client
}

func New(baseURL, internalToken string, timeout time.Duration) *Client {
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	return &Client{
		baseURL:       strings.TrimRight(strings.TrimSpace(baseURL), "/"),
		internalToken: strings.TrimSpace(internalToken),
		httpClient: &http.Client{
			Timeout: timeout,
		},
	}
}

func (c *Client) GetAccessToken(ctx context.Context, connectionID string) (TokenResponse, error) {
	connectionID = strings.TrimSpace(connectionID)
	if connectionID == "" {
		return TokenResponse{}, fmt.Errorf("connection_id is required")
	}
	if c.baseURL == "" {
		return TokenResponse{}, fmt.Errorf("auth service base url is empty")
	}
	endpoint := c.baseURL + "/api/authservice/v1/cloud/connections/" + url.PathEscape(connectionID) + "/token"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return TokenResponse{}, err
	}
	if c.internalToken != "" {
		req.Header.Set(internalTokenHeader, c.internalToken)
	}
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return TokenResponse{}, err
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return TokenResponse{}, err
	}
	if resp.StatusCode >= 400 {
		return TokenResponse{}, fmt.Errorf("auth service returned %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	var tokenResp TokenResponse
	if err := json.Unmarshal(body, &tokenResp); err == nil {
		if strings.TrimSpace(tokenResp.AccessToken) != "" {
			return tokenResp, nil
		}
	}

	// Compatibility with wrapped payload responses.
	var wrapped struct {
		Data TokenResponse `json:"data"`
	}
	if err := json.Unmarshal(body, &wrapped); err != nil {
		return TokenResponse{}, fmt.Errorf("decode auth token response failed: %w", err)
	}
	if strings.TrimSpace(wrapped.Data.AccessToken) == "" {
		return TokenResponse{}, fmt.Errorf("auth token response missing access_token")
	}
	return wrapped.Data, nil
}
