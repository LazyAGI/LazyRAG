package fs

import (
	"path"
	"path/filepath"
	"sort"
	"strings"

	"github.com/lazyrag/file_watcher/internal/config"
)

// PathMapper converts between the user/control-plane path space and the
// file-watcher runtime path space. Without mappings it behaves as identity.
type PathMapper interface {
	ToRuntime(publicPath string) string
	ToPublic(runtimePath string) string
	CleanPublic(publicPath string) string
}

type pathMapper struct {
	style    string
	mappings []pathMapping
}

type pathMapping struct {
	publicRoot  string
	runtimeRoot string
}

func NewPathMapper(hostPathStyle string, mappings []config.PathMapping) PathMapper {
	style := strings.ToLower(strings.TrimSpace(hostPathStyle))
	if style == "" {
		style = "auto"
	}
	pm := &pathMapper{
		style:    style,
		mappings: make([]pathMapping, 0, len(mappings)),
	}
	for _, item := range mappings {
		publicRoot := pm.cleanPublic(strings.TrimSpace(item.PublicRoot))
		runtimeRoot := cleanRuntime(strings.TrimSpace(item.RuntimeRoot))
		if publicRoot == "" || runtimeRoot == "" {
			continue
		}
		pm.mappings = append(pm.mappings, pathMapping{
			publicRoot:  publicRoot,
			runtimeRoot: runtimeRoot,
		})
	}
	sort.SliceStable(pm.mappings, func(i, j int) bool {
		return len(pm.mappings[i].publicRoot) > len(pm.mappings[j].publicRoot)
	})
	return pm
}

func (m *pathMapper) ToRuntime(publicPath string) string {
	cleanPublic := m.cleanPublic(publicPath)
	if cleanPublic == "" {
		return ""
	}
	for _, item := range m.mappings {
		if !hasPublicPrefix(cleanPublic, item.publicRoot) {
			continue
		}
		suffix := publicSuffix(cleanPublic, item.publicRoot)
		return joinRuntime(item.runtimeRoot, suffix)
	}
	return cleanRuntime(publicPath)
}

func (m *pathMapper) ToPublic(runtimePath string) string {
	clean := cleanRuntime(runtimePath)
	if clean == "" {
		return ""
	}
	for _, item := range m.mappings {
		if !hasRuntimePrefix(clean, item.runtimeRoot) {
			continue
		}
		suffix := runtimeSuffix(clean, item.runtimeRoot)
		return joinPublic(item.publicRoot, suffix)
	}
	return m.cleanPublic(clean)
}

func (m *pathMapper) CleanPublic(publicPath string) string {
	return m.cleanPublic(publicPath)
}

func (m *pathMapper) cleanPublic(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	if m.publicStyleFor(raw) == "windows" {
		return cleanWindowsPublic(raw)
	}
	return cleanPosixPublic(raw)
}

func (m *pathMapper) publicStyleFor(raw string) string {
	switch m.style {
	case "windows", "posix":
		return m.style
	default:
		if looksLikeWindowsPath(raw) {
			return "windows"
		}
		for _, item := range m.mappings {
			if looksLikeWindowsPath(item.publicRoot) {
				return "windows"
			}
		}
		return "posix"
	}
}

func cleanPosixPublic(raw string) string {
	clean := path.Clean(strings.TrimSpace(raw))
	if clean == "." {
		return ""
	}
	return clean
}

func cleanWindowsPublic(raw string) string {
	clean := strings.ReplaceAll(strings.TrimSpace(raw), "\\", "/")
	if clean == "" {
		return ""
	}
	if len(clean) >= 2 && clean[1] == ':' {
		drive := strings.ToUpper(clean[:1]) + ":"
		rest := strings.TrimLeft(clean[2:], "/")
		if rest == "" {
			return drive + "/"
		}
		rest = path.Clean("/" + rest)
		if rest == "/" {
			return drive + "/"
		}
		return drive + rest
	}
	if strings.HasPrefix(clean, "//") {
		trimmed := strings.TrimLeft(clean, "/")
		cleaned := path.Clean("/" + trimmed)
		return "//" + strings.TrimLeft(cleaned, "/")
	}
	clean = path.Clean(clean)
	if clean == "." {
		return ""
	}
	return clean
}

func cleanRuntime(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	return filepath.Clean(raw)
}

func looksLikeWindowsPath(raw string) bool {
	raw = strings.TrimSpace(raw)
	return len(raw) >= 2 && raw[1] == ':' && ((raw[0] >= 'a' && raw[0] <= 'z') || (raw[0] >= 'A' && raw[0] <= 'Z'))
}

func hasPublicPrefix(candidate, root string) bool {
	if looksLikeWindowsPath(candidate) || looksLikeWindowsPath(root) {
		return hasPublicPrefixFold(candidate, root)
	}
	if candidate == root {
		return true
	}
	if root == "/" {
		return strings.HasPrefix(candidate, "/")
	}
	if strings.HasSuffix(root, "/") {
		return strings.HasPrefix(candidate, root)
	}
	return strings.HasPrefix(candidate, root+"/")
}

func hasPublicPrefixFold(candidate, root string) bool {
	candidateLower := strings.ToLower(candidate)
	rootLower := strings.ToLower(root)
	if candidateLower == rootLower {
		return true
	}
	if rootLower == "/" {
		return strings.HasPrefix(candidateLower, "/")
	}
	if strings.HasSuffix(rootLower, "/") {
		return strings.HasPrefix(candidateLower, rootLower)
	}
	return strings.HasPrefix(candidateLower, rootLower+"/")
}

func publicSuffix(candidate, root string) string {
	if len(candidate) < len(root) {
		return ""
	}
	suffix := candidate[len(root):]
	return strings.TrimLeft(suffix, "/")
}

func hasRuntimePrefix(candidate, root string) bool {
	if candidate == root {
		return true
	}
	if root == string(filepath.Separator) {
		return strings.HasPrefix(candidate, string(filepath.Separator))
	}
	if strings.HasSuffix(root, string(filepath.Separator)) {
		return strings.HasPrefix(candidate, root)
	}
	return strings.HasPrefix(candidate, root+string(filepath.Separator))
}

func runtimeSuffix(candidate, root string) string {
	suffix := strings.TrimPrefix(candidate, root)
	suffix = strings.TrimLeft(suffix, string(filepath.Separator))
	return filepath.ToSlash(suffix)
}

func joinRuntime(root, slashSuffix string) string {
	if strings.TrimSpace(slashSuffix) == "" {
		return root
	}
	return filepath.Join(root, filepath.FromSlash(slashSuffix))
}

func joinPublic(root, slashSuffix string) string {
	suffix := strings.TrimLeft(strings.ReplaceAll(strings.TrimSpace(slashSuffix), "\\", "/"), "/")
	if suffix == "" {
		return root
	}
	if strings.HasSuffix(root, "/") {
		return root + suffix
	}
	return root + "/" + suffix
}
