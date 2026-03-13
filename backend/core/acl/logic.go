package acl

// PermissionFor 返回用户对资源的有效权限及来源。
// 顺序：所有者 -> 可见性 -> ACL；无可见性/ACL 能力时对应步骤返回 false。
// kb 使用 GetKB、GetVisibility；db 仅用 ACL（无可见性/所有者）。
func PermissionFor(resourceType, resourceID string, userID int64) (permission string, source string) {
	st := GetStore()
	if resourceType == ResourceTypeKB {
		kb := st.GetKB(resourceID)
		// 1) 所有者
		if kb != nil && kb.OwnerID == userID {
			return PermWrite, SourceOwner
		}
		// 2) 可见性（表中无记录时默认 private）
		vis := st.GetVisibility(resourceID)
		if vis == VisibilityPublic {
			// 公开：所有人可读；写仍仅通过所有者/ACL
			aclPerm := maxACLPermission(st.ACLsForUser(resourceType, resourceID, userID))
			if aclPerm == PermWrite {
				return PermWrite, SourceACL
			}
			return PermRead, SourcePublic
		}
		if vis == VisibilityProtected || vis == VisibilityPrivate {
			// 需 ACL 或所有者（上面已检查所有者）
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
	// db 或未知可见性：仅看 ACL（kb 已在上面对所有者做过检查）
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

// Can 统一鉴权：判断用户是否可在资源上执行指定操作。
// action: "read" | "write" | "create_doc" | "delete_doc" | "delete_kb"
//   - read、write：按权限级别校验
//   - create_doc、delete_doc：需写权限
//   - delete_kb：需为所有者（仅 kb，且不仅写权限）
//
// 由后端代码调用，非 HTTP 接口。
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
