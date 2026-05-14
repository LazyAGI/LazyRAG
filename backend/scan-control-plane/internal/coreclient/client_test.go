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
	var createUserID string
	var memberUserID string
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/datasets":
			createUserID = r.Header.Get("X-User-Id")
			if err := json.NewDecoder(r.Body).Decode(&createPayload); err != nil {
				t.Fatalf("decode create payload: %v", err)
			}
			_ = json.NewEncoder(w).Encode(map[string]any{"dataset_id": "ds-1", "display_name": "kb"})
		case r.Method == http.MethodPost && r.URL.Path == "/datasets/ds-1:batchAddMember":
			memberUserID = r.Header.Get("X-User-Id")
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
	wantUserID, _ := scanVirtualUser("scan-user", "scan-user", "user-1", "")
	if createUserID != wantUserID || memberUserID != wantUserID {
		t.Fatalf("expected derived virtual user %q, got create=%q member=%q", wantUserID, createUserID, memberUserID)
	}
}

func TestScanVirtualUserStablePerCurrentUser(t *testing.T) {
	t.Parallel()

	first, firstName := scanVirtualUser("scan-user", "scan-user", "user-1", "Alice")
	second, secondName := scanVirtualUser("scan-user", "scan-user", "user-1", "Alice Renamed")
	other, _ := scanVirtualUser("scan-user", "scan-user", "user-2", "Alice")

	if first == "" || first == "scan-user" {
		t.Fatalf("expected non-empty derived user id, got %q", first)
	}
	if first != second {
		t.Fatalf("expected same current user to derive same virtual user id, got %q and %q", first, second)
	}
	if first == other {
		t.Fatalf("expected different current users to derive different virtual user ids, got %q", first)
	}
	if firstName != secondName {
		t.Fatalf("expected same current user to derive same virtual user name, got %q and %q", firstName, secondName)
	}
	if !strings.HasPrefix(firstName, "scan-user:") {
		t.Fatalf("expected virtual name to retain scan-user prefix, got %q", firstName)
	}
}

func TestFindKnowledgeBaseByNameUsesExactNameAndScanMarker(t *testing.T) {
	t.Parallel()

	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/datasets" {
			http.NotFound(w, r)
			return
		}
		wantUserID, _ := scanVirtualUser("scan-user", "", "user-1", "")
		if got := r.Header.Get("X-User-Id"); got != wantUserID {
			t.Fatalf("expected derived virtual user header %q, got %q", wantUserID, got)
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

func TestDeleteDatasetUsesCurrentUserAndIgnoresNotFound(t *testing.T) {
	t.Parallel()

	var calls int
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.Method != http.MethodDelete || r.URL.Path != "/datasets/ds-1" {
			http.NotFound(w, r)
			return
		}
		wantUserID, _ := scanVirtualUser("scan-user", "", "user-1", "")
		if got := r.Header.Get("X-User-Id"); got != wantUserID {
			t.Fatalf("expected derived virtual user header %q, got %q", wantUserID, got)
		}
		if calls == 1 {
			w.WriteHeader(http.StatusOK)
			return
		}
		http.NotFound(w, r)
	}))
	defer ts.Close()

	c := &httpClient{
		cfg:    config.CoreConfig{Endpoint: ts.URL, UserID: "scan-user"},
		client: ts.Client(),
	}

	if err := c.DeleteDataset(context.Background(), "ds-1", "user-1", ""); err != nil {
		t.Fatalf("delete dataset failed: %v", err)
	}
	if err := c.DeleteDataset(context.Background(), "ds-1", "user-1", ""); err != nil {
		t.Fatalf("delete dataset should ignore not found, got: %v", err)
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
