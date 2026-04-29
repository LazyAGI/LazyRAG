package skill

import (
	"errors"
	"net/http"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"gorm.io/gorm"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/evolution"
	"lazyrag/core/store"
)

const (
	remoteFSRoot     = "skills"
	remoteFSTypeFile = "file"
	remoteFSTypeDir  = "directory"
)

type remoteFSEntry struct {
	Name  string `json:"name"`
	Size  int64  `json:"size"`
	Type  string `json:"type"`
	Mtime string `json:"mtime,omitempty"`
}

type remoteFSPath struct {
	parts        []string
	category     string
	skillName    string
	internalPath string
}

type remoteFSFile struct {
	InternalPath string
	Size         int64
	MimeType     string
	ContentHash  string
	Content      string
	UpdatedAt    time.Time
}

func RemoteFSList(w http.ResponseWriter, r *http.Request) {
	db, userID, ok := prepareRemoteFSRequest(w, r, false)
	if !ok {
		return
	}
	parsed, err := parseRemoteFSPath(r.URL.Query().Get("path"))
	if err != nil {
		common.ReplyErr(w, err.Error(), http.StatusBadRequest)
		return
	}
	entries, err := remoteFSListEntries(r, db, userID, parsed)
	if err != nil {
		replyRemoteFSError(w, err)
		return
	}
	if remoteFSDetail(r) {
		common.ReplyOK(w, map[string]any{"entries": entries})
		return
	}
	names := make([]string, 0, len(entries))
	for _, entry := range entries {
		names = append(names, entry.Name)
	}
	common.ReplyOK(w, map[string]any{"names": names})
}

func RemoteFSInfo(w http.ResponseWriter, r *http.Request) {
	db, userID, ok := prepareRemoteFSRequest(w, r, false)
	if !ok {
		return
	}
	parsed, err := parseRemoteFSPath(r.URL.Query().Get("path"))
	if err != nil {
		common.ReplyErr(w, err.Error(), http.StatusBadRequest)
		return
	}
	entry, err := remoteFSInfoEntry(r, db, userID, parsed)
	if err != nil {
		replyRemoteFSError(w, err)
		return
	}
	common.ReplyOK(w, entry)
}

func RemoteFSExists(w http.ResponseWriter, r *http.Request) {
	db, userID, ok := prepareRemoteFSRequest(w, r, true)
	if !ok {
		common.ReplyOK(w, map[string]any{"exists": false})
		return
	}
	parsed, err := parseRemoteFSPath(r.URL.Query().Get("path"))
	if err != nil {
		common.ReplyOK(w, map[string]any{"exists": false})
		return
	}
	_, err = remoteFSInfoEntry(r, db, userID, parsed)
	common.ReplyOK(w, map[string]any{"exists": err == nil})
}

func RemoteFSContent(w http.ResponseWriter, r *http.Request) {
	db, userID, ok := prepareRemoteFSRequest(w, r, false)
	if !ok {
		return
	}
	parsed, err := parseRemoteFSPath(r.URL.Query().Get("path"))
	if err != nil {
		common.ReplyErr(w, err.Error(), http.StatusBadRequest)
		return
	}
	if parsed.internalPath == "" {
		common.ReplyErr(w, "path points to directory", http.StatusBadRequest)
		return
	}
	files, err := loadRemoteFSSkillFiles(r, db, userID, parsed.category, parsed.skillName)
	if err != nil {
		replyRemoteFSError(w, err)
		return
	}
	file, ok := files[parsed.internalPath]
	if !ok {
		if hasRemoteFSDir(files, parsed.internalPath) {
			common.ReplyErr(w, "path points to directory", http.StatusBadRequest)
			return
		}
		common.ReplyErr(w, "file not found", http.StatusNotFound)
		return
	}
	contentType := strings.TrimSpace(file.MimeType)
	if contentType == "" {
		contentType = mimeTypeForExt(filepath.Ext(file.InternalPath))
	}
	w.Header().Set("Content-Type", contentType)
	if hash := strings.TrimSpace(file.ContentHash); hash != "" {
		w.Header().Set("ETag", `"`+hash+`"`)
	}
	_, _ = w.Write([]byte(file.Content))
}

func prepareRemoteFSRequest(w http.ResponseWriter, r *http.Request, silent bool) (*gorm.DB, string, bool) {
	db := store.DB()
	if db == nil {
		if !silent {
			common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		}
		return nil, "", false
	}
	sessionID := strings.TrimSpace(r.URL.Query().Get("session_id"))
	if sessionID == "" {
		if !silent {
			common.ReplyErr(w, "session_id required", http.StatusBadRequest)
		}
		return nil, "", false
	}
	userID, _, err := evolution.ResolveSessionUser(r.Context(), db, sessionID)
	if err != nil || strings.TrimSpace(userID) == "" {
		if !silent {
			common.ReplyErr(w, "unable to resolve session user", http.StatusBadRequest)
		}
		return nil, "", false
	}
	return db, strings.TrimSpace(userID), true
}

func parseRemoteFSPath(raw string) (remoteFSPath, error) {
	path := strings.TrimSpace(raw)
	if path == "" {
		return remoteFSPath{}, errors.New("path required")
	}
	if idx := strings.Index(path, "://"); idx >= 0 {
		path = path[idx+3:]
	}
	path = strings.Trim(path, "/")
	if path == "" || strings.Contains(path, "\\") {
		return remoteFSPath{}, errors.New("invalid path")
	}
	parts := strings.Split(path, "/")
	for _, part := range parts {
		if part == "" || part == "." || part == ".." {
			return remoteFSPath{}, errors.New("invalid path")
		}
	}
	if parts[0] != remoteFSRoot {
		return remoteFSPath{}, errors.New("path namespace must be skills")
	}
	parsed := remoteFSPath{parts: parts}
	if len(parts) > 1 {
		parsed.category = parts[1]
	}
	if len(parts) > 2 {
		parsed.skillName = parts[2]
	}
	if len(parts) > 3 {
		parsed.internalPath = strings.Join(parts[3:], "/")
	}
	return parsed, nil
}

func remoteFSDetail(r *http.Request) bool {
	raw := strings.TrimSpace(r.URL.Query().Get("detail"))
	return raw == "" || !(strings.EqualFold(raw, "false") || raw == "0")
}

func remoteFSListEntries(r *http.Request, db *gorm.DB, userID string, parsed remoteFSPath) ([]remoteFSEntry, error) {
	switch len(parsed.parts) {
	case 1:
		return listRemoteFSCategories(r, db, userID)
	case 2:
		return listRemoteFSSkills(r, db, userID, parsed.category)
	default:
		files, err := loadRemoteFSSkillFiles(r, db, userID, parsed.category, parsed.skillName)
		if err != nil {
			return nil, err
		}
		if parsed.internalPath != "" {
			if file, ok := files[parsed.internalPath]; ok {
				return []remoteFSEntry{remoteFSFileEntry(parsed.category, parsed.skillName, file)}, nil
			}
		}
		entries := listRemoteFSDir(files, parsed.category, parsed.skillName, parsed.internalPath)
		if len(entries) == 0 && parsed.internalPath != "" {
			return nil, gorm.ErrRecordNotFound
		}
		return entries, nil
	}
}

func remoteFSInfoEntry(r *http.Request, db *gorm.DB, userID string, parsed remoteFSPath) (remoteFSEntry, error) {
	switch len(parsed.parts) {
	case 1:
		return remoteFSEntry{Name: remoteFSRoot, Type: remoteFSTypeDir, Size: 0}, nil
	case 2:
		rows, err := listRemoteFSCategories(r, db, userID)
		if err != nil {
			return remoteFSEntry{}, err
		}
		name := remoteFSRoot + "/" + parsed.category
		for _, row := range rows {
			if row.Name == name {
				return row, nil
			}
		}
		return remoteFSEntry{}, gorm.ErrRecordNotFound
	default:
		files, err := loadRemoteFSSkillFiles(r, db, userID, parsed.category, parsed.skillName)
		if err != nil {
			return remoteFSEntry{}, err
		}
		if parsed.internalPath == "" {
			return remoteFSEntry{Name: remoteFSJoin(parsed.category, parsed.skillName, ""), Type: remoteFSTypeDir, Size: 0, Mtime: latestRemoteFSMtime(files)}, nil
		}
		if file, ok := files[parsed.internalPath]; ok {
			return remoteFSFileEntry(parsed.category, parsed.skillName, file), nil
		}
		if hasRemoteFSDir(files, parsed.internalPath) {
			return remoteFSEntry{Name: remoteFSJoin(parsed.category, parsed.skillName, parsed.internalPath), Type: remoteFSTypeDir, Size: 0, Mtime: latestRemoteFSMtimeForPrefix(files, parsed.internalPath)}, nil
		}
		return remoteFSEntry{}, gorm.ErrRecordNotFound
	}
}

func listRemoteFSCategories(r *http.Request, db *gorm.DB, userID string) ([]remoteFSEntry, error) {
	var rows []orm.SkillResource
	if err := db.WithContext(r.Context()).
		Where("owner_user_id = ? AND node_type = ? AND is_enabled = ?", userID, evolution.SkillNodeTypeParent, true).
		Order("category ASC, updated_at DESC").
		Find(&rows).Error; err != nil {
		return nil, err
	}
	seen := map[string]remoteFSEntry{}
	for _, row := range rows {
		category := strings.TrimSpace(row.Category)
		if category == "" {
			continue
		}
		name := remoteFSRoot + "/" + category
		if existing, ok := seen[name]; !ok || row.UpdatedAt.After(parseRemoteFSMtime(existing.Mtime)) {
			seen[name] = remoteFSEntry{Name: name, Type: remoteFSTypeDir, Size: 0, Mtime: formatRemoteFSMtime(row.UpdatedAt)}
		}
	}
	return sortedRemoteFSEntries(seen), nil
}

func listRemoteFSSkills(r *http.Request, db *gorm.DB, userID, category string) ([]remoteFSEntry, error) {
	var rows []orm.SkillResource
	if err := db.WithContext(r.Context()).
		Where("owner_user_id = ? AND category = ? AND node_type = ? AND is_enabled = ?", userID, strings.TrimSpace(category), evolution.SkillNodeTypeParent, true).
		Order("skill_name ASC").
		Find(&rows).Error; err != nil {
		return nil, err
	}
	entries := make([]remoteFSEntry, 0, len(rows))
	for _, row := range rows {
		entries = append(entries, remoteFSEntry{Name: remoteFSJoin(row.Category, row.SkillName, ""), Type: remoteFSTypeDir, Size: 0, Mtime: formatRemoteFSMtime(row.UpdatedAt)})
	}
	return entries, nil
}

func loadRemoteFSSkillFiles(r *http.Request, db *gorm.DB, userID, category, skillName string) (map[string]remoteFSFile, error) {
	var rows []orm.SkillResource
	if err := db.WithContext(r.Context()).
		Where("owner_user_id = ? AND category = ? AND is_enabled = ? AND (skill_name = ? OR parent_skill_name = ?)",
			strings.TrimSpace(userID), strings.TrimSpace(category), true, strings.TrimSpace(skillName), strings.TrimSpace(skillName)).
		Order("node_type ASC, relative_path ASC").
		Find(&rows).Error; err != nil {
		return nil, err
	}
	files := map[string]remoteFSFile{}
	foundParent := false
	for _, row := range rows {
		internal := remoteFSInternalPath(category, skillName, row)
		if internal == "" {
			continue
		}
		if row.NodeType == evolution.SkillNodeTypeParent {
			foundParent = true
		}
		content, err := storedSkillContent(row)
		if err != nil {
			return nil, err
		}
		size := row.ContentSize
		if size == 0 {
			size = skillContentSize(content)
		}
		mt := strings.TrimSpace(row.MimeType)
		if mt == "" {
			mt = mimeTypeForExt(row.FileExt)
		}
		hash := strings.TrimSpace(row.ContentHash)
		if hash == "" {
			hash = evolution.HashContent(content)
		}
		files[internal] = remoteFSFile{
			InternalPath: internal,
			Size:         size,
			MimeType:     mt,
			ContentHash:  hash,
			Content:      content,
			UpdatedAt:    row.UpdatedAt,
		}
	}
	if !foundParent {
		return nil, gorm.ErrRecordNotFound
	}
	return files, nil
}

func remoteFSInternalPath(category, skillName string, row orm.SkillResource) string {
	if row.NodeType == evolution.SkillNodeTypeParent {
		return "SKILL.md"
	}
	rel := filepath.ToSlash(strings.TrimSpace(row.RelativePath))
	prefix := filepath.ToSlash(filepath.Join(strings.TrimSpace(category), strings.TrimSpace(skillName))) + "/"
	if strings.HasPrefix(rel, prefix) {
		rel = strings.TrimPrefix(rel, prefix)
	}
	if rel == "" {
		rel = strings.TrimSpace(row.SkillName)
		if rel != "" {
			rel += "." + normalizeExt(row.FileExt)
		}
	}
	return strings.Trim(rel, "/")
}

func listRemoteFSDir(files map[string]remoteFSFile, category, skillName, dir string) []remoteFSEntry {
	dir = strings.Trim(strings.TrimSpace(filepath.ToSlash(dir)), "/")
	prefix := ""
	if dir != "" {
		prefix = dir + "/"
	}
	entries := map[string]remoteFSEntry{}
	for internal, file := range files {
		if dir != "" && internal == dir {
			entries[remoteFSJoin(category, skillName, internal)] = remoteFSFileEntry(category, skillName, file)
			continue
		}
		if !strings.HasPrefix(internal, prefix) {
			continue
		}
		rest := strings.TrimPrefix(internal, prefix)
		if rest == "" {
			continue
		}
		first := strings.SplitN(rest, "/", 2)[0]
		childInternal := first
		if dir != "" {
			childInternal = dir + "/" + first
		}
		name := remoteFSJoin(category, skillName, childInternal)
		if !strings.Contains(rest, "/") {
			entries[name] = remoteFSFileEntry(category, skillName, file)
			continue
		}
		if existing, ok := entries[name]; ok && existing.Type == remoteFSTypeFile {
			continue
		}
		entries[name] = remoteFSEntry{Name: name, Type: remoteFSTypeDir, Size: 0, Mtime: latestRemoteFSMtimeForPrefix(files, childInternal)}
	}
	return sortedRemoteFSEntries(entries)
}

func hasRemoteFSDir(files map[string]remoteFSFile, dir string) bool {
	dir = strings.Trim(strings.TrimSpace(filepath.ToSlash(dir)), "/")
	if dir == "" {
		return true
	}
	prefix := dir + "/"
	for internal := range files {
		if strings.HasPrefix(internal, prefix) {
			return true
		}
	}
	return false
}

func remoteFSFileEntry(category, skillName string, file remoteFSFile) remoteFSEntry {
	return remoteFSEntry{Name: remoteFSJoin(category, skillName, file.InternalPath), Type: remoteFSTypeFile, Size: file.Size, Mtime: formatRemoteFSMtime(file.UpdatedAt)}
}

func remoteFSJoin(category, skillName, internal string) string {
	parts := []string{remoteFSRoot, strings.TrimSpace(category), strings.TrimSpace(skillName)}
	if strings.TrimSpace(internal) != "" {
		parts = append(parts, strings.Trim(strings.TrimSpace(internal), "/"))
	}
	return filepath.ToSlash(filepath.Join(parts...))
}

func sortedRemoteFSEntries(items map[string]remoteFSEntry) []remoteFSEntry {
	out := make([]remoteFSEntry, 0, len(items))
	for _, item := range items {
		out = append(out, item)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Type != out[j].Type {
			return out[i].Type == remoteFSTypeDir
		}
		return out[i].Name < out[j].Name
	})
	return out
}

func latestRemoteFSMtime(files map[string]remoteFSFile) string {
	var latest time.Time
	for _, file := range files {
		if file.UpdatedAt.After(latest) {
			latest = file.UpdatedAt
		}
	}
	return formatRemoteFSMtime(latest)
}

func latestRemoteFSMtimeForPrefix(files map[string]remoteFSFile, dir string) string {
	dir = strings.Trim(strings.TrimSpace(filepath.ToSlash(dir)), "/")
	prefix := dir
	if prefix != "" {
		prefix += "/"
	}
	var latest time.Time
	for internal, file := range files {
		if internal == dir || strings.HasPrefix(internal, prefix) {
			if file.UpdatedAt.After(latest) {
				latest = file.UpdatedAt
			}
		}
	}
	return formatRemoteFSMtime(latest)
}

func formatRemoteFSMtime(t time.Time) string {
	if t.IsZero() {
		return ""
	}
	return t.UTC().Format(time.RFC3339Nano)
}

func parseRemoteFSMtime(raw string) time.Time {
	t, _ := time.Parse(time.RFC3339Nano, strings.TrimSpace(raw))
	return t
}

func replyRemoteFSError(w http.ResponseWriter, err error) {
	if errors.Is(err, gorm.ErrRecordNotFound) {
		common.ReplyErr(w, "path not found", http.StatusNotFound)
		return
	}
	common.ReplyErr(w, err.Error(), http.StatusInternalServerError)
}
