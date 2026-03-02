package chat

import (
	"os"

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

// Chat forwards POST /api/chat to the Python service and returns the result.
var Chat = common.Proxy(chatServiceURL()+"/api/chat", 0)

// ChatStream forwards POST /api/chat/stream to the Python service and flushes
// every chunk immediately so the client receives tokens as they arrive.
var ChatStream = common.Proxy(chatServiceURL()+"/api/chat/stream", -1)
