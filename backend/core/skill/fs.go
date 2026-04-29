package skill

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"mime"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"gopkg.in/yaml.v3"

	"lazyrag/core/common/orm"
	"lazyrag/core/evolution"
)

type parentFrontmatter struct {
	Name        string `yaml:"name"`
	Description string `yaml:"description"`
}

func normalizeExt(ext string) string {
	ext = strings.TrimSpace(strings.TrimPrefix(ext, "."))
	if ext == "" {
		return "md"
	}
	return strings.ToLower(ext)
}

func validatePathSegment(segment string) error {
	segment = strings.TrimSpace(segment)
	switch {
	case segment == "":
		return errors.New("path segment required")
	case segment == "." || segment == "..":
		return errors.New("invalid path segment")
	case strings.Contains(segment, "/") || strings.Contains(segment, "\\"):
		return errors.New("path segment cannot contain slash")
	}
	return nil
}

func skillRootDir(userID, category, skillName string) string {
	return filepath.Join(evolution.SkillFSURL(userID), filepath.FromSlash(filepath.Join(strings.TrimSpace(category), strings.TrimSpace(skillName))))
}

func parentRelativePath(category, skillName string) string {
	return evolution.ParentSkillRelativePath(category, skillName)
}

func childRelativePath(category, parentSkillName, childName, ext string) string {
	return filepath.ToSlash(filepath.Join(strings.TrimSpace(category), strings.TrimSpace(parentSkillName), fmt.Sprintf("%s.%s", strings.TrimSpace(childName), normalizeExt(ext))))
}

func absoluteSkillPath(userID, relativePath string) string {
	return filepath.Join(evolution.SkillFSURL(userID), filepath.FromSlash(relativePath))
}

func draftPath(userID, skillID string, version int64, relativePath string) string {
	return filepath.Join(evolution.SkillVolumeRoot(), "skills", ".drafts", strings.TrimSpace(userID), strings.TrimSpace(skillID), fmt.Sprintf("%d", version), filepath.FromSlash(relativePath))
}

func draftRoot(userID, skillID string) string {
	return filepath.Join(evolution.SkillVolumeRoot(), "skills", ".drafts", strings.TrimSpace(userID), strings.TrimSpace(skillID))
}

func storedSkillContent(row orm.SkillResource) (string, error) {
	if row.Content != "" || strings.TrimSpace(row.StoragePath) == "" {
		return row.Content, nil
	}
	return readTextFile(row.StoragePath)
}

func skillContentSize(content string) int64 {
	return int64(len([]byte(content)))
}

func mimeTypeForExt(ext string) string {
	ext = strings.TrimSpace(ext)
	if ext == "" {
		return "text/plain; charset=utf-8"
	}
	if !strings.HasPrefix(ext, ".") {
		ext = "." + ext
	}
	if mt := mime.TypeByExtension(strings.ToLower(ext)); mt != "" {
		if strings.HasPrefix(mt, "text/") && !strings.Contains(strings.ToLower(mt), "charset=") {
			return mt + "; charset=utf-8"
		}
		return mt
	}
	switch strings.ToLower(ext) {
	case ".md", ".markdown":
		return "text/markdown; charset=utf-8"
	case ".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".txt":
		return "text/plain; charset=utf-8"
	default:
		return "application/octet-stream"
	}
}

func readTextFile(path string) (string, error) {
	body, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return string(body), nil
}

func writeFileAtomic(path, content string) error {
	path = strings.TrimSpace(path)
	if path == "" {
		return errors.New("path required")
	}
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(dir, ".tmp-*")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	defer func() { _ = os.Remove(tmpPath) }()
	if _, err := tmp.WriteString(content); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmpPath, path)
}

func copyDir(src, dst string) error {
	entries, err := os.ReadDir(src)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dst, 0o755); err != nil {
		return err
	}
	for _, entry := range entries {
		srcPath := filepath.Join(src, entry.Name())
		dstPath := filepath.Join(dst, entry.Name())
		if entry.IsDir() {
			if err := copyDir(srcPath, dstPath); err != nil {
				return err
			}
			continue
		}
		if err := copyFile(srcPath, dstPath); err != nil {
			return err
		}
	}
	return nil
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return err
	}
	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		_ = out.Close()
		return err
	}
	return out.Close()
}

func exists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

func removePath(path string) {
	_ = os.RemoveAll(path)
}

func removePathChecked(path string) error {
	path = strings.TrimSpace(path)
	if path == "" {
		return nil
	}
	if err := os.RemoveAll(path); err != nil {
		return err
	}
	_, err := os.Stat(path)
	switch {
	case err == nil:
		return fmt.Errorf("path still exists after delete: %s", path)
	case os.IsNotExist(err):
		return nil
	default:
		return err
	}
}

func movePathAside(path string) (string, error) {
	path = strings.TrimSpace(path)
	if path == "" {
		return "", nil
	}
	if _, err := os.Stat(path); err != nil {
		if os.IsNotExist(err) {
			return "", nil
		}
		return "", err
	}
	dir := filepath.Dir(path)
	base := filepath.Base(path)
	for i := 0; i < 16; i++ {
		candidate := filepath.Join(dir, fmt.Sprintf(".trash-%s-%d-%d", base, time.Now().UnixNano(), i))
		if _, err := os.Stat(candidate); err == nil {
			continue
		} else if !os.IsNotExist(err) {
			return "", err
		}
		if err := os.Rename(path, candidate); err != nil {
			return "", err
		}
		return candidate, nil
	}
	return "", errors.New("unable to allocate trash path")
}

func restoreMovedPath(currentPath, originalPath string) error {
	currentPath = strings.TrimSpace(currentPath)
	originalPath = strings.TrimSpace(originalPath)
	if currentPath == "" || originalPath == "" {
		return nil
	}
	return os.Rename(currentPath, originalPath)
}

func parseTags(raw json.RawMessage) []string {
	if len(raw) == 0 {
		return nil
	}
	var tags []string
	if err := json.Unmarshal(raw, &tags); err != nil {
		return nil
	}
	out := make([]string, 0, len(tags))
	for _, tag := range tags {
		if trimmed := strings.TrimSpace(tag); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	if len(out) == 0 {
		return nil
	}
	sort.Strings(out)
	return out
}

func tagsJSON(tags []string) json.RawMessage {
	if len(tags) == 0 {
		return nil
	}
	uniq := make([]string, 0, len(tags))
	seen := map[string]struct{}{}
	for _, tag := range tags {
		trimmed := strings.TrimSpace(tag)
		if trimmed == "" {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		uniq = append(uniq, trimmed)
	}
	if len(uniq) == 0 {
		return nil
	}
	sort.Strings(uniq)
	b, _ := json.Marshal(uniq)
	return b
}

func parseFrontmatter(content string) (*parentFrontmatter, string, error) {
	content = strings.ReplaceAll(content, "\r\n", "\n")
	if !strings.HasPrefix(content, "---\n") {
		return nil, "", errors.New("parent skill content must start with YAML frontmatter")
	}
	rest := strings.TrimPrefix(content, "---\n")
	idx := strings.Index(rest, "\n---\n")
	if idx < 0 {
		return nil, "", errors.New("parent skill content must contain closing frontmatter separator")
	}
	yamlPart := rest[:idx]
	body := rest[idx+5:]
	if strings.TrimSpace(body) == "" {
		return nil, "", errors.New("parent skill content must include markdown body")
	}
	var meta parentFrontmatter
	if err := yaml.Unmarshal([]byte(yamlPart), &meta); err != nil {
		return nil, "", fmt.Errorf("invalid skill frontmatter: %w", err)
	}
	return &meta, body, nil
}

func parentSkillBody(content string) (string, error) {
	_, body, err := parseFrontmatter(content)
	if err != nil {
		return "", err
	}
	body = strings.TrimSpace(body)
	if body == "" {
		return "", errors.New("content required")
	}
	return body, nil
}

func buildParentSkillContent(name, description, body string) (string, string, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return "", "", errors.New("name required")
	}
	description = strings.TrimSpace(description)
	if description == "" {
		return "", "", errors.New("description required")
	}
	body = strings.TrimSpace(body)
	if body == "" {
		return "", "", errors.New("content required")
	}
	meta, err := yaml.Marshal(parentFrontmatter{
		Name:        name,
		Description: description,
	})
	if err != nil {
		return "", "", fmt.Errorf("marshal skill frontmatter failed: %w", err)
	}
	content := fmt.Sprintf("---\n%s---\n%s", string(meta), body)
	resolvedDescription, err := validateParentSkillContent(name, description, content)
	if err != nil {
		return "", "", err
	}
	return content, resolvedDescription, nil
}

func validateParentSkillContent(name, description, content string) (string, error) {
	name = strings.TrimSpace(name)
	description = strings.TrimSpace(description)
	content = strings.TrimSpace(content)
	if content == "" {
		return "", errors.New("content required")
	}
	meta, _, err := parseFrontmatter(content)
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(meta.Name) == "" {
		return "", errors.New("frontmatter name required")
	}
	if strings.TrimSpace(meta.Description) == "" {
		return "", errors.New("frontmatter description required")
	}
	if strings.TrimSpace(meta.Name) != name {
		return "", errors.New("request name and frontmatter name must match")
	}
	resolvedDescription := strings.TrimSpace(meta.Description)
	if description != "" && description != resolvedDescription {
		return "", errors.New("request description and frontmatter description must match")
	}
	return resolvedDescription, nil
}
