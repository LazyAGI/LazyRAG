package worker

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/lazyrag/scan_control_plane/internal/store"
	"go.uber.org/zap"
)

func TestRetryBackoff(t *testing.T) {
	t.Parallel()
	base := 2 * time.Second
	max := 30 * time.Second
	cases := []struct {
		retry int
		want  time.Duration
	}{
		{retry: 1, want: 2 * time.Second},
		{retry: 2, want: 4 * time.Second},
		{retry: 3, want: 8 * time.Second},
		{retry: 4, want: 16 * time.Second},
		{retry: 5, want: 30 * time.Second},
		{retry: 10, want: 30 * time.Second},
	}
	for _, tc := range cases {
		if got := retryBackoff(base, max, tc.retry); got != tc.want {
			t.Fatalf("retry=%d: expected %v, got %v", tc.retry, tc.want, got)
		}
	}
}

func TestIsCloudSyncOrigin(t *testing.T) {
	t.Parallel()
	cases := []struct {
		origin string
		want   bool
	}{
		{origin: "CLOUD_SYNC", want: true},
		{origin: "cloud_sync", want: true},
		{origin: "LOCAL_FS", want: false},
		{origin: "", want: false},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.origin, func(t *testing.T) {
			t.Parallel()
			if got := isCloudSyncOrigin(tc.origin); got != tc.want {
				t.Fatalf("origin=%q, want %v, got %v", tc.origin, tc.want, got)
			}
		})
	}
}

func TestStageFromCloudMirror(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	sourceRoot := filepath.Join(dir, "src_1")
	path := filepath.Join(sourceRoot, "mirror", "docs", "doc.md")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir mirror dir failed: %v", err)
	}
	content := "hello cloud sync"
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write temp mirror file failed: %v", err)
	}

	w := &Worker{log: zap.NewNop()}
	resp, err := w.stageFromCloudMirror(store.PendingTask{
		TaskID:         1,
		SourceID:       "src-1",
		SourceRootPath: sourceRoot,
		SourceObjectID: path,
	})
	if err != nil {
		t.Fatalf("stageFromCloudMirror failed: %v", err)
	}
	parseRoot := filepath.Join(sourceRoot, "parse")
	if !strings.HasPrefix(resp.HostPath, parseRoot+string(filepath.Separator)) {
		t.Fatalf("expected parse path under %q, got %q", parseRoot, resp.HostPath)
	}
	if !strings.HasPrefix(resp.URI, "file://") {
		t.Fatalf("expected file URI, got %q", resp.URI)
	}
	if resp.Size != int64(len(content)) {
		t.Fatalf("expected size %d, got %d", len(content), resp.Size)
	}
	raw, err := os.ReadFile(resp.HostPath)
	if err != nil {
		t.Fatalf("read staged parse file failed: %v", err)
	}
	if string(raw) != content {
		t.Fatalf("expected staged content %q, got %q", content, string(raw))
	}
}

func TestStageFromCloudMirrorMissingFile(t *testing.T) {
	t.Parallel()
	w := &Worker{log: zap.NewNop()}
	_, err := w.stageFromCloudMirror(store.PendingTask{
		TaskID:         1,
		SourceID:       "src-1",
		SourceObjectID: "/tmp/does-not-exist-doc.md",
	})
	if err == nil {
		t.Fatalf("expected error for missing mirror file")
	}
}
