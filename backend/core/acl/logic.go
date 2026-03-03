package acl

// PermissionFor returns the effective permission and source for user on kb.
// Order: owner -> visibility -> ACL. If no visibility/ACL capability, those steps return false.
func PermissionFor(kbID int64, userID int64) (permission string, source string) {
	st := GetStore()
	kb := st.GetKB(kbID)
	// 1) Owner
	if kb != nil && kb.OwnerID == userID {
		return PermWrite, SourceOwner
	}
	// 2) Visibility (default private if not in table)
	vis := st.GetVisibility(kbID)
	if vis == VisibilityPublic {
		// Public: everyone gets read; write still only via owner/ACL
		aclPerm := maxACLPermission(st.ACLsForUser(kbID, userID))
		if aclPerm == PermWrite {
			return PermWrite, SourceACL
		}
		return PermRead, SourcePublic
	}
	if vis == VisibilityProtected || vis == VisibilityPrivate {
		// Need ACL or owner (already checked)
		aclPerm := maxACLPermission(st.ACLsForUser(kbID, userID))
		if aclPerm != PermNone {
			return aclPerm, SourceACL
		}
		if vis == VisibilityProtected {
			return PermNone, SourceProtected
		}
		return PermNone, "private"
	}
	// Unknown visibility treat as private
	aclPerm := maxACLPermission(st.ACLsForUser(kbID, userID))
	if aclPerm != PermNone {
		return aclPerm, SourceACL
	}
	return PermNone, "private"
}

func maxACLPermission(rows []*ACLRow) string {
	p := PermNone
	for _, r := range rows {
		if r.Permission == PermWrite {
			return PermWrite
		}
		if r.Permission == PermRead {
			p = PermRead
		}
	}
	return p
}

// Can is the unified auth function: returns whether user may perform action on kb.
// action: "read" | "write" | "create_doc" | "delete_doc" | "delete_kb"
//   - read, write: permission-level check
//   - create_doc, delete_doc: requires write
//   - delete_kb: requires owner (not just write)
//
// Call from backend by function, not via HTTP.
func Can(userID int64, kbID int64, action string) bool {
	if userID == 0 || kbID == 0 {
		return false
	}
	st := GetStore()
	kb := st.GetKB(kbID)
	perm, _ := PermissionFor(kbID, userID)
	switch action {
	case PermRead:
		return perm == PermRead || perm == PermWrite
	case PermWrite:
		return perm == PermWrite
	case "create_doc", "delete_doc":
		return perm == PermWrite
	case "delete_kb":
		return kb != nil && kb.OwnerID == userID
	default:
		return false
	}
}
