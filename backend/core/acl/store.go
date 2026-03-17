package acl

import (
	"fmt"
	"time"

	"gorm.io/gorm"
	"lazyrag/core/common/orm"
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
func (s *Store) EnsureKB(kbID string, name string, ownerID int64) string {
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
func (s *Store) AddACL(resourceType, resourceID string, granteeType string, targetID int64, permission string, createdBy int64, expiresAt *time.Time) int64 {
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
	s.db.Create(m)
	return m.ID
}

// UpdateACL 更新权限及可选的过期时间。
func (s *Store) UpdateACL(aclID int64, permission string, expiresAt *time.Time) bool {
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
		q = q.Where("grantee_type = ?", granteeType)
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
func (s *Store) ACLsForUser(resourceType, resourceID string, userID int64) []*ACLRow {
	now := time.Now()
	q := s.db.Model(&orm.ACLModel{}).
		Where("resource_type = ? AND resource_id = ?", resourceType, resourceID).
		Where("expires_at IS NULL OR expires_at > ?", now)

	var rows []orm.ACLModel
	q.Find(&rows)

	var groupIDs []int64
	s.db.Model(&orm.UserGroupModel{}).Where("user_id = ?", userID).Pluck("group_id", &groupIDs)
	groupSet := make(map[int64]bool)
	for _, g := range groupIDs {
		groupSet[g] = true
	}

	var out []*ACLRow
	for _, r := range rows {
		if r.GranteeType == GranteeUser && r.TargetID == userID {
			out = append(out, toACLRow(&r))
			continue
		}
		if r.GranteeType == GranteeTenant && groupSet[r.TargetID] {
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

// SetUserGroups 设置用户所属的组/租户 id 列表。
func (s *Store) SetUserGroups(userID int64, groupIDs []int64) {
	s.db.Where("user_id = ?", userID).Delete(&orm.UserGroupModel{})
	for _, gid := range groupIDs {
		s.db.Create(&orm.UserGroupModel{UserID: userID, GroupID: gid})
	}
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
