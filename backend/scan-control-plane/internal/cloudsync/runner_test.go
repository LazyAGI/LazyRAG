package cloudsync

import (
	"path/filepath"
	"testing"

	"github.com/lazyrag/scan_control_plane/internal/cloudsync/provider"
	"github.com/lazyrag/scan_control_plane/internal/store"
)

func TestNormalizeManualScopePaths(t *testing.T) {
	t.Parallel()
	mirrorRoot := "/data/ragscan/source/src_ut_001/mirror"
	sourceID := "src_ut_001"
	got := normalizeManualScopePaths([]string{
		"cloud://source/src_ut_001/docs/a.md",
		filepath.Join(mirrorRoot, "docs", "b.md"),
		"/tmp/outside.txt",
		"cloud://source/src_other/docs/c.md",
		"",
	}, sourceID, mirrorRoot)

	if len(got) != 2 {
		t.Fatalf("expected 2 normalized paths, got %d (%v)", len(got), got)
	}
	if got[0] != filepath.Join(mirrorRoot, "docs", "a.md") {
		t.Fatalf("unexpected first normalized path: %s", got[0])
	}
	if got[1] != filepath.Join(mirrorRoot, "docs", "b.md") {
		t.Fatalf("unexpected second normalized path: %s", got[1])
	}
}

func TestPathInRequestedScope(t *testing.T) {
	t.Parallel()
	scope := []string{
		"/data/ragscan/source/src_ut_001/mirror/docs",
		"/data/ragscan/source/src_ut_001/mirror/readme.md",
	}
	if !pathInRequestedScope("/data/ragscan/source/src_ut_001/mirror/docs/a.md", scope) {
		t.Fatalf("expected nested path to match docs scope")
	}
	if !pathInRequestedScope("/data/ragscan/source/src_ut_001/mirror/readme.md", scope) {
		t.Fatalf("expected exact file path to match")
	}
	if pathInRequestedScope("/data/ragscan/source/src_ut_001/mirror/other.md", scope) {
		t.Fatalf("did not expect unrelated path to match")
	}
}

func TestCloudObjectInRequestedScopeMatchesWikiDisplayPath(t *testing.T) {
	t.Parallel()
	item := store.CloudObjectIndexRecord{
		ExternalObjectID: "wiki_parent",
		ExternalKind:     "docx",
		LocalAbsPath:     "/data/ragscan/source/src_ut_001/mirror/test2/test2.md",
		ProviderMeta:     map[string]any{"has_child": true},
	}
	if !cloudObjectInRequestedScope(item, []string{"/data/ragscan/source/src_ut_001/mirror/test2"}) {
		t.Fatalf("expected wiki display path to match mirrored parent page file")
	}
	if cloudObjectInRequestedScope(item, []string{"/data/ragscan/source/src_ut_001/mirror/other"}) {
		t.Fatalf("did not expect unrelated manual scope to match")
	}
}

func TestSanitizeRelativePathForWikiPageWithChildren(t *testing.T) {
	t.Parallel()
	obj := provider.RemoteObject{
		ExternalPath: "test2",
		ExternalName: "test2",
		ProviderMeta: map[string]any{
			"has_child": true,
		},
	}
	got := sanitizeRelativePathForObject(obj, "node_test2", "docx")
	if got != "test2/test2.md" {
		t.Fatalf("expected wiki page content under its own directory, got %q", got)
	}
}
