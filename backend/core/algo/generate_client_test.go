package algo

import "testing"

func TestGenerateURLUsesChatServiceEndpoint(t *testing.T) {
	t.Setenv("LAZYRAG_ALGO_SERVICE_URL", "http://algo-service.invalid")
	t.Setenv("LAZYRAG_CHAT_SERVICE_URL", "http://chat-service:8046")

	got := generateURL("/api/chat/memory/generate")
	want := "http://chat-service:8046/api/chat/memory/generate"
	if got != want {
		t.Fatalf("expected generate URL %q, got %q", want, got)
	}
}
