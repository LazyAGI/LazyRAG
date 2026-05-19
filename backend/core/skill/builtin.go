package skill

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"gorm.io/gorm"

	"lazymind/core/common/orm"
	"lazymind/core/evolution"
	appLog "lazymind/core/log"
)

const (
	builtinSkillOwnerUserID   = "__builtin__"
	builtinSkillOwnerUserName = "Builtin Skills"
	builtinSkillSourceType    = "builtin"
	userSkillSourceType       = "user"
)

type builtinSkillSeedSummary struct {
	ParentsCreated  int
	ChildrenCreated int
	ParentsSkipped  int
	ChildrenSkipped int
}

type builtinParentSeed struct {
	Category    string
	Name        string
	Description string
	Content     string
	Tags        []string
	Children    []builtinChildSeed
}

type builtinChildSeed struct {
	Name         string
	Description  string
	RelativePath string
	Content      string
	FileExt      string
}

func LoadVisibleSkillRows(ctx context.Context, db *gorm.DB, userID string, nodeType string) ([]orm.SkillResource, error) {
	userID = strings.TrimSpace(userID)
	nodeType = strings.TrimSpace(nodeType)

	var userRows []orm.SkillResource
	if err := db.WithContext(ctx).
		Where("owner_user_id = ? AND node_type = ?", userID, nodeType).
		Order("updated_at DESC, created_at ASC").
		Find(&userRows).Error; err != nil {
		return nil, err
	}
	var builtinRows []orm.SkillResource
	if err := db.WithContext(ctx).
		Where("owner_user_id = ? AND node_type = ?", builtinSkillOwnerUserID, nodeType).
		Order("updated_at DESC, created_at ASC").
		Find(&builtinRows).Error; err != nil {
		return nil, err
	}

	merged := make([]orm.SkillResource, 0, len(userRows)+len(builtinRows))
	seen := make(map[string]struct{}, len(userRows))
	for _, row := range userRows {
		merged = append(merged, row)
		seen[filepath.ToSlash(strings.TrimSpace(row.RelativePath))] = struct{}{}
	}
	for _, row := range builtinRows {
		key := filepath.ToSlash(strings.TrimSpace(row.RelativePath))
		if _, exists := seen[key]; exists {
			continue
		}
		merged = append(merged, row)
	}
	return merged, nil
}

func VisibleChildrenByParent(rows []orm.SkillResource) map[string][]orm.SkillResource {
	childMap := make(map[string][]orm.SkillResource)
	for _, child := range rows {
		key := child.Category + "/" + child.ParentSkillName
		childMap[key] = append(childMap[key], child)
	}
	for key := range childMap {
		children := childMap[key]
		sort.Slice(children, func(i, j int) bool {
			if children[i].RelativePath != children[j].RelativePath {
				return children[i].RelativePath < children[j].RelativePath
			}
			return children[i].CreatedAt.Before(children[j].CreatedAt)
		})
		childMap[key] = children
	}
	return childMap
}

func LoadVisibleSkillByID(ctx context.Context, db *gorm.DB, userID, skillID string) (orm.SkillResource, error) {
	var row orm.SkillResource
	if err := db.WithContext(ctx).Where("id = ?", strings.TrimSpace(skillID)).Take(&row).Error; err != nil {
		return orm.SkillResource{}, err
	}
	if strings.TrimSpace(row.OwnerUserID) == strings.TrimSpace(userID) || isBuiltinSkill(row) {
		return row, nil
	}
	return orm.SkillResource{}, gorm.ErrRecordNotFound
}

func LoadVisibleParentSkill(ctx context.Context, db *gorm.DB, userID, category, skillName string) (orm.SkillResource, error) {
	var row orm.SkillResource
	err := db.WithContext(ctx).
		Where("owner_user_id = ? AND category = ? AND node_type = ? AND skill_name = ?",
			strings.TrimSpace(userID),
			strings.TrimSpace(category),
			evolution.SkillNodeTypeParent,
			strings.TrimSpace(skillName),
		).
		Take(&row).Error
	if err == nil {
		return row, nil
	}
	if !errors.Is(err, gorm.ErrRecordNotFound) {
		return orm.SkillResource{}, err
	}
	err = db.WithContext(ctx).
		Where("owner_user_id = ? AND category = ? AND node_type = ? AND skill_name = ?",
			builtinSkillOwnerUserID,
			strings.TrimSpace(category),
			evolution.SkillNodeTypeParent,
			strings.TrimSpace(skillName),
		).
		Take(&row).Error
	return row, err
}

func isBuiltinSkill(row orm.SkillResource) bool {
	return strings.TrimSpace(row.SourceType) == builtinSkillSourceType ||
		strings.TrimSpace(row.OwnerUserID) == builtinSkillOwnerUserID
}

func builtinSkillsRoot() string {
	if value := strings.TrimSpace(os.Getenv("LAZYMIND_BUILTIN_SKILLS_DIR")); value != "" {
		return value
	}
	if info, err := os.Stat("/skills"); err == nil && info.IsDir() {
		return "/skills"
	}
	exePath, err := os.Executable()
	if err == nil {
		base := filepath.Dir(exePath)
		candidates := []string{
			filepath.Join(base, "skills"),
			filepath.Join(base, "..", "skills"),
			filepath.Join(base, "..", "..", "skills"),
			filepath.Join(base, "..", "..", "..", "skills"),
		}
		for _, candidate := range candidates {
			if info, statErr := os.Stat(candidate); statErr == nil && info.IsDir() {
				return candidate
			}
		}
	}
	wd, err := os.Getwd()
	if err == nil {
		candidates := []string{
			filepath.Join(wd, "skills"),
			filepath.Join(wd, "..", "..", "skills"),
			filepath.Join(wd, "..", "..", "..", "skills"),
		}
		for _, candidate := range candidates {
			if info, statErr := os.Stat(candidate); statErr == nil && info.IsDir() {
				return candidate
			}
		}
	}
	return ""
}

func SeedBuiltinSkills(ctx context.Context, db *gorm.DB) error {
	root := builtinSkillsRoot()
	if strings.TrimSpace(root) == "" {
		appLog.Logger.Warn().Msg("builtin skills root not found; skip seeding")
		return nil
	}
	parents, err := scanBuiltinSkills(root)
	if err != nil {
		return err
	}
	if len(parents) == 0 {
		appLog.Logger.Info().Str("root", root).Msg("no builtin skills found; skip seeding")
		return nil
	}
	summary, err := seedBuiltinSkillRows(ctx, db, parents)
	if err != nil {
		return err
	}
	appLog.Logger.Info().
		Str("root", root).
		Int("parents_created", summary.ParentsCreated).
		Int("children_created", summary.ChildrenCreated).
		Int("parents_skipped", summary.ParentsSkipped).
		Int("children_skipped", summary.ChildrenSkipped).
		Msg("builtin skills seeding completed")
	return nil
}

func scanBuiltinSkills(root string) ([]builtinParentSeed, error) {
	categoryEntries, err := os.ReadDir(root)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return nil, nil
		}
		return nil, err
	}
	parents := make([]builtinParentSeed, 0)
	for _, categoryEntry := range categoryEntries {
		categoryName := strings.TrimSpace(categoryEntry.Name())
		if !categoryEntry.IsDir() || strings.HasPrefix(categoryName, ".") {
			continue
		}
		if err := validatePathSegment(categoryName); err != nil {
			appLog.Logger.Warn().Str("category", categoryName).Err(err).Msg("skip builtin skill category with invalid path segment")
			continue
		}
		categoryDir := filepath.Join(root, categoryName)
		skillEntries, readErr := os.ReadDir(categoryDir)
		if readErr != nil {
			return nil, readErr
		}
		for _, skillEntry := range skillEntries {
			skillName := strings.TrimSpace(skillEntry.Name())
			if !skillEntry.IsDir() || strings.HasPrefix(skillName, ".") {
				continue
			}
			if err := validatePathSegment(skillName); err != nil {
				appLog.Logger.Warn().Str("category", categoryName).Str("skill", skillName).Err(err).Msg("skip builtin skill with invalid path segment")
				continue
			}
			skillDir := filepath.Join(categoryDir, skillName)
			parent, parseErr := scanBuiltinSkillDir(categoryName, skillName, skillDir)
			if parseErr != nil {
				return nil, parseErr
			}
			parents = append(parents, parent)
		}
	}
	sort.Slice(parents, func(i, j int) bool {
		if parents[i].Category != parents[j].Category {
			return parents[i].Category < parents[j].Category
		}
		return parents[i].Name < parents[j].Name
	})
	return parents, nil
}

func scanBuiltinSkillDir(category, skillName, skillDir string) (builtinParentSeed, error) {
	skillMDPath := filepath.Join(skillDir, "SKILL.md")
	contentBytes, err := os.ReadFile(skillMDPath)
	if err != nil {
		return builtinParentSeed{}, err
	}
	content := string(contentBytes)
	description, err := validateParentSkillContent(skillName, "", content)
	if err != nil {
		return builtinParentSeed{}, err
	}
	children := make([]builtinChildSeed, 0)
	walkErr := filepath.WalkDir(skillDir, func(path string, d fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if path == skillDir {
			return nil
		}
		rel, err := filepath.Rel(skillDir, path)
		if err != nil {
			return err
		}
		rel = filepath.ToSlash(rel)
		baseName := strings.TrimSpace(filepath.Base(path))
		if d.IsDir() {
			if strings.HasPrefix(baseName, ".") {
				return filepath.SkipDir
			}
			return nil
		}
		if baseName == "SKILL.md" {
			return nil
		}
		contentBytes, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		childName := strings.TrimSuffix(filepath.Base(rel), filepath.Ext(rel))
		if strings.TrimSpace(childName) == "" {
			childName = strings.ReplaceAll(rel, "/", "_")
		}
		children = append(children, builtinChildSeed{
			Name:         childName,
			Description:  rel,
			RelativePath: rel,
			Content:      string(contentBytes),
			FileExt:      normalizeExt(filepath.Ext(rel)),
		})
		return nil
	})
	if walkErr != nil {
		return builtinParentSeed{}, walkErr
	}
	sort.Slice(children, func(i, j int) bool {
		return children[i].RelativePath < children[j].RelativePath
	})
	return builtinParentSeed{
		Category:    category,
		Name:        skillName,
		Description: description,
		Content:     content,
		Children:    children,
	}, nil
}

func seedBuiltinSkillRows(ctx context.Context, db *gorm.DB, parents []builtinParentSeed) (builtinSkillSeedSummary, error) {
	summary := builtinSkillSeedSummary{}
	now := time.Now()
	for _, parent := range parents {
		parentRelPath := parentRelativePath(parent.Category, parent.Name)
		var existingParent orm.SkillResource
		parentErr := db.WithContext(ctx).
			Where("owner_user_id = ? AND relative_path = ?", builtinSkillOwnerUserID, parentRelPath).
			Take(&existingParent).Error
		if parentErr == nil {
			summary.ParentsSkipped++
		} else if errors.Is(parentErr, gorm.ErrRecordNotFound) {
			row := orm.SkillResource{
				ID:              evolution.NewID(),
				OwnerUserID:     builtinSkillOwnerUserID,
				OwnerUserName:   builtinSkillOwnerUserName,
				SourceType:      builtinSkillSourceType,
				Category:        parent.Category,
				SkillName:       parent.Name,
				NodeType:        evolution.SkillNodeTypeParent,
				Description:     parent.Description,
				FileExt:         "md",
				RelativePath:    parentRelPath,
				Content:         parent.Content,
				ContentSize:     skillContentSize(parent.Content),
				MimeType:        mimeTypeForExt("md"),
				ContentHash:     evolution.HashContent(parent.Content),
				Version:         1,
				IsEnabled:       true,
				UpdateStatus:    evolution.UpdateStatusUpToDate,
				CreateUserID:    builtinSkillOwnerUserID,
				CreateUserName:  builtinSkillOwnerUserName,
				CreatedAt:       now,
				UpdatedAt:       now,
			}
			if err := db.WithContext(ctx).Create(&row).Error; err != nil {
				return summary, err
			}
			existingParent = row
			summary.ParentsCreated++
		} else {
			return summary, parentErr
		}

		for _, child := range parent.Children {
			childRelPath := filepath.ToSlash(filepath.Join(parent.Category, parent.Name, child.RelativePath))
			var existingChild orm.SkillResource
			childErr := db.WithContext(ctx).
				Where("owner_user_id = ? AND relative_path = ?", builtinSkillOwnerUserID, childRelPath).
				Take(&existingChild).Error
			if childErr == nil {
				summary.ChildrenSkipped++
				continue
			}
			if !errors.Is(childErr, gorm.ErrRecordNotFound) {
				return summary, childErr
			}
			row := orm.SkillResource{
				ID:              evolution.NewID(),
				OwnerUserID:     builtinSkillOwnerUserID,
				OwnerUserName:   builtinSkillOwnerUserName,
				SourceType:      builtinSkillSourceType,
				Category:        parent.Category,
				ParentSkillName: existingParent.SkillName,
				SkillName:       child.Name,
				NodeType:        evolution.SkillNodeTypeChild,
				Description:     child.Description,
				FileExt:         child.FileExt,
				RelativePath:    childRelPath,
				Content:         child.Content,
				ContentSize:     skillContentSize(child.Content),
				MimeType:        mimeTypeForExt(child.FileExt),
				ContentHash:     evolution.HashContent(child.Content),
				Version:         1,
				IsEnabled:       true,
				UpdateStatus:    evolution.UpdateStatusUpToDate,
				CreateUserID:    builtinSkillOwnerUserID,
				CreateUserName:  builtinSkillOwnerUserName,
				CreatedAt:       now,
				UpdatedAt:       now,
			}
			if err := db.WithContext(ctx).Create(&row).Error; err != nil {
				return summary, err
			}
			summary.ChildrenCreated++
		}
	}
	return summary, nil
}
