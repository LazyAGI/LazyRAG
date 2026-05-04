package fs

import (
	"path/filepath"
	"testing"

	"github.com/lazyrag/file_watcher/internal/config"
)

func TestPathMapperIdentity(t *testing.T) {
	t.Parallel()

	mapper := NewPathMapper("auto", nil)
	path := filepath.Join(t.TempDir(), "docs", "a.txt")

	if got := mapper.ToRuntime(path); got != filepath.Clean(path) {
		t.Fatalf("ToRuntime() = %q, want %q", got, filepath.Clean(path))
	}
	if got := mapper.ToPublic(path); got != filepath.Clean(path) {
		t.Fatalf("ToPublic() = %q, want %q", got, filepath.Clean(path))
	}
}

func TestPathMapperPosixMappingAndBoundary(t *testing.T) {
	t.Parallel()

	mapper := NewPathMapper("posix", []config.PathMapping{
		{PublicRoot: "/Users/alice/docs", RuntimeRoot: "/watch/docs"},
	})

	if got := mapper.ToRuntime("/Users/alice/docs/nested/a.md"); got != filepath.Join("/watch/docs", "nested", "a.md") {
		t.Fatalf("ToRuntime() = %q", got)
	}
	if got := mapper.ToPublic(filepath.Join("/watch/docs", "nested", "a.md")); got != "/Users/alice/docs/nested/a.md" {
		t.Fatalf("ToPublic() = %q", got)
	}
	if got := mapper.ToRuntime("/Users/alice/docs2/a.md"); got == filepath.Join("/watch/docs", "2", "a.md") {
		t.Fatalf("expected path boundary to prevent false prefix match, got %q", got)
	}
}

func TestPathMapperLongestPrefixWins(t *testing.T) {
	t.Parallel()

	mapper := NewPathMapper("posix", []config.PathMapping{
		{PublicRoot: "/data", RuntimeRoot: "/watch/root"},
		{PublicRoot: "/data/team", RuntimeRoot: "/watch/team"},
	})

	if got := mapper.ToRuntime("/data/team/a.txt"); got != filepath.Join("/watch/team", "a.txt") {
		t.Fatalf("ToRuntime() = %q", got)
	}
}

func TestPathMapperWindowsPublicPath(t *testing.T) {
	t.Parallel()

	mapper := NewPathMapper("windows", []config.PathMapping{
		{PublicRoot: `c:\Users\alice\Documents`, RuntimeRoot: "/watch/documents"},
	})

	if got := mapper.ToRuntime(`C:\Users\alice\Documents\report.docx`); got != filepath.Join("/watch/documents", "report.docx") {
		t.Fatalf("ToRuntime(backslash) = %q", got)
	}
	if got := mapper.ToRuntime("c:/Users/alice/Documents/report.docx"); got != filepath.Join("/watch/documents", "report.docx") {
		t.Fatalf("ToRuntime(slash) = %q", got)
	}
	if got := mapper.ToRuntime("c:/users/alice/documents/report.docx"); got != filepath.Join("/watch/documents", "report.docx") {
		t.Fatalf("ToRuntime(case-insensitive) = %q", got)
	}
	if got := mapper.ToPublic(filepath.Join("/watch/documents", "nested", "report.docx")); got != "C:/Users/alice/Documents/nested/report.docx" {
		t.Fatalf("ToPublic() = %q", got)
	}
}
