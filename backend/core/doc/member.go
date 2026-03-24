package doc

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"lazyrag/core/acl"
	"lazyrag/core/common"
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
	memberName := datasetMemberNameFromPath(r)
	if datasetID == "" || memberName == "" {
		common.ReplyErr(w, "invalid path", http.StatusBadRequest)
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
	granteeType, targetID, err := parseDatasetMemberRef(memberName)
	if err != nil {
		common.ReplyErr(w, "invalid member", http.StatusBadRequest)
		return
	}
	member, ok := getDatasetMemberByRef(r, datasetID, granteeType, targetID)
	if !ok {
		common.ReplyErr(w, "member not found", http.StatusNotFound)
		return
	}
	common.ReplyJSON(w, member)
}

func DeleteDatasetMember(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	memberName := datasetMemberNameFromPath(r)
	if datasetID == "" || memberName == "" {
		common.ReplyErr(w, "invalid path", http.StatusBadRequest)
		return
	}
	if _, _, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetWrite); !ok {
		replyDatasetForbidden(w)
		return
	}
	granteeType, targetID, err := parseDatasetMemberRef(memberName)
	if err != nil {
		common.ReplyErr(w, "invalid member", http.StatusBadRequest)
		return
	}
	rows := acl.GetStore().ListACL(acl.ResourceTypeDB, datasetID, granteeType)
	deleted := false
	for _, row := range rows {
		if row.GranteeID == targetID {
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

func UpdateDatasetMember(w http.ResponseWriter, r *http.Request) {
	datasetID := datasetIDFromPath(r)
	memberName := datasetMemberNameFromPath(r)
	if datasetID == "" || memberName == "" {
		common.ReplyErr(w, "invalid path", http.StatusBadRequest)
		return
	}
	if _, _, ok := requireDatasetPermission(r, datasetID, acl.PermissionDatasetWrite); !ok {
		replyDatasetForbidden(w)
		return
	}
	var req updateDatasetMemberRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	granteeType, targetID, err := parseDatasetMemberRef(memberName)
	if err != nil {
		common.ReplyErr(w, "invalid member", http.StatusBadRequest)
		return
	}
	perm := roleToPermission(req.DatasetMember.Role.Role)
	if perm == "" {
		common.ReplyErr(w, "invalid role", http.StatusBadRequest)
		return
	}
	rows := acl.GetStore().ListACL(acl.ResourceTypeDB, datasetID, granteeType)
	updated := false
	for _, row := range rows {
		if row.GranteeID == targetID {
			if !acl.GetStore().UpdateACL(row.ID, perm, nil) {
				common.ReplyErr(w, "update failed", http.StatusInternalServerError)
				return
			}
			updated = true
			break
		}
	}
	if !updated {
		common.ReplyErr(w, "member not found", http.StatusNotFound)
		return
	}
	member, ok := getDatasetMemberByRef(r, datasetID, granteeType, targetID)
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
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	perm := roleToPermission(req.Role.Role)
	if perm == "" {
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
		Str("permission", perm).
		Int("user_count", len(req.UserIDList)).
		Int("group_count", len(req.GroupIDList)).
		Msg("batch add dataset member request received")
	created := make([]datasetMember, 0)
	insertedUsers := 0
	skippedUsers := 0
	failedUsers := 0
	insertedGroups := 0
	skippedGroups := 0
	failedGroups := 0
	validUsers := 0
	validGroups := 0
	userNamesByID := buildNameMap(req.UserIDList, req.UserNameList)
	groupNamesByID := buildNameMap(req.GroupIDList, req.GroupNameList)
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
		aclID := st.AddACL(acl.ResourceTypeDB, datasetID, acl.GranteeUser, uid, perm, createdBy, nil)
		if aclID == 0 {
			failedUsers++
			log.Logger.Error().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("request_user_id", requestUserID).
				Str("grantee_id", uid).
				Str("grantee_type", acl.GranteeUser).
				Str("permission", perm).
				Msg("add acl for dataset user returned zero id")
			continue
		}
		insertedUsers++
		log.Logger.Info().
			Str("handler", "BatchAddDatasetMember").
			Str("dataset_id", datasetID).
			Str("request_user_id", requestUserID).
			Int64("acl_id", aclID).
			Str("grantee_id", uid).
			Str("grantee_type", acl.GranteeUser).
			Str("permission", perm).
			Msg("dataset user acl added")
		if member, ok := getDatasetMemberByRef(r, datasetID, acl.GranteeUser, uid); ok {
			if name := userNamesByID[uid]; name != "" {
				member.User = name
			}
			created = append(created, member)
		} else {
			log.Logger.Warn().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("grantee_id", uid).
				Str("grantee_type", acl.GranteeUser).
				Msg("acl row inserted but member lookup failed")
		}
	}
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
		aclID := st.AddACL(acl.ResourceTypeDB, datasetID, acl.GranteeGroup, gid, perm, createdBy, nil)
		if aclID == 0 {
			failedGroups++
			log.Logger.Error().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("request_user_id", requestUserID).
				Str("grantee_id", gid).
				Str("grantee_type", acl.GranteeGroup).
				Str("permission", perm).
				Msg("add acl for dataset group returned zero id")
			continue
		}
		insertedGroups++
		log.Logger.Info().
			Str("handler", "BatchAddDatasetMember").
			Str("dataset_id", datasetID).
			Str("request_user_id", requestUserID).
			Int64("acl_id", aclID).
			Str("grantee_id", gid).
			Str("grantee_type", acl.GranteeGroup).
			Str("permission", perm).
			Msg("dataset group acl added")
		if member, ok := getDatasetMemberByRef(r, datasetID, acl.GranteeGroup, gid); ok {
			if name := groupNamesByID[gid]; name != "" {
				member.Group = name
			}
			created = append(created, member)
		} else {
			log.Logger.Warn().
				Str("handler", "BatchAddDatasetMember").
				Str("dataset_id", datasetID).
				Str("grantee_id", gid).
				Str("grantee_type", acl.GranteeGroup).
				Msg("acl row inserted but group member lookup failed")
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
	if insertedUsers == 0 && insertedGroups == 0 {
		log.Logger.Error().
			Str("handler", "BatchAddDatasetMember").
			Str("dataset_id", datasetID).
			Str("request_user_id", requestUserID).
			Str("permission", perm).
			Int("valid_users", validUsers).
			Int("failed_users", failedUsers).
			Int("valid_groups", validGroups).
			Int("failed_groups", failedGroups).
			Msg("batch add dataset member failed: no acl rows inserted")
		common.ReplyErr(w, "failed to add dataset members", http.StatusInternalServerError)
		return
	}
	log.Logger.Info().
		Str("handler", "BatchAddDatasetMember").
		Str("dataset_id", datasetID).
		Str("request_user_id", requestUserID).
		Str("permission", perm).
		Int("valid_users", validUsers).
		Int("inserted_users", insertedUsers).
		Int("skipped_users", skippedUsers).
		Int("failed_users", failedUsers).
		Int("valid_groups", validGroups).
		Int("inserted_groups", insertedGroups).
		Int("skipped_groups", skippedGroups).
		Int("failed_groups", failedGroups).
		Int("created_members", len(created)).
		Msg("batch add dataset member finished")
	common.ReplyJSON(w, batchAddDatasetMemberResponse{DatasetMembers: created})
}

func listDatasetMembers(r *http.Request, datasetID, prefix string) []datasetMember {
	list := acl.GetStore().ListACL(acl.ResourceTypeDB, datasetID, "")
	out := make([]datasetMember, 0, len(list))
	for _, row := range list {
		member, ok := datasetMemberFromACL(datasetID, row)
		if !ok {
			continue
		}
		out = append(out, member)
	}
	out = fillDatasetMemberNames(r, out)
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

func getDatasetMemberByRef(r *http.Request, datasetID, granteeType string, targetID string) (datasetMember, bool) {
	rows := acl.GetStore().ListACL(acl.ResourceTypeDB, datasetID, granteeType)
	for _, row := range rows {
		if row.GranteeID == targetID {
			member, ok := datasetMemberFromACL(datasetID, row)
			if !ok {
				return datasetMember{}, false
			}
			members := fillDatasetMemberNames(r, []datasetMember{member})
			if len(members) == 0 {
				return datasetMember{}, false
			}
			return members[0], true
		}
	}
	return datasetMember{}, false
}

func datasetMemberFromACL(datasetID string, row acl.ACLListItem) (datasetMember, bool) {
	roleName, displayName := permissionToRole(row.Permission)
	if roleName == "" {
		return datasetMember{}, false
	}
	member := datasetMember{
		Name:      encodeDatasetMemberName(datasetID, row.GranteeType, row.GranteeID, roleName),
		DatasetID: datasetID,
		Role: datasetRole{
			Role:        roleName,
			DisplayName: displayName,
		},
		CreateTime: row.CreatedAt.UTC().Format(time.RFC3339),
	}
	switch row.GranteeType {
	case acl.GranteeUser:
		member.UserID = row.GranteeID
		member.User = member.UserID
	case acl.GranteeGroup, acl.GranteeTenant:
		member.GroupID = row.GranteeID
		member.Group = member.GroupID
	}
	return member, true
}

func encodeDatasetMemberName(datasetID, granteeType string, targetID string, role string) string {
	return "datasets/" + datasetID + "/members/type/" + granteeType + "/id/" + targetID + "/role/" + role
}

func parseDatasetMemberRef(member string) (string, string, error) {
	parts := strings.Split(strings.Trim(member, "/"), "/")
	if len(parts) < 8 {
		return "", "", fmt.Errorf("invalid member ref")
	}
	granteeType := strings.TrimSpace(parts[len(parts)-5])
	if granteeType != acl.GranteeUser && granteeType != acl.GranteeGroup && granteeType != acl.GranteeTenant {
		return "", "", fmt.Errorf("invalid grantee_type")
	}
	targetID := strings.TrimSpace(parts[len(parts)-3])
	if targetID == "" {
		return "", "", fmt.Errorf("empty target id")
	}
	return granteeType, targetID, nil
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
			UserID      string `json:"user_id"`
			Username    string `json:"username"`
			DisplayName string `json:"display_name"`
		}
		if err := common.ApiGet(requestContext(r), authServiceBaseURL()+"/user/"+url.PathEscape(userID), authRequestHeaders(r), &resp, 3*time.Second); err != nil {
			continue
		}
		name := strings.TrimSpace(firstNonEmpty(resp.DisplayName, resp.Username))
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
			GroupID   string `json:"group_id"`
			GroupName string `json:"group_name"`
		}
		if err := common.ApiGet(requestContext(r), authServiceBaseURL()+"/group/"+url.PathEscape(groupID), authRequestHeaders(r), &resp, 3*time.Second); err != nil {
			continue
		}
		name := strings.TrimSpace(resp.GroupName)
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

func roleToPermission(role string) string {
	switch strings.TrimSpace(role) {
	case "dataset_user":
		return acl.PermissionDatasetRead
	case "dataset_uploader":
		return acl.PermissionDatasetUpload
	case "dataset_maintainer", "dataset_owner":
		return acl.PermissionDatasetWrite
	default:
		return ""
	}
}

func permissionToRole(permission string) (string, string) {
	switch strings.TrimSpace(permission) {
	case acl.PermissionDatasetRead:
		return "dataset_user", "只读者"
	case acl.PermissionDatasetUpload:
		return "dataset_uploader", "上传者"
	case acl.PermissionDatasetWrite:
		return "dataset_maintainer", "维护者"
	default:
		return "", ""
	}
}
