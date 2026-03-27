package acl

import "strings"

// normalizePermission 将旧权限名映射为具体权限种类，并允许按资源类型校验合法性。
func normalizePermission(resourceType, permission string) string {
	p := strings.ToUpper(strings.TrimSpace(permission))
	switch p {
	case "", strings.ToUpper(PermNone):
		return PermNone
	case strings.ToUpper(PermRead):
		if resourceType == ResourceTypeKB {
			return PermissionKBRead
		}
		if resourceType == ResourceTypeDB {
			return PermissionDatasetRead
		}
	case strings.ToUpper(PermWrite):
		if resourceType == ResourceTypeKB {
			return PermissionKBWrite
		}
		if resourceType == ResourceTypeDB {
			return PermissionDatasetWrite
		}
	case strings.ToUpper(PermUpload):
		if resourceType == ResourceTypeDB {
			return PermissionDatasetUpload
		}
	case PermissionKBRead, PermissionKBWrite, PermissionKBCreateDoc, PermissionKBDeleteDoc, PermissionKBDelete:
		if resourceType == ResourceTypeKB {
			return p
		}
	case PermissionDatasetRead, PermissionDatasetWrite, PermissionDatasetUpload:
		if resourceType == ResourceTypeDB {
			return p
		}
	}
	return ""
}

func ownerPermissions(resourceType string) []string {
	switch resourceType {
	case ResourceTypeKB:
		return []string{PermissionKBRead, PermissionKBWrite, PermissionKBCreateDoc, PermissionKBDeleteDoc, PermissionKBDelete}
	case ResourceTypeDB:
		return []string{PermissionDatasetRead, PermissionDatasetWrite, PermissionDatasetUpload}
	default:
		return nil
	}
}

func publicPermissions(resourceType string) []string {
	if resourceType == ResourceTypeKB {
		return []string{PermissionKBRead}
	}
	return nil
}

func effectivePermissions(resourceType, resourceID string, userID string) (permissions []string, source string) {
	st := GetStore()
	if st == nil || strings.TrimSpace(userID) == "" || strings.TrimSpace(resourceID) == "" {
		return nil, "private"
	}
	permSet := map[string]struct{}{}
	add := func(items []string) {
		for _, item := range items {
			if item == "" || item == PermNone {
				continue
			}
			permSet[item] = struct{}{}
		}
	}

	if resourceType == ResourceTypeKB {
		kb := st.GetKB(resourceID)
		if kb != nil && kb.OwnerID == userID {
			perms := ownerPermissions(resourceType)
			return perms, SourceOwner
		}
		vis := st.GetVisibility(resourceID)
		if vis == VisibilityPublic {
			add(publicPermissions(resourceType))
			source = SourcePublic
		}
		if vis == VisibilityProtected && source == "" {
			source = SourceProtected
		}
	}

	for _, row := range st.ACLsForUser(resourceType, resourceID, userID) {
		if perm := normalizePermission(resourceType, row.Permission); perm != "" && perm != PermNone {
			permSet[perm] = struct{}{}
			source = SourceACL
		}
	}

	if len(permSet) == 0 {
		if source == "" {
			source = "private"
		}
		return nil, source
	}
	permissions = make([]string, 0, len(permSet))
	for perm := range permSet {
		permissions = append(permissions, perm)
	}
	return permissions, source
}

// PermissionFor 返回用户对资源的有效权限及来源。
// 为兼容旧接口，这里仍返回一个聚合权限级别：none / read / write。
func PermissionFor(resourceType, resourceID string, userID string) (permission string, source string) {
	permissions, source := effectivePermissions(resourceType, resourceID, userID)
	if len(permissions) == 0 {
		return PermNone, source
	}
	for _, perm := range permissions {
		switch perm {
		case PermissionKBWrite, PermissionKBCreateDoc, PermissionKBDeleteDoc, PermissionKBDelete, PermissionDatasetWrite, PermissionDatasetUpload:
			return PermWrite, source
		}
	}
	return PermRead, source
}

// PermissionsFor 返回用户对资源生效的具体权限列表及来源。
func PermissionsFor(resourceType, resourceID string, userID string) (permissions []string, source string) {
	return effectivePermissions(resourceType, resourceID, userID)
}

func hasPermission(permissions []string, want string) bool {
	want = strings.TrimSpace(want)
	if want == "" || want == PermNone {
		return false
	}
	for _, perm := range permissions {
		if perm == want {
			return true
		}
	}
	return false
}

func actionToPermission(resourceType, action string) string {
	a := strings.TrimSpace(action)
	switch resourceType {
	case ResourceTypeKB:
		switch a {
		case PermRead:
			return PermissionKBRead
		case PermWrite:
			return PermissionKBWrite
		case "create_doc":
			return PermissionKBCreateDoc
		case "delete_doc":
			return PermissionKBDeleteDoc
		case "delete_kb":
			return PermissionKBDelete
		default:
			return normalizePermission(resourceType, a)
		}
	case ResourceTypeDB:
		switch a {
		case PermRead:
			return PermissionDatasetRead
		case PermWrite:
			return PermissionDatasetWrite
		case PermUpload, "create_doc":
			return PermissionDatasetUpload
		default:
			return normalizePermission(resourceType, a)
		}
	default:
		return ""
	}
}

// Can 统一鉴权：判断用户是否可在资源上执行指定动作或具备指定权限种类。
func Can(userID string, resourceType, resourceID string, action string) bool {
	if strings.TrimSpace(userID) == "" || resourceID == "" {
		return false
	}
	permissions, _ := PermissionsFor(resourceType, resourceID, userID)
	want := actionToPermission(resourceType, action)
	if want == "" {
		return false
	}
	if hasPermission(permissions, want) {
		return true
	}
	if resourceType == ResourceTypeDB {
		if want == PermissionDatasetRead {
			return hasPermission(permissions, PermissionDatasetWrite) || hasPermission(permissions, PermissionDatasetUpload)
		}
		if want == PermissionDatasetUpload {
			return hasPermission(permissions, PermissionDatasetWrite)
		}
	}
	if resourceType == ResourceTypeKB {
		if want == PermissionKBRead {
			return hasPermission(permissions, PermissionKBWrite)
		}
		if want == PermissionKBCreateDoc || want == PermissionKBDeleteDoc {
			return hasPermission(permissions, PermissionKBWrite)
		}
	}
	return false
}
