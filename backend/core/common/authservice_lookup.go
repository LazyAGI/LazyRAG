package common

import (
	"context"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"
)

type authServiceGroupUserItem struct {
	UserID string `json:"user_id"`
}

type authServiceGroupUsersResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    struct {
		Users []authServiceGroupUserItem `json:"users"`
	} `json:"data"`
	Users []authServiceGroupUserItem `json:"users"`
}

// FetchUserNamesFromAuthService resolves user IDs to display names via auth-service.
func FetchUserNamesFromAuthService(r *http.Request, userIDs []string) map[string]string {
	out := map[string]string{}
	for _, userID := range compactNonEmptyStrings(userIDs) {
		var resp struct {
			Code    int    `json:"code"`
			Message string `json:"message"`
			Data    struct {
				UserID      string `json:"user_id"`
				Username    string `json:"username"`
				DisplayName string `json:"display_name"`
			} `json:"data"`
			UserID      string `json:"user_id"`
			Username    string `json:"username"`
			DisplayName string `json:"display_name"`
		}
		if err := ApiGet(requestContext(r), AuthServiceBaseURL()+"/user/"+url.PathEscape(userID), authServiceRequestHeaders(r), &resp, 3*time.Second); err != nil {
			continue
		}
		if userName := firstNonEmpty(resp.DisplayName, resp.Username, resp.Data.DisplayName, resp.Data.Username); userName != "" {
			out[userID] = userName
		}
	}
	return out
}

// FetchGroupNamesFromAuthService resolves group IDs to group names via auth-service.
func FetchGroupNamesFromAuthService(r *http.Request, groupIDs []string) map[string]string {
	out := map[string]string{}
	for _, groupID := range compactNonEmptyStrings(groupIDs) {
		var resp struct {
			Code    int    `json:"code"`
			Message string `json:"message"`
			Data    struct {
				GroupID   string `json:"group_id"`
				GroupName string `json:"group_name"`
			} `json:"data"`
			GroupID   string `json:"group_id"`
			GroupName string `json:"group_name"`
		}
		if err := ApiGet(requestContext(r), AuthServiceBaseURL()+"/group/"+url.PathEscape(groupID), authServiceRequestHeaders(r), &resp, 3*time.Second); err != nil {
			continue
		}
		if groupName := firstNonEmpty(resp.GroupName, resp.Data.GroupName); groupName != "" {
			out[groupID] = groupName
		}
	}
	return out
}

// FetchGroupUserIDsFromAuthService resolves group IDs to member user IDs via auth-service.
func FetchGroupUserIDsFromAuthService(r *http.Request, groupIDs []string) []string {
	seen := map[string]struct{}{}
	out := []string{}
	for _, groupID := range compactNonEmptyStrings(groupIDs) {
		groupPath := "/group/" + url.PathEscape(groupID) + "/user"
		groupQuery := "?active_only=true"
		endpoints := []struct {
			path    string
			headers map[string]string
		}{
			{path: groupPath + groupQuery, headers: authServiceRequestHeaders(r)},
			{path: groupPath + "/internal" + groupQuery, headers: authServiceInternalRequestHeaders(r)},
		}
		users := []authServiceGroupUserItem{}
		for _, endpoint := range endpoints {
			var resp authServiceGroupUsersResponse
			if err := ApiGet(requestContext(r), AuthServiceBaseURL()+endpoint.path, endpoint.headers, &resp, 3*time.Second); err != nil {
				continue
			}
			users = resp.Users
			if len(users) == 0 {
				users = resp.Data.Users
			}
			break
		}
		if len(users) == 0 {
			continue
		}
		for _, user := range users {
			userID := strings.TrimSpace(user.UserID)
			if userID == "" {
				continue
			}
			if _, exists := seen[userID]; exists {
				continue
			}
			seen[userID] = struct{}{}
			out = append(out, userID)
		}
	}
	return out
}

func authServiceRequestHeaders(r *http.Request) map[string]string {
	headers := map[string]string{}
	if r == nil {
		return headers
	}
	if value := strings.TrimSpace(r.Header.Get("Authorization")); value != "" {
		headers["Authorization"] = value
	}
	if value := UserID(r); value != "" {
		headers["X-User-Id"] = value
	}
	if value := UserName(r); value != "" {
		headers["X-User-Name"] = value
	}
	return headers
}

func authServiceInternalRequestHeaders(r *http.Request) map[string]string {
	headers := authServiceRequestHeaders(r)
	if value := strings.TrimSpace(os.Getenv("LAZYRAG_AUTH_SERVICE_INTERNAL_TOKEN")); value != "" {
		headers["X-LazyRAG-Internal-Token"] = value
	}
	return headers
}

func requestContext(r *http.Request) context.Context {
	if r != nil {
		return r.Context()
	}
	return context.Background()
}

func compactNonEmptyStrings(values []string) []string {
	out := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	return out
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
