package common

import (
	"bytes"
	"context"
	"io"
	"net/http"
	"time"
)

const (
	// defaultHTTPTimeout 与上游对话服务的默认超时时间保持一致级别，避免长对话被过早取消。
	defaultHTTPTimeout = 10 * time.Minute
)

// HTTPPost 统一封装外部 POST 调用。
// - ctx 允许调用方控制超时/取消；为 nil 时使用 context.Background。
// - contentType 一般为 "application/json"。
// 返回响应 body、HTTP 状态码以及 error（仅在网络/构造/读 body 失败时返回 error）。
func HTTPPost(ctx context.Context, url, contentType string, body []byte) ([]byte, int, error) {
	if ctx == nil {
		ctx = context.Background()
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, 0, err
	}
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}

	client := &http.Client{
		Timeout: defaultHTTPTimeout,
	}

	resp, err := client.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, resp.StatusCode, err
	}
	return respBytes, resp.StatusCode, nil
}

