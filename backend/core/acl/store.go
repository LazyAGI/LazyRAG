package acl

import (
	"sync"
	"time"
)

// Store in-memory implementation for visibility and ACL. Replace with DB later.
type Store struct {
	mu         sync.RWMutex
	nextVisID  int64
	nextACLID  int64
	nextKBID   int64
	visibility map[int64]*VisibilityRow // kb_id -> row (missing = private)
	acl        map[int64][]*ACLRow      // kb_id -> list (no record = no permission)
	aclByID    map[int64]*ACLRow        // acl_id -> row
	kbs        map[int64]*KBInfo        // kb_id -> info (for owner, name, list)
	userGroups map[int64][]int64        // user_id -> tenant/group ids (for group ACL)
}

var defaultStore = &Store{
	visibility: make(map[int64]*VisibilityRow),
	acl:        make(map[int64][]*ACLRow),
	aclByID:    make(map[int64]*ACLRow),
	kbs:        make(map[int64]*KBInfo),
	userGroups: make(map[int64][]int64),
}

// GetStore returns the default in-memory store (for tests can swap).
func GetStore() *Store { return defaultStore }

// EnsureKB creates a KB if not exists (so we can set owner). Returns kb_id.
func (s *Store) EnsureKB(kbID int64, name string, ownerID int64) int64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.kbs[kbID] != nil {
		return kbID
	}
	if kbID == 0 {
		s.nextKBID++
		kbID = s.nextKBID
	}
	s.kbs[kbID] = &KBInfo{ID: kbID, Name: name, OwnerID: ownerID, Visibility: VisibilityPrivate}
	return kbID
}

// GetKB returns KB info if exists.
func (s *Store) GetKB(kbID int64) *KBInfo {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.kbs[kbID]
}

// SetKBVisibility sets visibility for a KB (creates row if needed).
func (s *Store) SetKBVisibility(kbID int64, level string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.nextVisID++
	s.visibility[kbID] = &VisibilityRow{ID: s.nextVisID, KbID: kbID, Level: level}
	if k := s.kbs[kbID]; k != nil {
		k.Visibility = level
	}
}

// GetVisibility returns visibility level for kb (default private).
func (s *Store) GetVisibility(kbID int64) string {
	s.mu.RLock()
	defer s.mu.RUnlock()
	if v, ok := s.visibility[kbID]; ok {
		return v.Level
	}
	return VisibilityPrivate
}

// AddACL adds an ACL row; returns acl_id.
func (s *Store) AddACL(kbID int64, granteeType string, targetID int64, permission string, createdBy int64, expiresAt *time.Time) int64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.nextACLID++
	row := &ACLRow{
		ID:          s.nextACLID,
		KbID:        kbID,
		GranteeType: granteeType,
		TargetID:    targetID,
		Permission:  permission,
		CreatedBy:   createdBy,
		CreatedAt:   time.Now(),
		ExpiresAt:   expiresAt,
	}
	s.acl[kbID] = append(s.acl[kbID], row)
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
	list := s.acl[row.KbID]
	for i, r := range list {
		if r.ID == aclID {
			s.acl[row.KbID] = append(list[:i], list[i+1:]...)
			break
		}
	}
	return true
}

// ListACL returns ACL list for kb, optionally filtered by grantee_type. Excludes expired.
func (s *Store) ListACL(kbID int64, granteeType string) []ACLListItem {
	s.mu.RLock()
	defer s.mu.RUnlock()
	now := time.Now()
	var out []ACLListItem
	for _, row := range s.acl[kbID] {
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

// GetACLByID returns ACL row and whether it belongs to kbID.
func (s *Store) GetACLByID(kbID int64, aclID int64) (*ACLRow, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	row, ok := s.aclByID[aclID]
	if !ok || row.KbID != kbID {
		return nil, false
	}
	return row, true
}

// ACLsForUser returns effective ACL entries for user: direct user entries + group entries (target_id in user's groups).
// For simplicity we only consider grantee_type=user with target_id=userID; group/tenant can be added via userGroups.
func (s *Store) ACLsForUser(kbID int64, userID int64) []*ACLRow {
	s.mu.RLock()
	defer s.mu.RUnlock()
	now := time.Now()
	var out []*ACLRow
	for _, row := range s.acl[kbID] {
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
func (s *Store) AllKBIDs() []int64 {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var ids []int64
	for id := range s.kbs {
		ids = append(ids, id)
	}
	for id := range s.visibility {
		if s.kbs[id] == nil {
			ids = append(ids, id)
		}
	}
	// dedup not strictly needed for small sets
	seen := make(map[int64]bool)
	var out []int64
	for _, id := range ids {
		if !seen[id] {
			seen[id] = true
			out = append(out, id)
		}
	}
	return out
}
