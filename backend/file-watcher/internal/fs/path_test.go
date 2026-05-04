package fs

import (
	"os"
	"path/filepath"
	"testing"
)

func TestEnsureAllowedRejectsSymlinkEscape(t *testing.T) {
	t.Parallel()

	base := t.TempDir()
	allowedRoot := filepath.Join(base, "allowed")
	outsideRoot := filepath.Join(base, "outside")
	if err := os.MkdirAll(allowedRoot, 0o755); err != nil {
		t.Fatalf("mkdir allowed root: %v", err)
	}
	if err := os.MkdirAll(outsideRoot, 0o755); err != nil {
		t.Fatalf("mkdir outside root: %v", err)
	}

	targetFile := filepath.Join(outsideRoot, "secret.txt")
	if err := os.WriteFile(targetFile, []byte("secret"), 0o644); err != nil {
		t.Fatalf("write target file: %v", err)
	}

	linkPath := filepath.Join(allowedRoot, "escape")
	if err := os.Symlink(outsideRoot, linkPath); err != nil {
		t.Fatalf("create symlink: %v", err)
	}

	validator := NewPathValidator([]string{allowedRoot})
	if err := validator.EnsureAllowed(filepath.Join(linkPath, "secret.txt")); err == nil {
		t.Fatal("expected symlink escape to be rejected")
	}
}

func TestEnsureAllowedAcceptsDirectChild(t *testing.T) {
	t.Parallel()

	allowedRoot := t.TempDir()
	child := filepath.Join(allowedRoot, "docs", "a.txt")
	if err := os.MkdirAll(filepath.Dir(child), 0o755); err != nil {
		t.Fatalf("mkdir child dir: %v", err)
	}
	if err := os.WriteFile(child, []byte("ok"), 0o644); err != nil {
		t.Fatalf("write child file: %v", err)
	}

	validator := NewPathValidator([]string{allowedRoot})
	if err := validator.EnsureAllowed(child); err != nil {
		t.Fatalf("expected allowed child path, got error: %v", err)
	}
}
