package chat

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"

	"lazyrag/core/acl"
	"lazyrag/core/common"
)

// chatServiceURL returns the base URL of the Python chat service.
// Override with env LAZYRAG_CHAT_SERVICE_URL (default: http://localhost:8046).
func chatServiceURL() string {
	if u := os.Getenv("LAZYRAG_CHAT_SERVICE_URL"); u != "" {
		return u
	}
	return "http://localhost:8046"
}

// extractMessageForACL extracts (userID, items) from chat request for proxy's ACL check.
// - kb_id only: items = [{ResourceType: "kb", ResourceID: kb_id, NeedPerm: "read"}]
// - dataset_id only: items = [{ResourceType: "db", ResourceID: dataset_id, NeedPerm: "read"}]
// - both: items = both entries, both must pass
// - neither: items = nil, skip auth
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
	kbID := ""
	datasetID := ""
	if v, ok := m["kb_id"]; ok {
		kbID = toString(v)
	}
	if v, ok := m["dataset_id"]; ok {
		datasetID = toString(v)
	}
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

// Chat forwards POST /api/chat to the Python service after ACL check (read on kb_id/dataset_id).
var Chat = common.ProxyWithACL(chatServiceURL()+"/api/chat", 0, extractMessageForACL)

// ChatStream forwards POST /api/chat/stream to the Python service and flushes
// every chunk immediately; guarded by same ACL check.
var ChatStream = common.ProxyWithACL(chatServiceURL()+"/api/chat/stream", -1, extractMessageForACL)
