package coreclient

import (
	"net/http"
	"testing"

	"github.com/lazyrag/scan_control_plane/internal/config"
)

func TestSetAuthHeadersIncludesBearerToken(t *testing.T) {
	t.Parallel()
	c := &httpClient{
		cfg: config.CoreConfig{
			UserID:    "scan-user",
			UserName:  "scan-user",
			AuthToken: "core-token-001",
		},
	}

	header := http.Header{}
	c.setAuthHeaders(header, "", "")

	if got := header.Get("Authorization"); got != "Bearer core-token-001" {
		t.Fatalf("expected authorization header with bearer token, got %q", got)
	}
}

func TestSetAuthHeadersSkipsAuthorizationWhenTokenEmpty(t *testing.T) {
	t.Parallel()
	c := &httpClient{
		cfg: config.CoreConfig{
			UserID:   "scan-user",
			UserName: "scan-user",
		},
	}

	header := http.Header{}
	c.setAuthHeaders(header, "", "")

	if got := header.Get("Authorization"); got != "" {
		t.Fatalf("expected empty authorization header when token missing, got %q", got)
	}
}
