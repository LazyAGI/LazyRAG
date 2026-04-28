package common

import (
	"os"
	"strings"
)

// ChatServiceEndpoint returns the base URL for the chat/generation service.
func ChatServiceEndpoint() string {
	if u := strings.TrimSpace(os.Getenv("LAZYRAG_CHAT_SERVICE_URL")); u != "" {
		return strings.TrimRight(u, "/")
	}
	return "http://chat:8046"
}

// AuthServiceBaseURL returns the base URL for auth-service APIs.
func AuthServiceBaseURL() string {
	if u := strings.TrimSpace(os.Getenv("LAZYRAG_AUTH_SERVICE_URL")); u != "" {
		base := strings.TrimRight(u, "/")
		if strings.HasSuffix(base, "/api/authservice") {
			return base
		}
		return base + "/api/authservice"
	}
	return "http://auth-service:8000/api/authservice"
}

// AlgoServiceEndpoint text base URL（text path）。
// text LAZYRAG_ALGO_SERVICE_URL text；textSettextDefaulttext，text。
func AlgoServiceEndpoint() string {
	if u := strings.TrimSpace(os.Getenv("LAZYRAG_ALGO_SERVICE_URL")); u != "" {
		return strings.TrimRight(u, "/")
	}
	return "http://10.119.24.129:8850"
}
