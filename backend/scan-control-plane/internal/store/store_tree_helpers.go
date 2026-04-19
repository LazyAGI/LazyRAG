package store

import (
	"context"
	"path/filepath"
	"sort"
	"strings"

	"github.com/lazyrag/scan_control_plane/internal/model"
)

func collectTreeFilePaths(items []model.TreeNode) []string {
	out := make([]string, 0, 64)
	seen := make(map[string]struct{}, 64)
	var walk func(nodes []model.TreeNode)
	walk = func(nodes []model.TreeNode) {
		for _, node := range nodes {
			if node.IsDir {
				if len(node.Children) > 0 {
					walk(node.Children)
				}
				continue
			}
			p := strings.TrimSpace(node.Key)
			if p == "" {
				continue
			}
			if _, ok := seen[p]; ok {
				continue
			}
			seen[p] = struct{}{}
			out = append(out, p)
		}
	}
	walk(items)
	return out
}

func CollectTreeFilePaths(items []model.TreeNode) []string {
	return collectTreeFilePaths(items)
}

func applyWatchTreeNodeStates(items []model.TreeNode, docMap map[string]treeDocumentRow, queueMap map[int64]parseTaskDocJoin) []model.TreeNode {
	out := make([]model.TreeNode, 0, len(items))
	for _, node := range items {
		item := node
		if item.IsDir {
			item.Children = applyWatchTreeNodeStates(item.Children, docMap, queueMap)
			v := false
			item.Selectable = &v
			item.StatusSource = "UNKNOWN"
			out = append(out, item)
			continue
		}
		v := true
		item.Selectable = &v
		path := strings.TrimSpace(item.Key)
		doc, ok := docMap[path]
		if !ok {
			item.UpdateType = "UNKNOWN"
			item.UpdateDesc = updateTypeDescription("UNKNOWN")
			item.StatusSource = "UNKNOWN"
			out = append(out, item)
			continue
		}
		updateType := inferDocumentUpdateType(doc.DesiredVersionID, doc.CurrentVersionID, doc.ParseStatus)
		item.UpdateType = updateType
		item.UpdateDesc = updateTypeDescription(updateType)
		item.StatusSource = "DOCUMENTS"
		switch updateType {
		case "NEW", "MODIFIED", "DELETED":
			has := true
			item.HasUpdate = &has
		case "UNCHANGED":
			has := false
			item.HasUpdate = &has
		default:
			item.HasUpdate = nil
		}
		if queue, ok := queueMap[doc.ID]; ok {
			item.ParseQueueState = queue.Status
		}
		out = append(out, item)
	}
	return out
}

func applySnapshotTreeNodeStates(items []model.TreeNode, diffByPath map[string]string, docMap map[string]treeDocumentRow, queueMap map[int64]parseTaskDocJoin) []model.TreeNode {
	out := make([]model.TreeNode, 0, len(items))
	for _, node := range items {
		item := node
		if item.IsDir {
			item.Children = applySnapshotTreeNodeStates(item.Children, diffByPath, docMap, queueMap)
			v := false
			item.Selectable = &v
			item.StatusSource = "UNKNOWN"
			out = append(out, item)
			continue
		}
		v := true
		item.Selectable = &v
		path := strings.TrimSpace(item.Key)
		updateType := strings.TrimSpace(diffByPath[path])
		if updateType == "" {
			updateType = "UNKNOWN"
		}
		item.UpdateType = updateType
		item.UpdateDesc = updateTypeDescription(updateType)
		item.StatusSource = "SNAPSHOT"
		switch updateType {
		case "NEW", "MODIFIED", "DELETED":
			has := true
			item.HasUpdate = &has
		case "UNCHANGED":
			has := false
			item.HasUpdate = &has
		default:
			item.HasUpdate = nil
		}
		if doc, ok := docMap[path]; ok {
			if queue, ok := queueMap[doc.ID]; ok {
				item.ParseQueueState = queue.Status
			}
		}
		out = append(out, item)
	}
	return out
}

func (s *Store) filterPathsByUpdatedOnly(ctx context.Context, sourceID string, paths []string) ([]string, int, error) {
	if len(paths) == 0 {
		return nil, 0, nil
	}
	var docs []treeDocumentRow
	if err := s.db.WithContext(ctx).
		Table("documents").
		Select("id, source_object_id, desired_version_id, current_version_id, parse_status").
		Where("source_id = ? AND source_object_id IN ?", sourceID, paths).
		Scan(&docs).Error; err != nil {
		return nil, 0, err
	}
	docMap := make(map[string]treeDocumentRow, len(docs))
	for _, doc := range docs {
		docMap[doc.SourceObjectID] = doc
	}
	filtered := make([]string, 0, len(paths))
	ignored := 0
	for _, path := range paths {
		doc, ok := docMap[path]
		if !ok {
			// No document record yet, treat as NEW.
			filtered = append(filtered, path)
			continue
		}
		updateType := inferDocumentUpdateType(doc.DesiredVersionID, doc.CurrentVersionID, doc.ParseStatus)
		if updateType == "NEW" || updateType == "MODIFIED" || updateType == "DELETED" {
			filtered = append(filtered, path)
			continue
		}
		ignored++
	}
	return filtered, ignored, nil
}

func filterPathsByDiff(paths []string, diffByPath map[string]string) ([]string, int) {
	filtered := make([]string, 0, len(paths))
	ignored := 0
	for _, path := range paths {
		updateType := strings.ToUpper(strings.TrimSpace(diffByPath[path]))
		if updateType == "NEW" || updateType == "MODIFIED" || updateType == "DELETED" {
			filtered = append(filtered, path)
			continue
		}
		ignored++
	}
	return filtered, ignored
}

func collectDeletedPathsFromDiff(diffByPath map[string]string, currentPaths []string) []string {
	currentSet := make(map[string]struct{}, len(currentPaths))
	for _, path := range currentPaths {
		currentSet[filepath.Clean(strings.TrimSpace(path))] = struct{}{}
	}
	out := make([]string, 0, len(diffByPath))
	for path, state := range diffByPath {
		if strings.ToUpper(strings.TrimSpace(state)) != "DELETED" {
			continue
		}
		cleanPath := filepath.Clean(strings.TrimSpace(path))
		if _, ok := currentSet[cleanPath]; ok {
			continue
		}
		out = append(out, cleanPath)
	}
	return out
}

func resolveCloudObjectLocalPath(rootPath string, row cloudObjectIndexEntity) string {
	if raw := strings.TrimSpace(row.LocalAbsPath); raw != "" {
		clean := filepath.Clean(raw)
		if clean != "" && clean != "." {
			return clean
		}
	}

	relative := strings.TrimSpace(row.LocalRelPath)
	if relative == "" {
		relative = strings.TrimSpace(row.ExternalPath)
	}
	rootPath = filepath.Clean(strings.TrimSpace(rootPath))
	if rootPath == "" || rootPath == "." {
		return ""
	}
	if relative == "" {
		return rootPath
	}
	relative = filepath.Clean(relative)
	if relative == "." || relative == string(filepath.Separator) {
		return rootPath
	}
	relative = strings.TrimPrefix(relative, string(filepath.Separator))
	if relative == "" || relative == "." {
		return rootPath
	}
	return filepath.Clean(filepath.Join(rootPath, relative))
}

func cloudObjectIsDirectory(kind string) bool {
	switch strings.ToLower(strings.TrimSpace(kind)) {
	case "folder", "directory", "dir", "wiki", "space":
		return true
	default:
		return false
	}
}

func treeRelativeDepth(rootPath, targetPath string) int {
	rootPath = filepath.Clean(strings.TrimSpace(rootPath))
	targetPath = filepath.Clean(strings.TrimSpace(targetPath))
	if rootPath == "" || targetPath == "" || rootPath == "." || targetPath == "." {
		return -1
	}
	rel, err := filepath.Rel(rootPath, targetPath)
	if err != nil {
		return -1
	}
	rel = filepath.Clean(rel)
	if rel == "." {
		return 0
	}
	if rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return -1
	}
	parts := strings.Split(rel, string(filepath.Separator))
	depth := 0
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" || part == "." {
			continue
		}
		depth++
	}
	return depth
}

func ensureCloudAncestorNodes(nodeMap map[string]*model.TreeNode, childMap map[string]map[string]struct{}, rootPath, targetPath string, maxDepth int) {
	rootPath = filepath.Clean(strings.TrimSpace(rootPath))
	targetPath = filepath.Clean(strings.TrimSpace(targetPath))
	if rootPath == "" || targetPath == "" || rootPath == "." || targetPath == "." {
		return
	}
	rel, err := filepath.Rel(rootPath, targetPath)
	if err != nil {
		return
	}
	rel = filepath.Clean(rel)
	if rel == "." {
		return
	}
	parts := strings.Split(rel, string(filepath.Separator))
	if len(parts) <= 1 {
		return
	}
	maxAncestorDepth := len(parts) - 1
	if maxAncestorDepth > maxDepth {
		maxAncestorDepth = maxDepth
	}
	current := rootPath
	for i := 0; i < maxAncestorDepth; i++ {
		part := strings.TrimSpace(parts[i])
		if part == "" || part == "." {
			continue
		}
		current = filepath.Clean(filepath.Join(current, part))
		ensureCloudNode(nodeMap, childMap, current, true, part, "")
	}
}

func ensureCloudNode(nodeMap map[string]*model.TreeNode, childMap map[string]map[string]struct{}, path string, isDir bool, title, externalFileID string) {
	path = filepath.Clean(strings.TrimSpace(path))
	if path == "" || path == "." {
		return
	}
	title = strings.TrimSpace(title)
	if title == "" {
		title = nodeTitleFromPath(path)
	}
	node, ok := nodeMap[path]
	if !ok {
		node = &model.TreeNode{
			Title: title,
			Key:   path,
			IsDir: isDir,
		}
		if !isDir {
			node.ExternalFileID = strings.TrimSpace(externalFileID)
		}
		nodeMap[path] = node
	} else {
		if isDir {
			node.IsDir = true
			node.ExternalFileID = ""
		} else if !node.IsDir && node.ExternalFileID == "" {
			node.ExternalFileID = strings.TrimSpace(externalFileID)
		}
		if strings.TrimSpace(node.Title) == "" || node.Title == nodeTitleFromPath(path) {
			node.Title = title
		}
	}
	parent := filepath.Clean(filepath.Dir(path))
	if parent == "" || parent == "." {
		parent = string(filepath.Separator)
	}
	if _, ok := childMap[parent]; !ok {
		childMap[parent] = make(map[string]struct{}, 4)
	}
	childMap[parent][path] = struct{}{}
}

func buildCloudTreeNodes(rootPath string, nodeMap map[string]*model.TreeNode, childMap map[string]map[string]struct{}) []model.TreeNode {
	rootPath = filepath.Clean(strings.TrimSpace(rootPath))
	if rootPath == "" || rootPath == "." {
		rootPath = string(filepath.Separator)
	}
	var walk func(parent string) []model.TreeNode
	walk = func(parent string) []model.TreeNode {
		childrenSet, ok := childMap[parent]
		if !ok || len(childrenSet) == 0 {
			return nil
		}
		keys := make([]string, 0, len(childrenSet))
		for key := range childrenSet {
			if _, exists := nodeMap[key]; !exists {
				continue
			}
			keys = append(keys, key)
		}
		sort.Slice(keys, func(i, j int) bool {
			left := nodeMap[keys[i]]
			right := nodeMap[keys[j]]
			if left.IsDir != right.IsDir {
				return left.IsDir
			}
			leftTitle := strings.ToLower(strings.TrimSpace(left.Title))
			rightTitle := strings.ToLower(strings.TrimSpace(right.Title))
			if leftTitle == rightTitle {
				return left.Key < right.Key
			}
			return leftTitle < rightTitle
		})
		out := make([]model.TreeNode, 0, len(keys))
		for _, key := range keys {
			base := nodeMap[key]
			if base == nil {
				continue
			}
			item := *base
			if item.IsDir {
				item.Children = walk(item.Key)
			} else {
				item.Children = nil
			}
			out = append(out, item)
		}
		return out
	}
	return walk(rootPath)
}

func addDeletedNodes(items []model.TreeNode, deletedPaths []string, rootPath, statusSource string, docMap map[string]treeDocumentRow, queueMap map[int64]parseTaskDocJoin) []model.TreeNode {
	for _, path := range deletedPaths {
		items = insertDeletedNode(items, path, rootPath, statusSource, docMap, queueMap)
	}
	return items
}

func insertDeletedNode(nodes []model.TreeNode, filePath, rootPath, statusSource string, docMap map[string]treeDocumentRow, queueMap map[int64]parseTaskDocJoin) []model.TreeNode {
	filePath = filepath.Clean(strings.TrimSpace(filePath))
	if filePath == "" || filePath == "." {
		return nodes
	}
	if findNodeByKey(nodes, filePath) >= 0 {
		return nodes
	}
	ancestors := buildAncestorPaths(filePath, rootPath)
	return ensureDeletedAtPath(nodes, ancestors, filePath, statusSource, docMap, queueMap)
}

func ensureDeletedAtPath(nodes []model.TreeNode, ancestors []string, filePath, statusSource string, docMap map[string]treeDocumentRow, queueMap map[int64]parseTaskDocJoin) []model.TreeNode {
	if len(ancestors) == 0 {
		if findNodeByKey(nodes, filePath) >= 0 {
			return nodes
		}
		hasUpdate := true
		selectable := true
		node := model.TreeNode{
			Title:        nodeTitleFromPath(filePath),
			Key:          filePath,
			IsDir:        false,
			HasUpdate:    &hasUpdate,
			UpdateType:   "DELETED",
			UpdateDesc:   updateTypeDescription("DELETED"),
			Selectable:   &selectable,
			StatusSource: statusSource,
		}
		if doc, ok := docMap[filePath]; ok {
			if queue, ok := queueMap[doc.ID]; ok {
				node.ParseQueueState = queue.Status
			}
		}
		return append(nodes, node)
	}
	dirPath := ancestors[0]
	idx := findDirNodeByKey(nodes, dirPath)
	if idx < 0 {
		selectable := false
		hasUpdate := true
		nodes = append(nodes, model.TreeNode{
			Title:        nodeTitleFromPath(dirPath),
			Key:          dirPath,
			IsDir:        true,
			HasUpdate:    &hasUpdate,
			UpdateType:   "DELETED",
			UpdateDesc:   updateTypeDescription("DELETED"),
			Selectable:   &selectable,
			StatusSource: statusSource,
		})
		idx = len(nodes) - 1
	}
	child := nodes[idx]
	if child.IsDir {
		hasUpdate := true
		child.HasUpdate = &hasUpdate
		if strings.TrimSpace(child.UpdateType) == "" || strings.EqualFold(strings.TrimSpace(child.UpdateType), "UNKNOWN") {
			child.UpdateType = "DELETED"
			child.UpdateDesc = updateTypeDescription("DELETED")
		}
	}
	child.Children = ensureDeletedAtPath(child.Children, ancestors[1:], filePath, statusSource, docMap, queueMap)
	nodes[idx] = child
	return nodes
}

func buildAncestorPaths(filePath, rootPath string) []string {
	filePath = filepath.Clean(strings.TrimSpace(filePath))
	rootPath = filepath.Clean(strings.TrimSpace(rootPath))
	dirPath := filepath.Clean(filepath.Dir(filePath))
	if dirPath == "." || dirPath == filePath {
		return nil
	}
	if rootPath == "" || rootPath == "." {
		return []string{dirPath}
	}
	if dirPath != rootPath && !strings.HasPrefix(dirPath, rootPath+string(filepath.Separator)) {
		return []string{dirPath}
	}
	if dirPath == rootPath {
		return []string{rootPath}
	}
	rel := strings.TrimPrefix(strings.TrimPrefix(dirPath, rootPath), string(filepath.Separator))
	parts := strings.Split(rel, string(filepath.Separator))
	out := make([]string, 0, len(parts)+1)
	out = append(out, rootPath)
	cur := rootPath
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		cur = filepath.Join(cur, part)
		out = append(out, cur)
	}
	return out
}

func findDirNodeByKey(nodes []model.TreeNode, key string) int {
	for i := range nodes {
		if nodes[i].Key == key && nodes[i].IsDir {
			return i
		}
	}
	return -1
}

func findNodeByKey(nodes []model.TreeNode, key string) int {
	for i := range nodes {
		if nodes[i].Key == key {
			return i
		}
	}
	return -1
}

func nodeTitleFromPath(path string) string {
	name := filepath.Base(strings.TrimSpace(path))
	if name == "." || name == "/" || name == string(filepath.Separator) {
		return path
	}
	return name
}

func collectTreeScopeRoots(items []model.TreeNode) []string {
	dirRoots := make([]string, 0, len(items))
	seen := make(map[string]struct{}, len(items))
	fileKeys := make([]string, 0, len(items))
	for _, item := range items {
		key := filepath.Clean(strings.TrimSpace(item.Key))
		if key == "" || key == "." {
			continue
		}
		if item.IsDir {
			if _, ok := seen[key]; ok {
				continue
			}
			seen[key] = struct{}{}
			dirRoots = append(dirRoots, key)
			continue
		}
		fileKeys = append(fileKeys, key)
	}
	if len(dirRoots) > 0 {
		return dirRoots
	}
	if len(fileKeys) == 0 {
		return nil
	}
	common := filepath.Clean(filepath.Dir(fileKeys[0]))
	for i := 1; i < len(fileKeys); i++ {
		key := filepath.Clean(fileKeys[i])
		for common != "" && common != "." && common != string(filepath.Separator) && !pathInScope(key, []string{common}) {
			parent := filepath.Clean(filepath.Dir(common))
			if parent == common {
				break
			}
			common = parent
		}
	}
	if common == "" || common == "." {
		return nil
	}
	return []string{common}
}

func pathInScope(path string, roots []string) bool {
	path = filepath.Clean(strings.TrimSpace(path))
	if path == "" || path == "." {
		return false
	}
	if len(roots) == 0 {
		return true
	}
	for _, root := range roots {
		root = filepath.Clean(strings.TrimSpace(root))
		if root == "" || root == "." {
			continue
		}
		if root == string(filepath.Separator) {
			if strings.HasPrefix(path, string(filepath.Separator)) {
				return true
			}
			continue
		}
		if path == root || strings.HasPrefix(path, root+string(filepath.Separator)) {
			return true
		}
	}
	return false
}

func (s *Store) deletedDocumentPaths(ctx context.Context, sourceID string, scopeRoots []string, currentPaths []string) ([]string, error) {
	var rows []struct {
		SourceObjectID string
	}
	query := s.db.WithContext(ctx).
		Table("documents").
		Select("source_object_id").
		Where("source_id = ? AND parse_status = ?", sourceID, "DELETED")
	if err := query.Scan(&rows).Error; err != nil {
		return nil, err
	}
	currentSet := make(map[string]struct{}, len(currentPaths))
	for _, path := range currentPaths {
		currentSet[filepath.Clean(strings.TrimSpace(path))] = struct{}{}
	}
	out := make([]string, 0, len(rows))
	for _, row := range rows {
		path := filepath.Clean(strings.TrimSpace(row.SourceObjectID))
		if path == "" || path == "." {
			continue
		}
		if len(scopeRoots) > 0 && !pathInScope(path, scopeRoots) {
			continue
		}
		if _, ok := currentSet[path]; ok {
			continue
		}
		out = append(out, path)
	}
	return out, nil
}
