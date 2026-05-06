package algo

import (
	"context"
	"fmt"
	"strings"
	"time"

	"lazyrag/core/common"
)

const generateTimeout = 10 * time.Minute

func GenerateSkill(ctx context.Context, req SkillGenerateRequest) (string, error) {
	return generate(ctx, "/api/chat/skill/generate", req)
}

func GenerateMemory(ctx context.Context, req MemoryGenerateRequest) (string, error) {
	return generate(ctx, "/api/chat/memory/generate", req)
}

func GenerateUserPreference(ctx context.Context, req MemoryGenerateRequest) (string, error) {
	return generate(ctx, "/api/chat/user_preference/generate", req)
}

func generateURL(path string) string {
	return common.ChatServiceEndpoint() + path
}

func generate(ctx context.Context, path string, req any) (string, error) {
	url := generateURL(path)
	var response map[string]any
	if err := common.ApiPost(ctx, url, req, nil, &response, generateTimeout); err != nil {
		return "", err
	}
	content := extractGeneratedContent(response)
	if strings.TrimSpace(content) == "" {
		return "", fmt.Errorf("generate endpoint returned empty content")
	}
	return content, nil
}

func extractGeneratedContent(payload any) string {
	switch typed := payload.(type) {
	case map[string]any:
		if data, ok := typed["data"]; ok {
			if s := extractGeneratedContent(data); strings.TrimSpace(s) != "" {
				return strings.TrimSpace(s)
			}
		}
		for _, key := range []string{"content", "text", "result", "generated_content", "full_content"} {
			if value, ok := typed[key]; ok {
				if s := extractGeneratedContent(value); strings.TrimSpace(s) != "" {
					return strings.TrimSpace(s)
				}
			}
		}
	case string:
		return strings.TrimSpace(typed)
	}
	return ""
}
