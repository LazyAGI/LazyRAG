package chat

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"

	"lazyrag/core/acl"
	"lazyrag/core/common"
)

func chatServiceURL() string {
	if u := os.Getenv("LAZYRAG_CHAT_SERVICE_URL"); u != "" {
		return u
	}
	return "http://localhost:8048"
}

func extractMessageForACL(r *http.Request, body []byte) (userID int64, items []common.ACLCheckItem) {
	if s := r.Header.Get("X-User-Id"); s != "" {
		userID, _ = strconv.ParseInt(s, 10, 64)
	}
	if len(body) == 0 {
		return userID, nil
	}
	var m map[string]any
	if json.Unmarshal(body, &m) != nil {
		return userID, nil
	}
	kbID := toString(m["kb_id"])
	datasetID := toString(m["dataset_id"])

	if kbID == "" && datasetID == "" {
		return userID, nil
	}
	if kbID != "" && datasetID != "" {
		return userID, []common.ACLCheckItem{
			{ResourceType: acl.ResourceTypeKB, ResourceID: kbID, NeedPerm: "read"},
			{ResourceType: acl.ResourceTypeDB, ResourceID: datasetID, NeedPerm: "read"},
		}
	}
	if kbID != "" {
		return userID, []common.ACLCheckItem{
			{ResourceType: acl.ResourceTypeKB, ResourceID: kbID, NeedPerm: "read"},
		}
	}
	return userID, []common.ACLCheckItem{
		{ResourceType: acl.ResourceTypeDB, ResourceID: datasetID, NeedPerm: "read"},
	}
}

func toString(v any) string {
	switch x := v.(type) {
	case string:
		return x
	case float64:
		return strconv.FormatFloat(x, 'f', -1, 64)
	case int:
		return strconv.Itoa(x)
	case int64:
		return strconv.FormatInt(x, 10)
	default:
		return ""
	}
}

