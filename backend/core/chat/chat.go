// chat 提供对上游 /api/chat 和 /api/chat_stream 的调用能力，
// 与 neutrino external/chat.go 的 ChatService 行为保持高度一致。
package chat

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"strings"
	"time"
)

const (
	chatPath       = "/api/chat"
	streamChatPath = "/api/chat_stream"

	defaultDialTimeout  = 10 * time.Second
	defaultTotalTimeout = 10 * time.Minute
	defaultTTFB         = 3 * time.Minute
)

// ChatMessage 与 neutrino external.ChatMessage 对齐。
type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// DatasetFilters 与 neutrino external.DatasetFilters 对齐（仅保留当前需要的字段）。
type DatasetFilters struct {
	Subject    []string `json:"subject,omitempty"`
	DatasetIDs []string `json:"kb_id,omitempty"`
	Tags       []string `json:"tags,omitempty"`
	Creators   []string `json:"creator,omitempty"`
}

// LazyChatRequest 与 neutrino external.LazyChatRequest 对齐，用于 /api/chat 与 /api/chat_stream。
type LazyChatRequest struct {
	Query          string          `json:"query"`
	History        []ChatMessage   `json:"history,omitempty"`
	SessionID      string          `json:"session_id"`
	Files          []string        `json:"files,omitempty"`
	Filters        *DatasetFilters `json:"filters"`
	Databases      []any           `json:"databases,omitempty"`
	EnableThinking bool            `json:"enable_thinking,omitempty"`
}

// LazyChatData 与外部返回的 data 区域字段对齐。
type LazyChatData struct {
	Text          string `json:"text"`
	Sources       []any  `json:"sources"`
	Status        string `json:"status"`
	ReasoningText string `json:"think"`
}

// LazyChatResponse 对应一次性 /api/chat 的响应。
type LazyChatResponse struct {
	Code int          `json:"code"`
	Msg  string       `json:"msg"`
	Data LazyChatData `json:"data"`
	Cost float64      `json:"cost"`
}

// LazyStreamData 对应 /api/chat_stream 每一行解析后的结构。
type LazyStreamData struct {
	RawText string
	Resp    *LazyChatResponse
}

// ChatService 封装对上游对话服务的访问（/api/chat 与 /api/chat_stream）。
type ChatService struct {
	chatURL       string
	streamChatURL string
	client        *http.Client
}

// NewChatServiceWithEndpoint 创建使用指定 endpoint 的 ChatService，endpoint 形如 http://host:port。
func NewChatServiceWithEndpoint(endpoint string) *ChatService {
	endpoint = strings.TrimRight(endpoint, "/")
	if endpoint == "" {
		panic("invalid chat endpoint")
	}
	dialTimeout := defaultDialTimeout
	totalTimeout := defaultTotalTimeout
	ttfb := defaultTTFB

	client := &http.Client{
		Transport: &http.Transport{
			Proxy: http.ProxyFromEnvironment,
			DialContext: (&net.Dialer{
				Timeout:   dialTimeout,
				KeepAlive: 5 * time.Minute,
			}).DialContext,
			ForceAttemptHTTP2:     false,
			MaxIdleConns:          10,
			IdleConnTimeout:       90 * time.Second,
			TLSHandshakeTimeout:   10 * time.Second,
			ExpectContinueTimeout: 1 * time.Second,
			ResponseHeaderTimeout: ttfb,
		},
		Timeout: totalTimeout,
	}
	return &ChatService{
		chatURL:       endpoint + chatPath,
		streamChatURL: endpoint + streamChatPath,
		client:        client,
	}
}

// Chat 调用上游 /api/chat，获取一次性完整结果。
func (c *ChatService) Chat(ctx context.Context, req *LazyChatRequest) (*LazyChatResponse, error) {
	bodyBytes, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.chatURL, bytes.NewReader(bodyBytes))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.client.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, errors.New("upstream /api/chat returned non-200")
	}
	var out LazyChatResponse
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &out, nil
}

// StreamChat 调用上游 /api/chat_stream，返回增量数据 channel；ctx 取消或上游关闭时 channel 关闭。
func (c *ChatService) StreamChat(ctx context.Context, req *LazyChatRequest) (<-chan *LazyStreamData, error) {
	bodyBytes, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.streamChatURL, bytes.NewReader(bodyBytes))
	if err != nil {
		return nil, err
	}
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := c.client.Do(httpReq)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		resp.Body.Close()
		return nil, errors.New("upstream /api/chat_stream returned non-200")
	}

	return lazyStreamHandler(ctx, resp), nil
}

// lazyStreamHandler 与 neutrino 实现类似：逐行读取，每行 JSON 反序列化为 LazyChatResponse。
func lazyStreamHandler(ctx context.Context, resp *http.Response) <-chan *LazyStreamData {
	scanner := bufio.NewScanner(resp.Body)
	dataChan := make(chan *LazyStreamData)
	go func() {
		defer func() {
			close(dataChan)
			_ = resp.Body.Close()
		}()
		// 防止单行过长
		scanner.Buffer(nil, 512*1024)
		for scanner.Scan() && ctx.Err() == nil {
			text := strings.TrimSpace(scanner.Text())
			if text == "" {
				continue
			}
			data := &LazyStreamData{}
			var streamResp LazyChatResponse
			if err := json.Unmarshal([]byte(text), &streamResp); err != nil {
				// 解析失败时传递原始行，保持与 neutrino 语义接近
				data.RawText = text
			} else {
				data.Resp = &streamResp
			}
			select {
			case dataChan <- data:
			case <-ctx.Done():
				return
			}
		}
	}()
	return dataChan
}

// UpstreamStreamChunk 保留给现有 ChatConversations 逻辑使用，对应 LazyChatResponse.Data。
type UpstreamStreamChunk struct {
	Text          string `json:"text"`
	Think         string `json:"think"`
	Status        string `json:"status"`
	Sources       []any  `json:"sources"`
	ReasoningText string `json:"reasoning_text"` // 部分上游用 think
}

type upstreamStreamLine struct {
	Code int                `json:"code"`
	Msg  string             `json:"msg"`
	Data UpstreamStreamChunk `json:"data"`
}

// StreamChatUpstream 兼容旧签名：用于 ChatConversations 内部，基于上面的 ChatService.StreamChat 实现。
// body 为请求 JSON 的 map 表示，baseURL 为上游服务 endpoint（不带 /api/...）。
func StreamChatUpstream(ctx context.Context, baseURL string, body map[string]any) (<-chan UpstreamStreamChunk, error) {
	service := NewChatServiceWithEndpoint(baseURL)

	req := &LazyChatRequest{}
	if q, ok := body["query"].(string); ok {
		req.Query = q
	}
	if s, ok := body["session_id"].(string); ok {
		req.SessionID = s
	}
	if hs, ok := body["history"].([]map[string]string); ok {
		for _, h := range hs {
			req.History = append(req.History, ChatMessage{
				Role:    h["role"],
				Content: h["content"],
			})
		}
	}
	// 其余字段（filters/files/databases/enable_thinking）暂不强转，保持与原实现行为一致。

	streamChan, err := service.StreamChat(ctx, req)
	if err != nil {
		return nil, err
	}

	out := make(chan UpstreamStreamChunk, 1)
	go func() {
		defer close(out)
		for d := range streamChan {
			if d == nil {
				continue
			}
			if d.Resp == nil {
				// 解析失败时的 RawText：忽略或按需处理，这里直接跳过，保持与旧实现接近
				continue
			}
			chunk := UpstreamStreamChunk{
				Text:          d.Resp.Data.Text,
				Think:         d.Resp.Data.ReasoningText,
				Status:        d.Resp.Data.Status,
				Sources:       d.Resp.Data.Sources,
				ReasoningText: d.Resp.Data.ReasoningText,
			}
			select {
			case out <- chunk:
			case <-ctx.Done():
				return
			}
		}
	}()
	return out, nil
}

