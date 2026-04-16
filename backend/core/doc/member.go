package doc

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"sort"
	"strings"
	"time"

	"lazyrag/core/acl"
	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/log"
	"lazyrag/core/store"
)

type datasetRole struct {
	Role        string `json:"role,omitempty"`
	DisplayName string `json:"display_name,omitempty"`
}

type datasetMember struct {
	Name       string      `json:"name,omitempty"`
	DatasetID  string      `json:"dataset_id,omitempty"`
	UserID     string      `json:"user_id,omitempty"`
	User       string      `json:"user,omitempty"`
	Group      string      `json:"group,omitempty"`
	Role       datasetRole `json:"role,omitempty"`
	CreateTime string      `json:"create_time,omitempty"`
	GroupID    string      `json:"group_id,omitempty"`
	IsCreator  bool        `json:"is_creator,omitempty"`
}

type listDatasetMembersResponse struct {
	DatasetMembers []datasetMember `json:"dataset_members"`
	NextPageToken  string          `json:"next_page_token,omitempty"`
}

type searchDatasetMemberRequest struct {
	Parent     string `json:"parent,omitempty"`
	NamePrefix string `json:"name_prefix,omitempty"`
	IsAll      bool   `json:"is_all,omitempty"`
	PageToken  string `json:"page_token,omitempty"`
	PageSize   int32  `json:"page_size,omitempty"`
}

type batchAddDatasetMemberRequest struct {
	Parent        string   `json:"parent,omitempty"`
	UserNameList  []string `json:"user_name_list,omitempty"`
	GroupNameList []string `json:"group_name_list,omitempty"`
	UserIDList    []string `json:"user_id_list,omitempty"`
	GroupIDList   []string `json:"group_id_list,omitempty"`
	Role          struct {
		Role string `json:"role,omitempty"`
	} `json:"role"`
}

type batchAddDatasetMemberResponse struct {
	DatasetMembers []datasetMember `json:"dataset_members"`
}

type updateDatasetMemberRequest struct {
	DatasetMember datasetMember `json:"dataset_member"`
	UpdateMask    struct {
		Paths []string `json:"paths,omitempty"`
	} `json:"update_mask"`
}

func ListDatasetMembers(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	if datasetID == "" {
		common.ReplyErr(w, "missing dataset", http.StatusBadRequest)
		return
	}
	if _, userID, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetRead); !ok {
		if userID == "" {
			common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		} else {
			replyDatasetForbidden(w)
		}
		return
	}
	members := listDatasetMembers(r, datasetID, "")
	common.ReplyJSON(w, listDatasetMembersResponse{DatasetMembers: members, NextPageToken: ""})
}

func GetDatasetMember(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	userID := userIDFromPath(r)
	if datasetID == "" || userID == "" {
		common.ReplyErr(w, "invalid path", http.StatusBadRequest)
		return
	}
	if _, requestUserID, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetRead); !ok {
		if requestUserID == "" {
			common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		} else {
			replyDatasetForbidden(w)
		}
		return
	}
	member, ok := getDatasetMemberByUserID(r, datasetID, userID)
	if !ok {
		common.ReplyErr(w, "member not found", http.StatusNotFound)
		return
	}
	common.ReplyJSON(w, member)
}

func DeleteDatasetGroupMember(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	groupID := groupIDFromPath(r)
	if datasetID == "" || groupID == "" {
		common.ReplyErr(w, "invalid path", http.StatusBadRequest)
		return
	}
	if _, _, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetWrite); !ok {
		replyDatasetForbidden(w)
		return
	}
	rows := acl.GetStore().ListACL(acl.ResourceTypeDB, datasetID, acl.GranteeGroup)
	deleted := false
	for _, row := range rows {
		if row.GranteeID == groupID {
			acl.GetStore().DeleteACL(row.ID)
			deleted = true
		}
	}
	if !deleted {
		common.ReplyErr(w, "member not found", http.StatusNotFound)
		return
	}
	w.WriteHeader(http.StatusOK)
}

func DeleteDatasetMember(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	userID := userIDFromPath(r)
	if datasetID == "" || userID == "" {
		common.ReplyErr(w, "invalid path", http.StatusBadRequest)
		return
	}
	if _, _, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetWrite); !ok {
		replyDatasetForbidden(w)
		return
	}
	rows := acl.GetStore().ListACL(acl.ResourceTypeDB, datasetID, acl.GranteeUser)
	deleted := false
	for _, row := range rows {
		if row.GranteeID == userID {
			acl.GetStore().DeleteACL(row.ID)
			deleted = true
		}
	}
	if !deleted {
		common.ReplyErr(w, "member not found", http.StatusNotFound)
		return
	}
	w.WriteHeader(http.StatusOK)
}

func UpdateDatasetGroupMember(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	groupID := groupIDFromPath(r)
	if datasetID == "" || groupID == "" {
		common.ReplyErr(w, "invalid path", http.StatusBadRequest)
		return
	}
	if _, _, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetWrite); !ok {
		replyDatasetForbidden(w)
		return
	}
	var req updateDatasetMemberRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "invalid body", err), http.StatusBadRequest)
		return
	}
	perms := roleToPermissions(req.DatasetMember.Role.Role)
	if len(perms) == 0 {
		common.ReplyErr(w, "invalid role", http.StatusBadRequest)
		return
	}
	rows := acl.GetStore().ListACL(acl.ResourceTypeDB, datasetID, acl.GranteeGroup)
	if ok := upsertDatasetMemberPermissions(acl.GetStore(), datasetID, acl.GranteeGroup, groupID, perms, strings.TrimSpace(store.UserID(r)), rows); !ok {
		common.ReplyErr(w, "update failed", http.StatusInternalServerError)
		return
	}
	member, ok := getDatasetMemberByPrincipal(r, datasetID, acl.GranteeGroup, groupID)
	if !ok {
		common.ReplyErr(w, "member not found", http.StatusNotFound)
		return
	}
	common.ReplyJSON(w, member)
}

func UpdateDatasetMember(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	userID := userIDFromPath(r)
	if datasetID == "" || userID == "" {
		common.ReplyErr(w, "invalid path", http.StatusBadRequest)
		return
	}
	if _, _, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetWrite); !ok {
		replyDatasetForbidden(w)
		return
	}
	var req updateDatasetMemberRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "invalid body", err), http.StatusBadRequest)
		return
	}
	perms := roleToPermissions(req.DatasetMember.Role.Role)
	if len(perms) == 0 {
		common.ReplyErr(w, "invalid role", http.StatusBadRequest)
		return
	}
	rows := acl.GetStore().ListACL(acl.ResourceTypeDB, datasetID, acl.GranteeUser)
	if ok := upsertDatasetMemberPermissions(acl.GetStore(), datasetID, acl.GranteeUser, userID, perms, strings.TrimSpace(store.UserID(r)), rows); !ok {
		common.ReplyErr(w, "update failed", http.StatusInternalServerError)
		return
	}
	member, ok := getDatasetMemberByUserID(r, datasetID, userID)
	if !ok {
		common.ReplyErr(w, "member not found", http.StatusNotFound)
		return
	}
	common.ReplyJSON(w, member)
}

func SearchDatasetMember(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	if datasetID == "" {
		common.ReplyErr(w, "missing dataset", http.StatusBadRequest)
		return
	}
	if _, userID, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetRead); !ok {
		if userID == "" {
			common.ReplyErr(w, "missing X-User-Id", http.StatusBadRequest)
		} else {
			replyDatasetForbidden(w)
		}
		return
	}
	prefix := strings.TrimSpace(r.URL.Query().Get("name_prefix"))
	if prefix == "" {
		var req searchDatasetMemberRequest
		if r.Body != nil {
			if err := json.NewDecoder(r.Body).Decode(&req); err != nil && err.Error() != "EOF" {
				common.ReplyErr(w, "invalid body", http.StatusBadRequest)
				return
			}
		}
		prefix = strings.TrimSpace(req.NamePrefix)
	}
	members := listDatasetMembers(r, datasetID, prefix)
	common.ReplyJSON(w, listDatasetMembersResponse{DatasetMembers: members, NextPageToken: ""})
}

func BatchAddDatasetMember(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	requestUserID := strings.TrimSpace(store.UserID(r))
	if datasetID == "" {
		log.Logger.Warn().
			Str("handler", "BatchAddDatasetMember").
			Str("request_user_id", requestUserID).
			Msg("batch add dataset member failed: missing dataset id")
		common.ReplyErr(w, "missing dataset", http.StatusBadRequest)
		return
	}
	if _, _, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetWrite); !ok {
		log.Logger.Warn().
			Str("handler", "BatchAddDatasetMember").
			Str("dataset_id", datasetID).
			Str("request_user_id", requestUserID).
			Msg("batch add dataset member forbidden: no dataset write permission")
		replyDatasetForbidden(w)
		return
	}
	var req batchAddDatasetMemberRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		log.Logger.Warn().
			Err(err).
			Str("handler", "BatchAddDatasetMember").
			Str("dataset_id", datasetID).
			Str("request_user_id", requestUserID).
			Msg("batch add dataset member failed: invalid body")
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "invalid body", err), http.StatusBadRequest)
		return
	}
	perms := roleToPermissions(req.Role.Role)
	if len(perms) == 0 {
		log.Logger.Warn().
			Str("handler", "BatchAddDatasetMember").
			Str("dataset_id", datasetID).
			Str("request_user_id", requestUserID).
			Str("role", strings.TrimSpace(req.Role.Role)).
			Msg("batch add dataset member failed: invalid role")
		common.ReplyErr(w, "invalid role", http.StatusBadRequest)
		return
	}
	st := acl.GetStore()
	if st == nil {
		log.Logger.Error().
			Str("handler", "BatchAddDatasetMember").
			Str("dataset_id", datasetID).
			Str("request_user_id", requestUserID).
			Msg("batch add dataset member failed: acl store is nil")
		common.ReplyErr(w, "acl store not initialized", http.StatusInternalServerError)
		return
	}
	if len(req.UserIDList) == 0 && len(req.GroupIDList) == 0 {
		log.Logger.Warn().
			Str("handler", "BatchAddDatasetMember").
			Str("dataset_id", datasetID).
			Str("request_user_id", requestUserID).
			Msg("batch add dataset member failed: empty user_id_list and group_id_list")
		common.ReplyErr(w, "user_id_list and group_id_list cannot both be empty", http.StatusBadRequest)
		return
	}
	createdBy := requestUserID
	log.Logger.Info().
		Str("handler", "BatchAddDatasetMember").
		Str("dataset_id", datasetID).
		Str("request_user_id", requestUserID).
		Str("role", strings.TrimSpace(req.Role.Role)).
		Str("permissions", strings.Join(perms, ",")).
		Int("user_count", len(req.UserIDList)).
		Int("group_count", len(req.GroupIDList)).
		Msg("batch add dataset member request received")
	created := make([]datasetMember, 0)
	seenMemberKeys := map[string]struct{}{}
	insertedUsers := 0
	updatedUsers := 0
	skippedUsers := 0
	failedUsers := 0
	insertedGroups := 0
	updatedGroups := 0
	skippedGroups := 0
	failedGroups := 0
	validUsers := 0
	validGroups := 0
	userNamesByID := buildNameMap(req.UserIDList, req.UserNameList)
	groupNamesByID := buildNameMap(req.GroupIDList, req.GroupNameList)
	appendMember := func(member datasetMember) {
		key := member.Name
		if key == "" {
			key = member.DatasetID + "|" + member.UserID + "|" + member.GroupID + "|" + member.Role.Role
		}
		if _, exists := seenMemberKeys[key]; exists {
			return
		}
		seenMemberKeys[key] = struct{}{}
		created = append(created, member)
	}
	userRows := st.ListACL(acl.ResourceTypeDB, datasetID, acl.GranteeUser)
	for _, raw := range req.UserIDList {
		uid := strings.TrimSpace(raw)
		if uid == "" {
			skippedUsers++
			log.Logger.Warn().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("request_user_id", requestUserID).
				Str("raw_user_id", raw).
				Msg("skip empty user id while batch adding dataset member")
			continue
		}
		validUsers++
		matchedBefore := false
		for _, row := range userRows {
			if row.GranteeID == uid {
				matchedBefore = true
				break
			}
		}
		ok := upsertDatasetMemberPermissions(st, datasetID, acl.GranteeUser, uid, perms, createdBy, userRows)
		if !ok {
			failedUsers++
			log.Logger.Error().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("request_user_id", requestUserID).
				Str("grantee_id", uid).
				Str("grantee_type", acl.GranteeUser).
				Str("permissions", strings.Join(perms, ",")).
				Msg("upsert dataset user acl failed")
			continue
		}
		if matchedBefore {
			updatedUsers++
			log.Logger.Info().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("request_user_id", requestUserID).
				Str("grantee_id", uid).
				Str("grantee_type", acl.GranteeUser).
				Str("permissions", strings.Join(perms, ",")).
				Msg("existing dataset user acl updated")
		} else {
			insertedUsers++
			log.Logger.Info().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("request_user_id", requestUserID).
				Str("grantee_id", uid).
				Str("grantee_type", acl.GranteeUser).
				Str("permissions", strings.Join(perms, ",")).
				Msg("dataset user acl added")
			userRows = refreshDatasetMemberRows(st, datasetID, acl.GranteeUser, userRows, uid)
		}
		if member, ok := getDatasetMemberByPrincipal(r, datasetID, acl.GranteeUser, uid); ok {
			if name := userNamesByID[uid]; name != "" {
				member.User = name
			}
			appendMember(member)
		} else {
			log.Logger.Warn().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("grantee_id", uid).
				Str("grantee_type", acl.GranteeUser).
				Msg("acl row upserted but member lookup failed")
		}
	}
	groupRows := st.ListACL(acl.ResourceTypeDB, datasetID, acl.GranteeGroup)
	for _, raw := range req.GroupIDList {
		gid := strings.TrimSpace(raw)
		if gid == "" {
			skippedGroups++
			log.Logger.Warn().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("request_user_id", requestUserID).
				Str("raw_group_id", raw).
				Msg("skip empty group id while batch adding dataset member")
			continue
		}
		validGroups++
		st.EnsureGroup(gid, "")
		matchedBefore := false
		for _, row := range groupRows {
			if row.GranteeID == gid {
				matchedBefore = true
				break
			}
		}
		ok := upsertDatasetMemberPermissions(st, datasetID, acl.GranteeGroup, gid, perms, createdBy, groupRows)
		if !ok {
			failedGroups++
			log.Logger.Error().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("request_user_id", requestUserID).
				Str("grantee_id", gid).
				Str("grantee_type", acl.GranteeGroup).
				Str("permissions", strings.Join(perms, ",")).
				Msg("upsert dataset group acl failed")
			continue
		}
		if matchedBefore {
			updatedGroups++
			log.Logger.Info().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("request_user_id", requestUserID).
				Str("grantee_id", gid).
				Str("grantee_type", acl.GranteeGroup).
				Str("permissions", strings.Join(perms, ",")).
				Msg("existing dataset group acl updated")
		} else {
			insertedGroups++
			log.Logger.Info().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("request_user_id", requestUserID).
				Str("grantee_id", gid).
				Str("grantee_type", acl.GranteeGroup).
				Str("permissions", strings.Join(perms, ",")).
				Msg("dataset group acl added")
			groupRows = refreshDatasetMemberRows(st, datasetID, acl.GranteeGroup, groupRows, gid)
		}
		if member, ok := getDatasetMemberByPrincipal(r, datasetID, acl.GranteeGroup, gid); ok {
			if name := groupNamesByID[gid]; name != "" {
				member.Group = name
			}
			appendMember(member)
		} else {
			log.Logger.Warn().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("grantee_id", gid).
				Str("grantee_type", acl.GranteeGroup).
				Msg("acl row upserted but group member lookup failed")
		}
	}
	if validUsers == 0 && validGroups == 0 {
		log.Logger.Warn().
			Str("handler", "BatchAddDatasetMember").
			Str("dataset_id", datasetID).
			Str("request_user_id", requestUserID).
			Int("skipped_users", skippedUsers).
			Int("skipped_groups", skippedGroups).
			Msg("batch add dataset member failed: no valid user/group ids provided")
		common.ReplyErr(w, "no valid user_id_list or group_id_list provided", http.StatusBadRequest)
		return
	}
	if insertedUsers == 0 && insertedGroups == 0 && updatedUsers == 0 && updatedGroups == 0 {
		log.Logger.Error().
			Str("handler", "BatchAddDatasetMember").
			Str("dataset_id", datasetID).
			Str("request_user_id", requestUserID).
			Str("permissions", strings.Join(perms, ",")).
			Int("valid_users", validUsers).
			Int("updated_users", updatedUsers).
			Int("failed_users", failedUsers).
			Int("valid_groups", validGroups).
			Int("updated_groups", updatedGroups).
			Int("failed_groups", failedGroups).
			Msg("batch add dataset member failed: no acl rows inserted or updated")
		common.ReplyErr(w, "failed to add dataset members", http.StatusInternalServerError)
		return
	}
	log.Logger.Info().
		Str("handler", "BatchAddDatasetMember").
		Str("dataset_id", datasetID).
		Str("request_user_id", requestUserID).
		Str("permissions", strings.Join(perms, ",")).
		Int("valid_users", validUsers).
		Int("inserted_users", insertedUsers).
		Int("updated_users", updatedUsers).
		Int("skipped_users", skippedUsers).
		Int("failed_users", failedUsers).
		Int("valid_groups", validGroups).
		Int("inserted_groups", insertedGroups).
		Int("updated_groups", updatedGroups).
		Int("skipped_groups", skippedGroups).
		Int("failed_groups", failedGroups).
		Int("created_members", len(created)).
		Msg("batch add dataset member finished")
	common.ReplyJSON(w, batchAddDatasetMemberResponse{DatasetMembers: created})
}

func listDatasetMembers(r *http.Request, datasetID, prefix string) []datasetMember {
	list := acl.GetStore().ListACL(acl.ResourceTypeDB, datasetID, "")
	out := buildDatasetMembers(r, datasetID, list)
	if prefix != "" {
		filtered := make([]datasetMember, 0, len(out))
		for _, member := range out {
			candidate := strings.ToLower(firstNonEmpty(member.User, member.Group, member.UserID, member.GroupID))
			if strings.Contains(candidate, strings.ToLower(prefix)) {
				filtered = append(filtered, member)
			}
		}
		return filtered
	}
	return out
}

func getDatasetMemberByUserID(r *http.Request, datasetID, userID string) (datasetMember, bool) {
	return getDatasetMemberByPrincipal(r, datasetID, acl.GranteeUser, userID)
}

func getDatasetMemberByPrincipal(r *http.Request, datasetID, granteeType, principalID string) (datasetMember, bool) {
	rows := acl.GetStore().ListACL(acl.ResourceTypeDB, datasetID, granteeType)
	members := buildDatasetMembers(r, datasetID, rows)
	for _, member := range members {
		if granteeType == acl.GranteeUser && member.UserID == principalID {
			return member, true
		}
		if (granteeType == acl.GranteeGroup || granteeType == acl.GranteeTenant) && member.GroupID == principalID {
			return member, true
		}
	}
	return datasetMember{}, false
}

func buildDatasetMembers(r *http.Request, datasetID string, rows []acl.ACLListItem) []datasetMember {
	ds, _ := loadDatasetByID(requestContext(r), datasetID)
	type principalKey struct {
		granteeType string
		granteeID   string
	}
	aggregated := make(map[principalKey]datasetMember, len(rows)+1)
	for _, row := range rows {
		member, ok := datasetMemberFromACL(datasetID, row)
		if !ok {
			continue
		}
		key := principalKey{granteeType: normalizeDatasetGranteeType(row.GranteeType), granteeID: row.GranteeID}
		if existing, exists := aggregated[key]; exists {
			if compareDatasetPermissionPriority(member.Role.Role, existing.Role.Role) > 0 {
				existing.Role = member.Role
			}
			if existing.CreateTime == "" || (member.CreateTime != "" && member.CreateTime < existing.CreateTime) {
				existing.CreateTime = member.CreateTime
			}
			aggregated[key] = existing
			continue
		}
		aggregated[key] = member
	}
	if ds != nil && strings.TrimSpace(ds.CreateUserID) != "" {
		key := principalKey{granteeType: acl.GranteeUser, granteeID: strings.TrimSpace(ds.CreateUserID)}
		creator, exists := aggregated[key]
		if !exists {
			creator = datasetMember{
				Name:      "datasets/" + datasetID + "/members/" + strings.TrimSpace(ds.CreateUserID),
				DatasetID: datasetID,
				UserID:    strings.TrimSpace(ds.CreateUserID),
				User:      strings.TrimSpace(ds.CreateUserName),
				Role: datasetRole{
					Role:        "dataset_maintainer",
					DisplayName: "管理者",
				},
			}
			if !ds.CreatedAt.IsZero() {
				creator.CreateTime = ds.CreatedAt.UTC().Format(time.RFC3339)
			}
		}
		creator.IsCreator = true
		creator.Role = datasetRole{Role: "dataset_maintainer", DisplayName: "管理者"}
		if creator.User == "" {
			creator.User = strings.TrimSpace(ds.CreateUserName)
		}
		aggregated[key] = creator
	}
	out := make([]datasetMember, 0, len(aggregated))
	for _, member := range aggregated {
		out = append(out, member)
	}
	out = fillDatasetMemberNames(r, out)
	sort.SliceStable(out, func(i, j int) bool {
		if out[i].IsCreator != out[j].IsCreator {
			return out[i].IsCreator
		}
		if c := compareDatasetPermissionPriority(out[i].Role.Role, out[j].Role.Role); c != 0 {
			return c > 0
		}
		return firstNonEmpty(out[i].UserID, out[i].GroupID) < firstNonEmpty(out[j].UserID, out[j].GroupID)
	})
	return out
}

func datasetMemberFromACL(datasetID string, row acl.ACLListItem) (datasetMember, bool) {
	roleName, displayName := permissionToRole(row.Permission)
	if roleName == "" {
		return datasetMember{}, false
	}
	member := datasetMember{
		DatasetID: datasetID,
		Role: datasetRole{
			Role:        roleName,
			DisplayName: displayName,
		},
		CreateTime: row.CreatedAt.UTC().Format(time.RFC3339),
	}
	switch normalizeDatasetGranteeType(row.GranteeType) {
	case acl.GranteeUser:
		member.UserID = row.GranteeID
		member.User = member.UserID
		member.Name = "datasets/" + datasetID + "/members/" + row.GranteeID
	case acl.GranteeGroup:
		member.GroupID = row.GranteeID
		member.Group = member.GroupID
		member.Name = "datasets/" + datasetID + "/members/groups/" + row.GranteeID
	default:
		return datasetMember{}, false
	}
	return member, true
}

func normalizeDatasetGranteeType(granteeType string) string {
	switch granteeType {
	case acl.GranteeTenant:
		return acl.GranteeGroup
	default:
		return granteeType
	}
}

func compareDatasetPermissionPriority(leftRole, rightRole string) int {
	priority := func(role string) int {
		switch strings.TrimSpace(role) {
		case "dataset_owner":
			return 4
		case "dataset_maintainer":
			return 3
		case "dataset_uploader":
			return 2
		case "dataset_user":
			return 1
		default:
			return 0
		}
	}
	return priority(leftRole) - priority(rightRole)
}

func loadDatasetByID(ctx context.Context, datasetID string) (*orm.Dataset, bool) {
	datasetID = strings.TrimSpace(datasetID)
	if datasetID == "" || store.DB() == nil {
		return nil, false
	}
	var ds orm.Dataset
	if err := store.DB().WithContext(ctx).Where("id = ? AND deleted_at IS NULL", datasetID).First(&ds).Error; err != nil {
		return nil, false
	}
	return &ds, true
}

func ensureDatasetCreatorMember(st *acl.Store, datasetID, creatorUserID string) {
	if st == nil {
		return
	}
	creatorUserID = strings.TrimSpace(creatorUserID)
	datasetID = strings.TrimSpace(datasetID)
	if datasetID == "" || creatorUserID == "" {
		return
	}
	rows := st.ListACL(acl.ResourceTypeDB, datasetID, acl.GranteeUser)
	var creatorRows []acl.ACLListItem
	for _, row := range rows {
		if row.GranteeID == creatorUserID {
			creatorRows = append(creatorRows, row)
		}
	}
	upsertDatasetMemberPermissions(st, datasetID, acl.GranteeUser, creatorUserID, roleToPermissions("dataset_maintainer"), creatorUserID, creatorRows)
}

func upsertDatasetMemberPermissions(st *acl.Store, datasetID, granteeType, principalID string, permissions []string, createdBy string, rows []acl.ACLListItem) bool {
	if st == nil {
		return false
	}
	principalID = strings.TrimSpace(principalID)
	if principalID == "" || len(permissions) == 0 {
		return false
	}
	wanted := map[string]struct{}{}
	for _, permission := range permissions {
		permission = strings.TrimSpace(permission)
		if permission == "" {
			continue
		}
		wanted[permission] = struct{}{}
	}
	if len(wanted) == 0 {
		return false
	}
	var matched []acl.ACLListItem
	for _, row := range rows {
		if row.GranteeID == principalID {
			matched = append(matched, row)
		}
	}
	for _, row := range matched {
		if _, ok := wanted[row.Permission]; ok {
			delete(wanted, row.Permission)
			continue
		}
		st.DeleteACL(row.ID)
	}
	for permission := range wanted {
		aclID := st.AddACL(acl.ResourceTypeDB, datasetID, granteeType, principalID, permission, createdBy, nil)
		if aclID == 0 {
			return false
		}
	}
	return true
}

func buildNameMap(ids, names []string) map[string]string {
	m := make(map[string]string, len(ids))
	for i, rawID := range ids {
		id := strings.TrimSpace(rawID)
		if id == "" {
			continue
		}
		if i >= len(names) {
			continue
		}
		name := strings.TrimSpace(names[i])
		if name == "" {
			continue
		}
		m[id] = name
	}
	return m
}

func fillDatasetMemberNames(r *http.Request, members []datasetMember) []datasetMember {
	if len(members) == 0 {
		return members
	}
	userNameMap, groupNameMap := fetchDatasetMemberNames(r, members)
	for i := range members {
		if members[i].UserID != "" {
			if name := userNameMap[members[i].UserID]; name != "" {
				members[i].User = name
			}
		}
		if members[i].GroupID != "" {
			if name := groupNameMap[members[i].GroupID]; name != "" {
				members[i].Group = name
			}
		}
	}
	return members
}

func fetchDatasetMemberNames(r *http.Request, members []datasetMember) (map[string]string, map[string]string) {
	userIDs := make([]string, 0)
	groupIDs := make([]string, 0)
	userSeen := map[string]struct{}{}
	groupSeen := map[string]struct{}{}
	for _, member := range members {
		if member.UserID != "" {
			if _, ok := userSeen[member.UserID]; !ok {
				userSeen[member.UserID] = struct{}{}
				userIDs = append(userIDs, member.UserID)
			}
		}
		if member.GroupID != "" {
			if _, ok := groupSeen[member.GroupID]; !ok {
				groupSeen[member.GroupID] = struct{}{}
				groupIDs = append(groupIDs, member.GroupID)
			}
		}
	}
	return fetchUserNames(r, userIDs), fetchGroupNames(r, groupIDs)
}

func fetchUserNames(r *http.Request, userIDs []string) map[string]string {
	out := map[string]string{}
	for _, userID := range userIDs {
		userID = strings.TrimSpace(userID)
		if userID == "" {
			continue
		}
		var resp struct {
			Code    int    `json:"code"`
			Message string `json:"message"`
			Data    struct {
				UserID      string `json:"user_id"`
				Username    string `json:"username"`
				DisplayName string `json:"display_name"`
			} `json:"data"`
			// auth-service may return the object directly (not wrapped by "data").
			UserID      string `json:"user_id"`
			Username    string `json:"username"`
			DisplayName string `json:"display_name"`
		}
		if err := common.ApiGet(requestContext(r), authServiceBaseURL()+"/user/"+url.PathEscape(userID), authRequestHeaders(r), &resp, 3*time.Second); err != nil {
			continue
		}
		// Support both response formats: top-level fields or "data" wrapper.
		name := strings.TrimSpace(firstNonEmpty(resp.DisplayName, resp.Username, resp.Data.DisplayName, resp.Data.Username))
		if name != "" {
			out[userID] = name
		}
	}
	return out
}

func fetchGroupNames(r *http.Request, groupIDs []string) map[string]string {
	out := map[string]string{}
	for _, groupID := range groupIDs {
		groupID = strings.TrimSpace(groupID)
		if groupID == "" {
			continue
		}
		var resp struct {
			Code    int    `json:"code"`
			Message string `json:"message"`
			Data    struct {
				GroupID   string `json:"group_id"`
				GroupName string `json:"group_name"`
			} `json:"data"`
			// auth-service may return the object directly (not wrapped by "data").
			GroupID   string `json:"group_id"`
			GroupName string `json:"group_name"`
		}
		if err := common.ApiGet(requestContext(r), authServiceBaseURL()+"/group/"+url.PathEscape(groupID), authRequestHeaders(r), &resp, 3*time.Second); err != nil {
			continue
		}
		// Support both response formats: top-level fields or "data" wrapper.
		name := strings.TrimSpace(firstNonEmpty(resp.GroupName, resp.Data.GroupName))
		if name != "" {
			out[groupID] = name
		}
	}
	return out
}

func authServiceBaseURL() string {
	if u := strings.TrimSpace(os.Getenv("LAZYRAG_AUTH_SERVICE_URL")); u != "" {
		base := strings.TrimRight(u, "/")
		if strings.HasSuffix(base, "/api/authservice") {
			return base
		}
		return base + "/api/authservice"
	}
	return "http://auth-service:8000/api/authservice"
}

func authRequestHeaders(r *http.Request) map[string]string {
	headers := map[string]string{}
	if r == nil {
		return headers
	}
	if v := strings.TrimSpace(r.Header.Get("Authorization")); v != "" {
		headers["Authorization"] = v
	}
	if v := strings.TrimSpace(r.Header.Get("X-User-Id")); v != "" {
		headers["X-User-Id"] = v
	}
	if v := strings.TrimSpace(r.Header.Get("X-User-Name")); v != "" {
		headers["X-User-Name"] = v
	}
	return headers
}

func requestContext(r *http.Request) context.Context {
	if r != nil {
		return r.Context()
	}
	return context.Background()
}

func roleToPermissions(role string) []string {
	switch strings.TrimSpace(role) {
	case "dataset_user":
		return []string{acl.PermissionDatasetRead}
	case "dataset_uploader":
		return []string{acl.PermissionDatasetUpload}
	case "dataset_maintainer", "dataset_owner":
		return []string{acl.PermissionDatasetRead, acl.PermissionDatasetUpload, acl.PermissionDatasetWrite}
	default:
		return nil
	}
}

func permissionToRole(permission string) (string, string) {
	switch strings.TrimSpace(permission) {
	case acl.PermissionDatasetRead:
		return "dataset_user", "只读者"
	case acl.PermissionDatasetUpload:
		return "dataset_uploader", "上传者"
	case acl.PermissionDatasetWrite:
		return "dataset_maintainer", "管理者"
	default:
		return "", ""
	}
}

func refreshDatasetMemberRows(st *acl.Store, datasetID, granteeType string, rows []acl.ACLListItem, principalID string) []acl.ACLListItem {
	if st == nil {
		return rows
	}
	principalID = strings.TrimSpace(principalID)
	filtered := rows[:0]
	for _, row := range rows {
		if row.GranteeID != principalID {
			filtered = append(filtered, row)
		}
	}
	for _, row := range st.ListACL(acl.ResourceTypeDB, datasetID, granteeType) {
		if row.GranteeID == principalID {
			filtered = append(filtered, row)
		}
	}
	return filtered
}

func formatACLIDs(ids []int64) string {
	if len(ids) == 0 {
		return ""
	}
	parts := make([]string, 0, len(ids))
	for _, id := range ids {
		if id == 0 {
			continue
		}
		parts = append(parts, fmt.Sprintf("%d", id))
	}
	return strings.Join(parts, ",")
}
