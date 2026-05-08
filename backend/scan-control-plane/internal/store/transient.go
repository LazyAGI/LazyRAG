package store

import (
	"path/filepath"
	"strings"
)

var transientSourceFileExtensions = map[string]struct{}{
	".swp": {},
	".swo": {},
	".swn": {},
	".swm": {},
	".swx": {},
}

func isTransientSourceFilePath(path string, isDir bool) bool {
	if isDir {
		return false
	}
	name := filepath.Base(path)
	if name == "." || name == "" {
		return false
	}
	lowerName := strings.ToLower(name)
	if _, ok := transientSourceFileExtensions[filepath.Ext(lowerName)]; ok {
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

func filterTransientSnapshotItems(items map[string]sourceFileSnapshotItemEntity) map[string]sourceFileSnapshotItemEntity {
	if len(items) == 0 {
		return items
	}
	filtered := make(map[string]sourceFileSnapshotItemEntity, len(items))
	for path, item := range items {
		if isTransientSourceFilePath(path, item.IsDir) {
			continue
		}
		filtered[path] = item
	}
	return filtered
}
