package coreclient

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
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

func TestCreateKnowledgeBaseMarksScanManaged(t *testing.T) {
	t.Parallel()

	var createPayload map[string]any
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/datasets":
			if err := json.NewDecoder(r.Body).Decode(&createPayload); err != nil {
				t.Fatalf("decode create payload: %v", err)
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"dataset_id": "ds-1", "display_name": "kb"})
		case r.Method == http.MethodPost && r.URL.Path == "/datasets/ds-1:batchAddMember":
			_ = json.NewEncoder(w).Encode(map[string]any{"ok": true})
		default:
			http.NotFound(w, r)
		}
	}))
	defer ts.Close()

	c := &httpClient{
		cfg: config.CoreConfig{
			Endpoint: ts.URL,
			UserID:   "scan-user",
			UserName: "scan-user",
		},
		client: ts.Client(),
	}

	if _, err := c.CreateKnowledgeBase(context.Background(), CreateKnowledgeBaseRequest{
		Name:          "kb",
		AlgoID:        "algo-1",
		CurrentUserID: "user-1",
	}); err != nil {
		t.Fatalf("create knowledge base failed: %v", err)
	}
	if got, ok := createPayload["scan_managed"].(bool); !ok || !got {
		t.Fatalf("expected scan_managed=true in payload, got %#v", createPayload["scan_managed"])
	}
}

func TestFindKnowledgeBaseByNameUsesExactNameAndScanMarker(t *testing.T) {
	t.Parallel()

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/datasets" {
			http.NotFound(w, r)
			return
		}
		if got := r.Header.Get("X-User-Id"); got != "user-1" {
			t.Fatalf("expected current user header user-1, got %q", got)
		}
		if got := r.URL.Query().Get("keyword"); got != "kb" {
			t.Fatalf("expected keyword kb, got %q", got)
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"datasets": []map[string]any{
				{"dataset_id": "ds-other", "display_name": "kb suffix", "scan_managed": true},
				{"dataset_id": "ds-kb", "display_name": "kb", "tags": []string{"scan"}},
			},
		})
	}))
	defer ts.Close()

	c := &httpClient{
		cfg:    config.CoreConfig{Endpoint: ts.URL, UserID: "scan-user"},
		client: ts.Client(),
	}

	kb, ok, err := c.FindKnowledgeBaseByName(context.Background(), "kb", "user-1", "")
	if err != nil {
		t.Fatalf("find knowledge base failed: %v", err)
	}
	if !ok {
		t.Fatalf("expected knowledge base to be found")
	}
	if kb.DatasetID != "ds-kb" || !kb.ScanManaged {
		t.Fatalf("unexpected knowledge base ref: %#v", kb)
	}
}

func TestDoJSONAsReturnsHTTPError(t *testing.T) {
	t.Parallel()

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "dataset name already exists", http.StatusConflict)
	}))
	defer ts.Close()

	c := &httpClient{
		cfg:    config.CoreConfig{Endpoint: ts.URL},
		client: ts.Client(),
	}

	var out any
	err := c.doJSON(context.Background(), http.MethodGet, ts.URL, nil, &out)
	if err == nil {
		t.Fatalf("expected error")
	}
	if !IsConflictError(err) || !strings.Contains(err.Error(), "status=409") {
		t.Fatalf("expected conflict HTTP error, got %v", err)
	}
}
