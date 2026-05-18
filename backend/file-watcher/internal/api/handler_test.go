package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	internal "github.com/lazymind/file_watcher/internal"
	"github.com/lazymind/file_watcher/internal/fs"
)

func TestTreeFiltersByKeyword(t *testing.T) {
	t.Parallel()

	root := filepath.Join(t.TempDir(), "release-root")
	mustMkdir(t, root)
	mustMkdir(t, filepath.Join(root, "docs"))
	mustMkdir(t, filepath.Join(root, "assets"))
	mustWriteFile(t, filepath.Join(root, "docs", "ReleaseNotes.md"), "notes")
	mustWriteFile(t, filepath.Join(root, "docs", "guide.txt"), "guide")
	mustWriteFile(t, filepath.Join(root, "assets", "logo.png"), "logo")

	handler := NewHandler(nil, fs.NewPathValidator([]string{root}), nil, nil, fs.NewPathMapper("", nil), nil)
	req := httptest.NewRequest(http.MethodPost, "/api/v1/fs/tree", strings.NewReader(`{"path":`+quoteJSON(root)+`,"keyword":"release","max_depth":3,"include_files":true}`))
	w := httptest.NewRecorder()

	handler.Tree(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200 status, got %d: %s", w.Code, w.Body.String())
	}
	var resp internal.TreeResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response failed: %v", err)
	}
	if len(resp.Items) != 1 {
		t.Fatalf("expected one root node, got %d", len(resp.Items))
	}
	rootNode := resp.Items[0]
	if len(rootNode.Children) != 1 || rootNode.Children[0].Title != "docs" {
		t.Fatalf("expected only docs directory under root, got %#v", rootNode.Children)
	}
	docs := rootNode.Children[0]
	if len(docs.Children) != 1 || docs.Children[0].Title != "ReleaseNotes.md" {
		t.Fatalf("expected only matching release file, got %#v", docs.Children)
	}
}

func mustMkdir(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(path, 0o755); err != nil {
		t.Fatalf("mkdir %s failed: %v", path, err)
	}
}

func mustWriteFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write %s failed: %v", path, err)
	}
}

func quoteJSON(s string) string {
	raw, err := json.Marshal(s)
	if err != nil {
		panic(err)
	}
	return string(raw)
}
