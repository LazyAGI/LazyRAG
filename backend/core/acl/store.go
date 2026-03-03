package acl

import (
	"fmt"
	"time"

	"gorm.io/gorm"
	"lazyrag/core/common/orm"
)

// Store holds ACL data in database via ORM.
type Store struct {
	db *orm.DB
}

var defaultStore *Store

// GetStore returns the ACL store. Must call InitStore first.
func GetStore() *Store { return defaultStore }

// InitStore initializes the ACL store with database. Call from main after DB connect.
// Runs migrations for ACL tables.
func InitStore(db *orm.DB) {
	if db == nil {
		panic("acl: InitStore requires non-nil db")
	}
	if err := db.MigrateACL(); err != nil {
		panic("acl: migrate failed: " + err.Error())
	}
	defaultStore = &Store{db: db}
}

// EnsureKB creates a KB if not exists. Returns kb_id.
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

// GetKB returns KB info if exists.
func (s *Store) GetKB(kbID string) *KBInfo {
	var m orm.KBModel
	if err := s.db.First(&m, "id = ?", kbID).Error; err != nil {
		return nil
	}
	return &KBInfo{ID: m.ID, Name: m.Name, OwnerID: m.OwnerID, Visibility: m.Visibility}
}

// SetKBVisibility sets visibility for a KB. Updates acl_visibility and acl_kbs in one transaction.
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

// GetVisibility returns visibility level for kb (default private).
func (s *Store) GetVisibility(kbID string) string {
	var v orm.VisibilityModel
	if err := s.db.Where("resource_id = ?", kbID).First(&v).Error; err != nil {
		return VisibilityPrivate
	}
	return v.Level
}

// AddACL adds an ACL row; returns acl_id.
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

// UpdateACL updates permission and optional expires_at.
func (s *Store) UpdateACL(aclID int64, permission string, expiresAt *time.Time) bool {
	res := s.db.Model(&orm.ACLModel{}).Where("id = ?", aclID).Updates(map[string]any{
		"permission": permission,
		"expires_at": expiresAt,
	})
	return res.RowsAffected > 0
}

// DeleteACL removes an ACL by id.
func (s *Store) DeleteACL(aclID int64) bool {
	res := s.db.Delete(&orm.ACLModel{}, "id = ?", aclID)
	return res.RowsAffected > 0
}

// ListACL returns ACL list for resource, optionally filtered by grantee_type. Excludes expired.
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

// GetACLByID returns ACL row and whether it belongs to the given resource.
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

// ACLsForUser returns effective ACL entries for user.
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

// SetUserGroups sets group/tenant ids for a user.
func (s *Store) SetUserGroups(userID int64, groupIDs []int64) {
	s.db.Where("user_id = ?", userID).Delete(&orm.UserGroupModel{})
	for _, gid := range groupIDs {
		s.db.Create(&orm.UserGroupModel{UserID: userID, GroupID: gid})
	}
}

// AllKBIDs returns all kb ids (from acl_kbs and acl_visibility, deduplicated).
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
