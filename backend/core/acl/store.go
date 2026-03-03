package acl

import (
	"fmt"
	"sync"
	"time"
)

// aclKey returns composite key for ACL index.
func aclKey(resourceType, resourceID string) string {
	return resourceType + ":" + resourceID
}

// Store in-memory implementation for visibility and ACL. Replace with DB later.
type Store struct {
	mu         sync.RWMutex
	nextVisID  int64
	nextACLID  int64
	nextKBID   int64
	visibility map[string]*VisibilityRow // kb_id -> row (missing = private)
	acl        map[string][]*ACLRow      // resourceType:resourceID -> list (no record = no permission)
	aclByID    map[int64]*ACLRow         // acl_id -> row
	kbs        map[string]*KBInfo        // kb_id -> info (for owner, name, list)
	userGroups map[int64][]int64         // user_id -> tenant/group ids (for group ACL)
}

var defaultStore = &Store{
	visibility: make(map[string]*VisibilityRow),
	acl:        make(map[string][]*ACLRow),
	aclByID:    make(map[int64]*ACLRow),
	kbs:        make(map[string]*KBInfo),
	userGroups: make(map[int64][]int64),
}

// GetStore returns the default in-memory store (for tests can swap).
func GetStore() *Store { return defaultStore }

// EnsureKB creates a KB if not exists (so we can set owner). Returns kb_id.
func (s *Store) EnsureKB(kbID string, name string, ownerID int64) string {
	s.mu.Lock()
	defer s.mu.Unlock()
	if kbID != "" && s.kbs[kbID] != nil {
		return kbID
	}
	if kbID == "" {
		s.nextKBID++
		kbID = fmt.Sprintf("kb_%d", s.nextKBID)
	}
	s.kbs[kbID] = &KBInfo{ID: kbID, Name: name, OwnerID: ownerID, Visibility: VisibilityPrivate}
	return kbID
}

// GetKB returns KB info if exists.
func (s *Store) GetKB(kbID string) *KBInfo {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.kbs[kbID]
}

// SetKBVisibility sets visibility for a KB (creates row if needed).
func (s *Store) SetKBVisibility(kbID string, level string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.nextVisID++
	s.visibility[kbID] = &VisibilityRow{ID: s.nextVisID, ResourceID: kbID, Level: level}
	if k := s.kbs[kbID]; k != nil {
		k.Visibility = level
	}
}

// GetVisibility returns visibility level for kb (default private).
func (s *Store) GetVisibility(kbID string) string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if v, ok := s.visibility[kbID]; ok {
		return v.Level
	}
	return VisibilityPrivate
}

// AddACL adds an ACL row; returns acl_id.
func (s *Store) AddACL(resourceType, resourceID string, granteeType string, targetID int64, permission string, createdBy int64, expiresAt *time.Time) int64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.nextACLID++
	row := &ACLRow{
		ID:           s.nextACLID,
		ResourceType: resourceType,
		ResourceID:   resourceID,
		GranteeType:  granteeType,
		TargetID:     targetID,
		Permission:   permission,
		CreatedBy:    createdBy,
		CreatedAt:    time.Now(),
		ExpiresAt:    expiresAt,
	}
	key := aclKey(resourceType, resourceID)
	s.acl[key] = append(s.acl[key], row)
	s.aclByID[row.ID] = row
	return row.ID
}

// UpdateACL updates permission and optional expires_at.
func (s *Store) UpdateACL(aclID int64, permission string, expiresAt *time.Time) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	row, ok := s.aclByID[aclID]
	if !ok {
		return false
	}
	row.Permission = permission
	row.ExpiresAt = expiresAt
	return true
}

// DeleteACL removes an ACL by id.
func (s *Store) DeleteACL(aclID int64) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	row, ok := s.aclByID[aclID]
	if !ok {
		return false
	}
	delete(s.aclByID, aclID)
	key := aclKey(row.ResourceType, row.ResourceID)
	list := s.acl[key]
	for i, r := range list {
		if r.ID == aclID {
			s.acl[key] = append(list[:i], list[i+1:]...)
			break
		}
	}
	return true
}

// ListACL returns ACL list for resource, optionally filtered by grantee_type. Excludes expired.
func (s *Store) ListACL(resourceType, resourceID string, granteeType string) []ACLListItem {
	s.mu.RLock()
	defer s.mu.RUnlock()
	now := time.Now()
	var out []ACLListItem
	for _, row := range s.acl[aclKey(resourceType, resourceID)] {
		if row.ExpiresAt != nil && row.ExpiresAt.Before(now) {
			continue
		}
		if granteeType != "" && row.GranteeType != granteeType {
			continue
		}
		out = append(out, ACLListItem{
			ID:          row.ID,
			GranteeType: row.GranteeType,
			GranteeID:   row.TargetID,
			Permission:  row.Permission,
			CreatedAt:   row.CreatedAt,
		})
	}
	return out
}

// GetACLByID returns ACL row and whether it belongs to the given resource.
func (s *Store) GetACLByID(resourceType, resourceID string, aclID int64) (*ACLRow, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	row, ok := s.aclByID[aclID]
	if !ok || row.ResourceType != resourceType || row.ResourceID != resourceID {
		return nil, false
	}
	return row, true
}

// ACLsForUser returns effective ACL entries for user: direct user entries + group entries (target_id in user's groups).
// For simplicity we only consider grantee_type=user with target_id=userID; group/tenant can be added via userGroups.
func (s *Store) ACLsForUser(resourceType, resourceID string, userID int64) []*ACLRow {
	s.mu.RLock()
	defer s.mu.RUnlock()
	now := time.Now()
	var out []*ACLRow
	for _, row := range s.acl[aclKey(resourceType, resourceID)] {
		if row.ExpiresAt != nil && row.ExpiresAt.Before(now) {
			continue
		}
		if row.GranteeType == GranteeUser && row.TargetID == userID {
			out = append(out, row)
			continue
		}
		if row.GranteeType == GranteeTenant {
			for _, gid := range s.userGroups[userID] {
				if row.TargetID == gid {
					out = append(out, row)
					break
				}
			}
		}
	}
	return out
}

// SetUserGroups sets group/tenant ids for a user (for permission formula).
func (s *Store) SetUserGroups(userID int64, groupIDs []int64) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.userGroups[userID] = groupIDs
}

// AllKBIDs returns all kb ids (for list filtering by permission).
func (s *Store) AllKBIDs() []string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	seen := make(map[string]bool)
	for id := range s.kbs {
		seen[id] = true
	}
	for id := range s.visibility {
		if !seen[id] {
			seen[id] = true
		}
	}
	var out []string
	for id := range seen {
		out = append(out, id)
	}
	return out
}
