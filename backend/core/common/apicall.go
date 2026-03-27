package common

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// ApiGet 统一封装外部 HTTP GET(JSON) 调用。
func ApiGet(ctx context.Context, url string, header map[string]string, response any, timeout time.Duration) error {
	return do(ctx, url, http.MethodGet, nil, header, response, timeout)
}

// ApiPost 统一封装外部 HTTP POST(JSON) 调用。
func ApiPost(ctx context.Context, url string, body any, header map[string]string, response any, timeout time.Duration) error {
	return do(ctx, url, http.MethodPost, body, header, response, timeout)
}

// ApiDelete 统一封装外部 HTTP DELETE(JSON) 调用。
func ApiDelete(ctx context.Context, url string, header map[string]string, response any, timeout time.Duration) error {
	return do(ctx, url, http.MethodDelete, nil, header, response, timeout)
}

func do(ctx context.Context, url, method string, body any, header map[string]string, response any, timeout time.Duration) error {
	var reqBody io.Reader = http.NoBody
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return fmt.Errorf("marshal body: %w", err)
		}
		reqBody = bytes.NewReader(b)
	}

	req, err := http.NewRequestWithContext(ctx, method, url, reqBody)
	if err != nil {
		return fmt.Errorf("new request: %w", err)
	}
	for k, v := range header {
		req.Header.Set(k, v)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}

	cli := &http.Client{Timeout: timeout}
	resp, err := cli.Do(req)
	if err != nil {
		return fmt.Errorf("do request: %w", err)
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("read response: %w", err)
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("http %d: %s", resp.StatusCode, string(respBytes))
	}
	if response == nil {
		return nil
	}
	if len(respBytes) == 0 {
		return nil
	}
	if err := json.Unmarshal(respBytes, response); err != nil {
		return fmt.Errorf("unmarshal response: %w", err)
	}
	return nil
}

