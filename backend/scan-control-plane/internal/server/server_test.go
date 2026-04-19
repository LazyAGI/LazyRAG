package server

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"go.uber.org/zap"

	"github.com/lazyrag/scan_control_plane/internal/model"
)

func TestFetchTreeFileStatsRunsInParallel(t *testing.T) {
	t.Parallel()

	var inFlight int64
	var maxInFlight int64
	var ts *httptest.Server
	func() {
		defer func() {
			if r := recover(); r != nil {
				t.Skipf("skip: httptest listener not available in current sandbox: %v", r)
			}
		}()
		ts = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.URL.Path != "/api/v1/fs/stat" {
				http.NotFound(w, r)
				return
			}
			var req struct {
				Path string `json:"path"`
			}
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
				http.Error(w, "bad json", http.StatusBadRequest)
				return
			}
			current := atomic.AddInt64(&inFlight, 1)
			for {
				prev := atomic.LoadInt64(&maxInFlight)
				if current <= prev {
					break
				}
				if atomic.CompareAndSwapInt64(&maxInFlight, prev, current) {
					break
				}
			}
			defer atomic.AddInt64(&inFlight, -1)
			time.Sleep(50 * time.Millisecond)

			_ = json.NewEncoder(w).Encode(map[string]any{
				"path":     req.Path,
				"size":     123,
				"mod_time": time.Now().UTC(),
				"is_dir":   false,
				"checksum": "sha1",
			})
		}))
	}()
	if ts == nil {
		return
	}
	defer ts.Close()

	h := &Handler{
		client: &http.Client{Timeout: 2 * time.Second},
		log:    zap.NewNop(),
	}

	items := []model.TreeNode{
		{Key: "/tmp/watch/a.txt", IsDir: false},
		{Key: "/tmp/watch/b.txt", IsDir: false},
		{Key: "/tmp/watch/c.txt", IsDir: false},
		{Key: "/tmp/watch/d.txt", IsDir: false},
		{Key: "/tmp/watch/e.txt", IsDir: false},
		{Key: "/tmp/watch/f.txt", IsDir: false},
	}

	stats, err := h.fetchTreeFileStats(context.Background(), ts.URL, items)
	if err != nil {
		t.Fatalf("fetchTreeFileStats failed: %v", err)
	}
	if len(stats) != len(items) {
		t.Fatalf("expected %d stats, got %d", len(items), len(stats))
	}
	if atomic.LoadInt64(&maxInFlight) <= 1 {
		t.Fatalf("expected concurrent fs/stat calls, max in-flight=%d", atomic.LoadInt64(&maxInFlight))
	}
}

func TestDecodeJSONRejectsUnknownFields(t *testing.T) {
	t.Parallel()

	req := httptest.NewRequest(http.MethodPost, "/decode", strings.NewReader(`{"agent_id":"a1","tenant_id":"t1","unknown":"x"}`))
	w := httptest.NewRecorder()
	var out model.PullCommandsRequest
	if ok := decodeJSON(w, req, &out); ok {
		t.Fatalf("expected decodeJSON to reject unknown fields")
	}
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 status, got %d", w.Code)
	}
}

func TestDecodeJSONRejectsMultipleJSONValues(t *testing.T) {
	t.Parallel()

	req := httptest.NewRequest(http.MethodPost, "/decode", strings.NewReader(`{"agent_id":"a1","tenant_id":"t1"} {"x":1}`))
	w := httptest.NewRecorder()
	var out model.PullCommandsRequest
	if ok := decodeJSON(w, req, &out); ok {
		t.Fatalf("expected decodeJSON to reject multiple JSON payloads")
	}
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 status, got %d", w.Code)
	}
}
