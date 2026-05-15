package fs

import (
	"path/filepath"
	"strings"
)

var transientFileExtensions = map[string]struct{}{
	".swp": {},
	".swo": {},
	".swn": {},
	".swm": {},
	".swx": {},
}

func IsTransientFile(path string, isDir bool) bool {
	return isTransientFile(path, isDir)
}

func isTransientFile(path string, isDir bool) bool {
	if isDir {
		return false
	}
	name := filepath.Base(path)
	if name == "." || name == "" {
		return false
	}
	lowerName := strings.ToLower(name)
	if _, ok := transientFileExtensions[filepath.Ext(lowerName)]; ok {
		return true
	}
	if strings.HasPrefix(lowerName, "~$") {
		return true
	}
	if strings.HasPrefix(lowerName, ".#") {
		return true
	}
	if strings.HasPrefix(lowerName, "#") && strings.HasSuffix(lowerName, "#") {
		return true
	}
	return false
}
