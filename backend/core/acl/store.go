package acl

import (
	"fmt"
	"sort"
	"strings"
	"time"

	"gorm.io/gorm"
	"lazyrag/core/common/orm"
	"lazyrag/core/log"
)

// Store 通过 ORM 在数据库中持有 ACL 数据。
type Store struct {
	db *orm.DB
}

var defaultStore *Store

// GetStore 返回 ACL 存储。须先调用 InitStore。
func GetStore() *Store { return defaultStore }

// InitStore 使用数据库初始化 ACL 存储。在 main 中连接 DB 并执行 migrate.RunUp() 后调用。
func InitStore(db *orm.DB) {
	if db == nil {
		panic("acl: InitStore requires non-nil db")
	}
	defaultStore = &Store{db: db}
}

// EnsureKB 若知识库不存在则创建，返回 kb_id。
func (s *Store) EnsureKB(kbID string, name string, ownerID string) string {
	if kbID != "" {
		var m orm.KBModel
		if err := s.db.First(&m, "id = ?", kbID).Error; err == nil {
			return kbID
		}
	}
	if kbID == "" {
		kbID = fmt.Sprintf("kb_%d", time.Now().UnixNano())
	}
	s.db.Create(&orm.KBModel{ID: kbID, Name: name, OwnerID: ownerID, Visibility: VisibilityPrivate})
	return kbID
}

// GetKB 返回知识库信息（若存在）。
func (s *Store) GetKB(kbID string) *KBInfo {
	var m orm.KBModel
	if err := s.db.First(&m, "id = ?", kbID).Error; err != nil {
		return nil
	}
	return &KBInfo{ID: m.ID, Name: m.Name, OwnerID: m.OwnerID, Visibility: m.Visibility}
}

// SetKBVisibility 设置知识库可见级别，在同一事务中更新 acl_visibility 与 acl_kbs。
func (s *Store) SetKBVisibility(kbID string, level string) {
	_ = s.db.Transaction(func(tx *gorm.DB) error {
		var v orm.VisibilityModel
		if err := tx.Where("resource_id = ?", kbID).First(&v).Error; err != nil {
			tx.Create(&orm.VisibilityModel{ResourceID: kbID, Level: level})
		} else {
			tx.Model(&v).Update("level", level)
		}
		var k orm.KBModel
		if tx.First(&k, "id = ?", kbID).Error == nil {
			tx.Model(&k).Update("visibility", level)
		}
		return nil
	})
}

// GetVisibility 返回知识库可见级别，缺省为 private。
func (s *Store) GetVisibility(kbID string) string {
	var v orm.VisibilityModel
	if err := s.db.Where("resource_id = ?", kbID).First(&v).Error; err != nil {
		return VisibilityPrivate
	}
	return v.Level
}

// AddACL 新增一条 ACL 记录，返回 acl_id。
func canonicalGranteeType(granteeType string) string {
	switch granteeType {
	case GranteeTenant:
		return GranteeGroup
	default:
		return granteeType
	}
}

func (s *Store) AddACL(resourceType, resourceID string, granteeType string, targetID string, permission string, createdBy string, expiresAt *time.Time) int64 {
	if s == nil || s.db == nil {
		log.Logger.Error().
			Str("resource_type", resourceType).
			Str("resource_id", resourceID).
			Str("grantee_type", granteeType).
			Str("target_id", targetID).
			Str("permission", permission).
			Str("created_by", createdBy).
			Msg("add acl failed: store is not initialized")
		return 0
	}
	permission = normalizePermission(resourceType, permission)
	granteeType = canonicalGranteeType(granteeType)
	if permission == "" || permission == PermNone {
		log.Logger.Warn().
			Str("resource_type", resourceType).
			Str("resource_id", resourceID).
			Str("grantee_type", granteeType).
			Str("target_id", targetID).
			Str("permission", permission).
			Str("created_by", createdBy).
			Msg("add acl skipped: invalid normalized permission")
		return 0
	}
	if strings.TrimSpace(targetID) == "" {
		log.Logger.Warn().
			Str("resource_type", resourceType).
			Str("resource_id", resourceID).
			Str("grantee_type", granteeType).
			Str("permission", permission).
			Str("created_by", createdBy).
			Msg("add acl skipped: empty target id")
		return 0
	}
	var existing orm.ACLModel
	if err := s.db.Where("resource_type = ? AND resource_id = ? AND grantee_type = ? AND target_id = ? AND permission = ?", resourceType, resourceID, granteeType, targetID, permission).First(&existing).Error; err == nil {
		updates := map[string]any{}
		if expiresAt != nil || existing.ExpiresAt != nil {
			updates["expires_at"] = expiresAt
		}
		if len(updates) > 0 {
			if err := s.db.Model(&existing).Updates(updates).Error; err != nil {
				log.Logger.Error().
					Err(err).
					Int64("acl_id", existing.ID).
					Str("resource_type", resourceType).
					Str("resource_id", resourceID).
					Str("grantee_type", granteeType).
					Str("target_id", targetID).
					Str("permission", permission).
					Msg("add acl found existing row but failed to update expires_at")
				return 0
			}
		}
		log.Logger.Info().
			Int64("acl_id", existing.ID).
			Str("resource_type", resourceType).
			Str("resource_id", resourceID).
			Str("grantee_type", granteeType).
			Str("target_id", targetID).
			Str("permission", permission).
			Str("created_by", createdBy).
			Msg("add acl reused existing row")
		return existing.ID
	}
	m := &orm.ACLModel{
		ResourceType: resourceType,
		ResourceID:   resourceID,
		GranteeType:  granteeType,
		TargetID:     targetID,
		Permission:   permission,
		CreatedBy:    createdBy,
		CreatedAt:    time.Now(),
		ExpiresAt:    expiresAt,
	}
	if err := s.db.Create(m).Error; err != nil {
		log.Logger.Error().
			Err(err).
			Str("resource_type", resourceType).
			Str("resource_id", resourceID).
			Str("grantee_type", granteeType).
			Str("target_id", targetID).
			Str("permission", permission).
			Str("created_by", createdBy).
			Msg("add acl insert failed")
		return 0
	}
	log.Logger.Info().
		Int64("acl_id", m.ID).
		Str("resource_type", resourceType).
		Str("resource_id", resourceID).
		Str("grantee_type", granteeType).
		Str("target_id", targetID).
		Str("permission", permission).
		Str("created_by", createdBy).
		Msg("add acl inserted row")
	return m.ID
}

// UpdateACL 更新权限及可选的过期时间。
func (s *Store) UpdateACL(aclID int64, permission string, expiresAt *time.Time) bool {
	var row orm.ACLModel
	if err := s.db.First(&row, "id = ?", aclID).Error; err != nil {
		return false
	}
	permission = normalizePermission(row.ResourceType, permission)
	res := s.db.Model(&orm.ACLModel{}).Where("id = ?", aclID).Updates(map[string]any{
		"permission": permission,
		"expires_at": expiresAt,
	})
	return res.RowsAffected > 0
}

// DeleteACL 按 id 删除一条 ACL。
func (s *Store) DeleteACL(aclID int64) bool {
	res := s.db.Delete(&orm.ACLModel{}, "id = ?", aclID)
	return res.RowsAffected > 0
}

// ListACL 返回资源的 ACL 列表，可按 grantee_type 过滤，排除已过期项。
func (s *Store) ListACL(resourceType, resourceID string, granteeType string) []ACLListItem {
	q := s.db.Model(&orm.ACLModel{}).
		Where("resource_type = ? AND resource_id = ?", resourceType, resourceID).
		Where("expires_at IS NULL OR expires_at > ?", time.Now())
	if granteeType != "" {
		q = q.Where("grantee_type = ?", canonicalGranteeType(granteeType))
	}
	var rows []orm.ACLModel
	q.Find(&rows)
	out := make([]ACLListItem, 0, len(rows))
	for _, r := range rows {
		out = append(out, ACLListItem{
			ID:          r.ID,
			GranteeType: r.GranteeType,
			GranteeID:   r.TargetID,
			Permission:  r.Permission,
			CreatedAt:   r.CreatedAt,
		})
	}
	return out
}

// GetACLByID 按 id 取 ACL 行，并返回是否属于指定资源。
func (s *Store) GetACLByID(resourceType, resourceID string, aclID int64) (*ACLRow, bool) {
	var m orm.ACLModel
	if err := s.db.First(&m, "id = ? AND resource_type = ? AND resource_id = ?", aclID, resourceType, resourceID).Error; err != nil {
		return nil, false
	}
	return &ACLRow{
		ID:           m.ID,
		ResourceType: m.ResourceType,
		ResourceID:   m.ResourceID,
		GranteeType:  m.GranteeType,
		TargetID:     m.TargetID,
		Permission:   m.Permission,
		CreatedBy:    m.CreatedBy,
		CreatedAt:    m.CreatedAt,
		ExpiresAt:    m.ExpiresAt,
	}, true
}

// ACLsForUser 返回对用户生效的 ACL 记录（含用户直赋与租户/组继承）。
func (s *Store) ACLsForUser(resourceType, resourceID string, userID string) []*ACLRow {
	now := time.Now()
	q := s.db.Model(&orm.ACLModel{}).
		Where("resource_type = ? AND resource_id = ?", resourceType, resourceID).
		Where("expires_at IS NULL OR expires_at > ?", now)

	var rows []orm.ACLModel
	q.Find(&rows)

	var groupIDs []string
	s.db.Model(&orm.UserGroupModel{}).Where("user_id = ?", userID).Pluck("group_id", &groupIDs)
	groupSet := make(map[string]bool)
	for _, g := range groupIDs {
		groupSet[g] = true
	}

	var out []*ACLRow
	for _, r := range rows {
		if r.GranteeType == GranteeUser && r.TargetID == userID {
			out = append(out, toACLRow(&r))
			continue
		}
		if (r.GranteeType == GranteeGroup || r.GranteeType == GranteeTenant) && groupSet[r.TargetID] {
			out = append(out, toACLRow(&r))
		}
	}
	return out
}

func toACLRow(m *orm.ACLModel) *ACLRow {
	return &ACLRow{
		ID:           m.ID,
		ResourceType: m.ResourceType,
		ResourceID:   m.ResourceID,
		GranteeType:  m.GranteeType,
		TargetID:     m.TargetID,
		Permission:   m.Permission,
		CreatedBy:    m.CreatedBy,
		CreatedAt:    m.CreatedAt,
		ExpiresAt:    m.ExpiresAt,
	}
}

// EnsureGroup 若组不存在则创建；name 可为空。
func (s *Store) EnsureGroup(groupID string, name string) string {
	groupID = strings.TrimSpace(groupID)
	if groupID == "" {
		groupID = fmt.Sprintf("group_%d", time.Now().UnixNano())
	}
	var g orm.ACLGroupModel
	if err := s.db.First(&g, "id = ?", groupID).Error; err == nil {
		if name != "" && g.Name != name {
			s.db.Model(&g).Update("name", name)
		}
		return groupID
	}
	s.db.Create(&orm.ACLGroupModel{ID: groupID, Name: name})
	return groupID
}

// DeleteGroup 删除组定义、成员关系与基于该组的 ACL 行。
func (s *Store) DeleteGroup(groupID string) {
	if strings.TrimSpace(groupID) == "" {
		return
	}
	_ = s.db.Transaction(func(tx *gorm.DB) error {
		tx.Delete(&orm.UserGroupModel{}, "group_id = ?", groupID)
		tx.Delete(&orm.ACLModel{}, "grantee_type IN ? AND target_id = ?", []string{GranteeGroup, GranteeTenant}, groupID)
		tx.Delete(&orm.ACLGroupModel{}, "id = ?", groupID)
		return nil
	})
}

// AddUserToGroup 为用户添加一个组成员关系。
func (s *Store) AddUserToGroup(userID, groupID string) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(groupID) == "" {
		return
	}
	s.EnsureGroup(groupID, "")
	s.db.FirstOrCreate(&orm.UserGroupModel{}, &orm.UserGroupModel{UserID: userID, GroupID: groupID})
}

// RemoveUserFromGroup 移除用户的组成员关系，不影响该用户自身 ACL。
func (s *Store) RemoveUserFromGroup(userID, groupID string) {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(groupID) == "" {
		return
	}
	s.db.Delete(&orm.UserGroupModel{}, "user_id = ? AND group_id = ?", userID, groupID)
}

// SetUserGroups 设置用户所属的组 id 列表；未包含的旧组关系会被移除。
func (s *Store) SetUserGroups(userID string, groupIDs []string) {
	s.db.Where("user_id = ?", userID).Delete(&orm.UserGroupModel{})
	for _, gid := range groupIDs {
		s.AddUserToGroup(userID, gid)
	}
}

// ListGroups 返回所有组及成员数。
func (s *Store) ListGroups() []GroupInfo {
	var groups []orm.ACLGroupModel
	s.db.Order("id asc").Find(&groups)
	out := make([]GroupInfo, 0, len(groups))
	for _, g := range groups {
		var n int64
		_ = s.db.Model(&orm.UserGroupModel{}).Where("group_id = ?", g.ID).Count(&n).Error
		out = append(out, GroupInfo{ID: g.ID, Name: g.Name, UserCount: n})
	}
	return out
}

// ListGroupUsers 返回组成员列表。
func (s *Store) ListGroupUsers(groupID string) []GroupMember {
	var rows []orm.UserGroupModel
	s.db.Where("group_id = ?", groupID).Order("user_id asc").Find(&rows)
	out := make([]GroupMember, 0, len(rows))
	for _, row := range rows {
		out = append(out, GroupMember{UserID: row.UserID})
	}
	return out
}

// ListUserGroups 返回用户所属组列表。
func (s *Store) ListUserGroups(userID string) []GroupInfo {
	var memberships []orm.UserGroupModel
	s.db.Where("user_id = ?", userID).Order("group_id asc").Find(&memberships)
	out := make([]GroupInfo, 0, len(memberships))
	for _, membership := range memberships {
		var group orm.ACLGroupModel
		if err := s.db.First(&group, "id = ?", membership.GroupID).Error; err != nil {
			continue
		}
		var n int64
		_ = s.db.Model(&orm.UserGroupModel{}).Where("group_id = ?", group.ID).Count(&n).Error
		out = append(out, GroupInfo{ID: group.ID, Name: group.Name, UserCount: n})
	}
	return out
}

// ReplaceACLForKB replaces all ACL rows for the kb with submitted grants.
// It is used by authorization page "save" behavior.
func (s *Store) ReplaceACLForKB(kbID string, grants []AuthorizationSubjectGrant, createdBy string) (int64, error) {
	var inserted int64
	err := s.db.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("resource_type = ? AND resource_id = ?", ResourceTypeKB, kbID).Delete(&orm.ACLModel{}).Error; err != nil {
			return err
		}
		now := time.Now()
		for _, g := range grants {
			gt := canonicalGranteeType(g.GranteeType)
			if gt != GranteeUser && gt != GranteeGroup {
				continue
			}
			for _, p := range g.Permissions {
				np := normalizePermission(ResourceTypeKB, p)
				if np == "" || np == PermNone {
					continue
				}
				row := orm.ACLModel{
					ResourceType: ResourceTypeKB,
					ResourceID:   kbID,
					GranteeType:  gt,
					TargetID:     g.GranteeID,
					Permission:   np,
					CreatedBy:    createdBy,
					CreatedAt:    now,
				}
				if err := tx.Create(&row).Error; err != nil {
					return err
				}
				inserted++
			}
		}
		return nil
	})
	return inserted, err
}

// ListKBAuthorization returns ACL rows grouped by (grantee_type, grantee_id).
func (s *Store) ListKBAuthorization(kbID string) []AuthorizationSubjectGrant {
	rows := s.ListACL(ResourceTypeKB, kbID, "")
	type key struct {
		t string
		i string
	}
	m := map[key]map[string]struct{}{}
	for _, r := range rows {
		k := key{t: canonicalGranteeType(r.GranteeType), i: r.GranteeID}
		if _, ok := m[k]; !ok {
			m[k] = map[string]struct{}{}
		}
		np := normalizePermission(ResourceTypeKB, r.Permission)
		if np == "" || np == PermNone {
			continue
		}
		m[k][np] = struct{}{}
	}
	out := make([]AuthorizationSubjectGrant, 0, len(m))
	for k, perms := range m {
		items := make([]string, 0, len(perms))
		for p := range perms {
			items = append(items, p)
		}
		sort.Strings(items)
		out = append(out, AuthorizationSubjectGrant{
			GranteeType: k.t,
			GranteeID:   k.i,
			Permissions: items,
		})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].GranteeType != out[j].GranteeType {
			return out[i].GranteeType < out[j].GranteeType
		}
		return out[i].GranteeID < out[j].GranteeID
	})
	return out
}

// ListKnownUserIDs returns user IDs that are known to ACL store.
// Since Core has no user profile table, this is assembled from ACL rows and group memberships.
func (s *Store) ListKnownUserIDs() []string {
	seen := map[string]struct{}{}
	var ids []string
	_ = s.db.Model(&orm.ACLModel{}).Where("grantee_type = ?", GranteeUser).Distinct("target_id").Pluck("target_id", &ids).Error
	for _, id := range ids {
		if strings.TrimSpace(id) != "" {
			seen[id] = struct{}{}
		}
	}
	ids = ids[:0]
	_ = s.db.Model(&orm.UserGroupModel{}).Distinct("user_id").Pluck("user_id", &ids).Error
	for _, id := range ids {
		if strings.TrimSpace(id) != "" {
			seen[id] = struct{}{}
		}
	}
	out := make([]string, 0, len(seen))
	for id := range seen {
		out = append(out, id)
	}
	sort.Strings(out)
	return out
}

// AllKBIDs 返回所有知识库 id（来自 acl_kbs 与 acl_visibility，去重）。
func (s *Store) AllKBIDs() []string {
	seen := make(map[string]bool)
	var ids []string
	s.db.Model(&orm.KBModel{}).Pluck("id", &ids)
	for _, id := range ids {
		seen[id] = true
	}
	s.db.Model(&orm.VisibilityModel{}).Distinct("resource_id").Pluck("resource_id", &ids)
	for _, id := range ids {
		seen[id] = true
	}
	out := make([]string, 0, len(seen))
	for id := range seen {
		out = append(out, id)
	}
	return out
}
