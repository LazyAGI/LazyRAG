package sourcelayout

import (
	"path/filepath"
	"strings"
)

const (
	CloudSourceBaseRoot = "/data/ragscan/source"
	CloudMirrorDirName  = "mirror"
	CloudParseDirName   = "parse"
)

const cloudPublicRootPrefix = "cloud://source/"

func IsCloudOriginType(originType string) bool {
	return strings.EqualFold(strings.TrimSpace(originType), "CLOUD_SYNC")
}

func CloudSourceRootForID(sourceID string) string {
	id := strings.TrimSpace(sourceID)
	if id == "" {
		return filepath.Clean(CloudSourceBaseRoot)
	}
	return filepath.Join(filepath.Clean(CloudSourceBaseRoot), id)
}

func CloudMirrorRoot(sourceRoot string) string {
	return filepath.Join(cleanRoot(sourceRoot), CloudMirrorDirName)
}

func CloudParseRoot(sourceRoot string) string {
	return filepath.Join(cleanRoot(sourceRoot), CloudParseDirName)
}

func CloudPublicRoot(sourceID string) string {
	id := strings.TrimSpace(sourceID)
	if id == "" {
		return cloudPublicRootPrefix
	}
	return cloudPublicRootPrefix + id
}

func ResolveCloudPublicPath(rawPath, sourceID, physicalMirrorRoot string) string {
	trimmed := strings.TrimSpace(rawPath)
	if trimmed == "" {
		return filepath.Clean(physicalMirrorRoot)
	}
	publicRoot := CloudPublicRoot(sourceID)
	publicRootAlt := strings.Replace(publicRoot, "://", ":/", 1)
	if trimmed == publicRoot || trimmed == publicRootAlt {
		return filepath.Clean(physicalMirrorRoot)
	}
	if strings.HasPrefix(trimmed, publicRoot+"/") || strings.HasPrefix(trimmed, publicRootAlt+"/") {
		suffix := strings.TrimPrefix(trimmed, publicRoot)
		suffix = strings.TrimPrefix(suffix, publicRootAlt)
		suffix = strings.TrimPrefix(strings.ReplaceAll(suffix, "\\", "/"), "/")
		candidate := filepath.Clean(filepath.Join(filepath.Clean(physicalMirrorRoot), filepath.FromSlash(suffix)))
		if pathUnderRoot(candidate, physicalMirrorRoot) {
			return candidate
		}
		return filepath.Clean(physicalMirrorRoot)
	}
	return filepath.Clean(trimmed)
}

func cleanRoot(root string) string {
	root = filepath.Clean(strings.TrimSpace(root))
	if root == "" || root == "." {
		return filepath.Clean(CloudSourceBaseRoot)
	}
	return root
}

func pathUnderRoot(path, root string) bool {
	path = filepath.Clean(strings.TrimSpace(path))
	root = filepath.Clean(strings.TrimSpace(root))
	if path == "" || path == "." || root == "" || root == "." {
		return false
	}
	if root == string(filepath.Separator) {
		return strings.HasPrefix(path, string(filepath.Separator))
	}
	return path == root || strings.HasPrefix(path, root+string(filepath.Separator))
}
