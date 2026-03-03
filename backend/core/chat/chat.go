package chat

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"

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

// extractChatACL extracts (userID, kbID, needPerm) from chat request for proxy's ACL check.
// Proxy will call acl.Can(userID, kbID, needPerm). Returns empty needPerm to deny.
func extractChatACL(r *http.Request, body []byte) (userID, kbID int64, needPerm string) {
	if s := r.Header.Get("X-User-Id"); s != "" {
		userID, _ = strconv.ParseInt(s, 10, 64)
	}
	if len(body) > 0 {
		var m map[string]any
		if json.Unmarshal(body, &m) == nil {
			if v, ok := m["kb_id"]; ok {
				kbID = toInt64(v)
			}
			if kbID == 0 {
				if v, ok := m["dataset_id"]; ok {
					kbID = toInt64(v)
				}
			}
		}
	}
	if kbID == 0 {
		return userID, kbID, ""
	}
	return userID, kbID, "read"
}

func toInt64(v any) int64 {
	switch x := v.(type) {
	case float64:
		return int64(x)
	case int:
		return int64(x)
	case int64:
		return x
	case string:
		n, _ := strconv.ParseInt(x, 10, 64)
		return n
	default:
		return 0
	}
}

// Chat forwards POST /api/chat to the Python service after ACL check (read on kb_id/dataset_id).
var Chat = common.ProxyWithACL(chatServiceURL()+"/api/chat", 0, extractChatACL)

// ChatStream forwards POST /api/chat/stream to the Python service and flushes
// every chunk immediately; guarded by same ACL check.
var ChatStream = common.ProxyWithACL(chatServiceURL()+"/api/chat/stream", -1, extractChatACL)
