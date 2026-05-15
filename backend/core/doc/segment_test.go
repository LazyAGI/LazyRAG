package doc

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSignSegmentImageKeys(t *testing.T) {
	root := t.TempDir()
	t.Setenv("LAZYRAG_UPLOAD_ROOT", root)

	fullPath := filepath.Join(root, "tenants", "root", "normalized_images", "root", "frame.jpg")
	if err := os.MkdirAll(filepath.Dir(fullPath), 0o755); err != nil {
		t.Fatalf("create dir: %v", err)
	}
	if err := os.WriteFile(fullPath, []byte("img"), 0o644); err != nil {
		t.Fatalf("write file: %v", err)
	}

	signed := signSegmentImageKeys([]string{fullPath, "/static-files/tenants/root/a.png?expires=1&sig=x"})
	if !strings.HasPrefix(signed[0], "/static-files/") || !strings.Contains(signed[0], "sig=") {
		t.Fatalf("expected signed static file url, got %q", signed[0])
	}
	if signed[1] != "/static-files/tenants/root/a.png?expires=1&sig=x" {
		t.Fatalf("expected existing static path unchanged, got %q", signed[1])
	}
}
