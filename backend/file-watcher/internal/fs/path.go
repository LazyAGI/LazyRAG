package fs

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	internal "github.com/lazyrag/file_watcher/internal"
)

// PathValidator validates filesystem paths.
type PathValidator interface {
	Validate(path string) internal.ValidatePathResponse
	EnsureAllowed(path string) error
}

type pathValidator struct {
	allowedRoots []string
}

func NewPathValidator(allowedRoots []string) PathValidator {
	cleaned := make([]string, 0, len(allowedRoots))
	for _, r := range allowedRoots {
		canonical, err := canonicalize(r)
		if err != nil {
			canonical = filepath.Clean(r)
		}
		cleaned = append(cleaned, canonical)
	}
	return &pathValidator{allowedRoots: cleaned}
}

func (v *pathValidator) Validate(path string) internal.ValidatePathResponse {
	resp := internal.ValidatePathResponse{Path: path}

	clean, err := canonicalize(path)
	if err != nil {
		resp.Reason = fmt.Sprintf("invalid path: %v", err)
		return resp
	}
	resp.Path = clean

	if !v.isAllowed(clean) {
		resp.Reason = "path is not under any allowed root"
		return resp
	}
	resp.Allowed = true

	info, err := os.Stat(clean)
	if err != nil {
		if os.IsNotExist(err) {
			resp.Reason = "path does not exist"
		} else {
			resp.Reason = fmt.Sprintf("stat error: %v", err)
		}
		return resp
	}

	resp.Exists = true
	resp.IsDir = info.IsDir()

	// Try reading the path to determine readability.
	if info.IsDir() {
		f, err := os.Open(clean)
		if err == nil {
			_ = f.Close()
			resp.Readable = true
		} else {
			resp.Reason = "directory not readable"
		}
	} else {
		f, err := os.Open(clean)
		if err == nil {
			_ = f.Close()
			resp.Readable = true
		} else {
			resp.Reason = "file not readable"
		}
	}

	return resp
}

func (v *pathValidator) EnsureAllowed(path string) error {
	clean, err := canonicalize(path)
	if err != nil {
		return fmt.Errorf("%s: %w", internal.ErrInvalidPath, err)
	}
	if !v.isAllowed(clean) {
		return fmt.Errorf("%s: %s", internal.ErrPathNotAllowed, clean)
	}
	return nil
}

func (v *pathValidator) isAllowed(clean string) bool {
	for _, root := range v.allowedRoots {
		if strings.HasPrefix(clean, root+string(filepath.Separator)) || clean == root {
			return true
		}
	}
	return false
}

// canonicalize applies Clean and Abs, and resolves symlinks where the path exists.
func canonicalize(path string) (string, error) {
	if path == "" {
		return "", fmt.Errorf("empty path")
	}
	abs, err := filepath.Abs(filepath.Clean(path))
	if err != nil {
		return "", err
	}

	if _, err := os.Lstat(abs); err == nil {
		resolved, err := filepath.EvalSymlinks(abs)
		if err != nil {
			return "", err
		}
		return filepath.Clean(resolved), nil
	} else if !os.IsNotExist(err) {
		return "", err
	}

	parent := filepath.Dir(abs)
	if parent == abs {
		return abs, nil
	}

	resolvedParent, err := canonicalize(parent)
	if err != nil {
		return "", err
	}
	return filepath.Join(resolvedParent, filepath.Base(abs)), nil
}
