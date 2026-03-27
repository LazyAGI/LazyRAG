// chat text /api/chat text /api/chat_stream text，
// text neutrino external/chat.go text ChatService text。
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

// ChatMessage text neutrino external.ChatMessage text。
type ChatMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// DatasetFilters text neutrino external.DatasetFilters text（text）。
type DatasetFilters struct {
	Subject    []string `json:"subject,omitempty"`
	DatasetIDs []string `json:"kb_id,omitempty"`
	Tags       []string `json:"tags,omitempty"`
	Creators   []string `json:"creator,omitempty"`
}

// LazyChatRequest text neutrino external.LazyChatRequest text，text /api/chat text /api/chat_stream。
type LazyChatRequest struct {
	Query          string          `json:"query"`
	History        []ChatMessage   `json:"history,omitempty"`
	SessionID      string          `json:"session_id"`
	Files          []string        `json:"files,omitempty"`
	Filters        *DatasetFilters `json:"filters"`
	Databases      []any           `json:"databases,omitempty"`
	EnableThinking bool            `json:"enable_thinking,omitempty"`
}

// LazyChatData text data text。
type LazyChatData struct {
	Text          string `json:"text"`
	Sources       []any  `json:"sources"`
	Status        string `json:"status"`
	ReasoningText string `json:"think"`
}

// LazyChatResponse text /api/chat textResponse。
type LazyChatResponse struct {
	Code int          `json:"code"`
	Msg  string       `json:"msg"`
	Data LazyChatData `json:"data"`
	Cost float64      `json:"cost"`
}

// LazyStreamData text /api/chat_stream text。
type LazyStreamData struct {
	RawText string
	Resp    *LazyChatResponse
}

// ChatService text（/api/chat text /api/chat_stream）。
type ChatService struct {
	chatURL       string
	streamChatURL string
	client        *http.Client
}

// NewChatServiceWithEndpoint Createtext endpoint text ChatService，endpoint text http://host:port。
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

// Chat text /api/chat，Gettext。
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

// StreamChat text /api/chat_stream，text channel；ctx Unsettext channel text。
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

// lazyStreamHandler text neutrino text：text，text JSON text LazyChatResponse。
func lazyStreamHandler(ctx context.Context, resp *http.Response) <-chan *LazyStreamData {
	scanner := bufio.NewScanner(resp.Body)
	dataChan := make(chan *LazyStreamData)
	go func() {
		defer func() {
			close(dataChan)
			_ = resp.Body.Close()
		}()
		// text
		scanner.Buffer(nil, 512*1024)
		for scanner.Scan() && ctx.Err() == nil {
			text := strings.TrimSpace(scanner.Text())
			if text == "" {
				continue
			}
			data := &LazyStreamData{}
			var streamResp LazyChatResponse
			if err := json.Unmarshal([]byte(text), &streamResp); err != nil {
				// textFailedtext，text neutrino text
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

// UpstreamStreamChunk text ChatConversations text，text LazyChatResponse.Data。
type UpstreamStreamChunk struct {
	Text          string `json:"text"`
	Think         string `json:"think"`
	Status        string `json:"status"`
	Sources       []any  `json:"sources"`
	ReasoningText string `json:"reasoning_text"` // text think
}

type upstreamStreamLine struct {
	Code int                 `json:"code"`
	Msg  string              `json:"msg"`
	Data UpstreamStreamChunk `json:"data"`
}

// StreamChatUpstream text：text ChatConversations text，text ChatService.StreamChat text。
// body textRequest JSON text map text，baseURL text endpoint（text /api/...）。
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
	// text（filters/files/databases/enable_thinking）text，text。

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
				// textFailedtext RawText：text，text，text
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
