package acl

// PermissionFor returns the effective permission and source for user on resource.
// Order: owner -> visibility -> ACL. If no visibility/ACL capability, those steps return false.
// For kb: uses GetKB, GetVisibility. For db: only ACL (no visibility/owner).
func PermissionFor(resourceType, resourceID string, userID int64) (permission string, source string) {
	st := GetStore()
	if resourceType == ResourceTypeKB {
		kb := st.GetKB(resourceID)
		// 1) Owner
		if kb != nil && kb.OwnerID == userID {
			return PermWrite, SourceOwner
		}
		// 2) Visibility (default: private if not in table)
		vis := st.GetVisibility(resourceID)
		if vis == VisibilityPublic {
			// Public: everyone gets read; write still only via owner/ACL
			aclPerm := maxACLPermission(st.ACLsForUser(resourceType, resourceID, userID))
			if aclPerm == PermWrite {
				return PermWrite, SourceACL
			}
			return PermRead, SourcePublic
		}
		if vis == VisibilityProtected || vis == VisibilityPrivate {
			// Need ACL or owner (already checked)
			aclPerm := maxACLPermission(st.ACLsForUser(resourceType, resourceID, userID))
			if aclPerm != PermNone {
				return aclPerm, SourceACL
			}
			if vis == VisibilityProtected {
				return PermNone, SourceProtected
			}
			return PermNone, "private"
		}
	}
	// db or unknown visibility: only ACL (owner already checked for kb above)
	aclPerm := maxACLPermission(st.ACLsForUser(resourceType, resourceID, userID))
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

// Can is the unified auth function: returns whether user may perform action on resource.
// action: "read" | "write" | "create_doc" | "delete_doc" | "delete_kb"
//   - read, write: permission-level check
//   - create_doc, delete_doc: requires write
//   - delete_kb: requires owner (kb only, not just write)
//
// Call from backend by function, not via HTTP.
func Can(userID int64, resourceType, resourceID string, action string) bool {
	if userID == 0 || resourceID == "" {
		return false
	}
	perm, _ := PermissionFor(resourceType, resourceID, userID)
	switch action {
	case PermRead:
		return perm == PermRead || perm == PermWrite
	case PermWrite:
		return perm == PermWrite
	case "create_doc", "delete_doc":
		return perm == PermWrite
	case "delete_kb":
		if resourceType != ResourceTypeKB {
			return false
		}
		kb := GetStore().GetKB(resourceID)
		return kb != nil && kb.OwnerID == userID
	default:
		return false
	}
}
