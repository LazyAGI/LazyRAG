package common

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httputil"
	"net/url"
	"time"

	"lazyrag/core/acl"
)

// ACLCheckItem 表示待做 ACL 校验的一项资源。
type ACLCheckItem struct {
	ResourceType string // kb / db
	ResourceID   string
	NeedPerm     string // read / write
}

// ACLExtractor 从请求中解析 (userID, items) 用于 ACL 校验。
// items 为 nil 或空时跳过鉴权直接放行；有项时对每项调用 acl.Can，全部通过才放行。
type ACLExtractor func(req *http.Request, body []byte) (userID int64, items []ACLCheckItem)

// Proxy 构造反向代理，将请求转发到 targetURL。
// flushInterval 控制向客户端刷写缓冲的频率：
//   - 0  → 仅在上游响应结束时刷写（适合普通 JSON）
//   - -1 → 每次写入后立即刷写（适合 SSE/流式）
func Proxy(targetURL string, flushInterval time.Duration) http.HandlerFunc {
	return ProxyWithACL(targetURL, flushInterval, nil)
}

// ForbiddenBody 为 403 响应的 JSON 体，与 acl.APIResponse 结构一致（code, message, data）。
const ForbiddenBody = `{"code":1,"message":"forbidden: no permission for this resource","data":null}`

// ProxyWithACL 在反向代理外增加 ACL 校验：转发前先读 body，用 extractor 得到 (userID, items)。
// items 为空则跳过鉴权；否则对每项调用 acl.Can，全部通过才转发。extractor 传 nil 则不做校验（等同 Proxy）。
func ProxyWithACL(targetURL string, flushInterval time.Duration, extractor ACLExtractor) http.HandlerFunc {
	target, _ := url.Parse(targetURL)
	rp := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			q := req.URL.RawQuery
			req.URL = target
			if q != "" {
				req.URL.RawQuery = q
			}
			req.Host = target.Host
		},
		FlushInterval: flushInterval,
	}
	return func(w http.ResponseWriter, r *http.Request) {
		var body []byte
		if r.Body != nil {
			body, _ = io.ReadAll(r.Body)
			r.Body.Close()
		}
		if extractor != nil {
			userID, items := extractor(r, body)
			for _, item := range items {
				if item.NeedPerm == "" || !acl.Can(userID, item.ResourceType, item.ResourceID, item.NeedPerm) {
					w.Header().Set("Content-Type", "application/json")
					w.WriteHeader(http.StatusForbidden)
					_, _ = w.Write([]byte(ForbiddenBody))
					return
				}
			}
		}
		if len(body) > 0 {
			r.Body = io.NopCloser(bytes.NewReader(body))
			r.ContentLength = int64(len(body))
		}
		rp.ServeHTTP(w, r)
	}
}

// ProxyWithACLDynamicFlush 与 ProxyWithACL 类似，但由调用方按请求（headers/body）决定本次的 flush 间隔，
// 从而同一接口可同时支持流式与非流式。
func ProxyWithACLDynamicFlush(
	targetURL string,
	extractor ACLExtractor,
	flushInterval func(req *http.Request, body []byte) time.Duration,
) http.HandlerFunc {
	target, _ := url.Parse(targetURL)
	return func(w http.ResponseWriter, r *http.Request) {
		var body []byte
		if r.Body != nil {
			body, _ = io.ReadAll(r.Body)
			r.Body.Close()
		}
		if extractor != nil {
			userID, items := extractor(r, body)
			for _, item := range items {
				if item.NeedPerm == "" || !acl.Can(userID, item.ResourceType, item.ResourceID, item.NeedPerm) {
					w.Header().Set("Content-Type", "application/json")
					w.WriteHeader(http.StatusForbidden)
					_, _ = w.Write([]byte(ForbiddenBody))
					return
				}
			}
		}
		if len(body) > 0 {
			r.Body = io.NopCloser(bytes.NewReader(body))
			r.ContentLength = int64(len(body))
		}

		fi := time.Duration(0)
		if flushInterval != nil {
			fi = flushInterval(r, body)
		}

		// 每个请求新建 proxy，以便 FlushInterval 可按请求区分。
		rp := &httputil.ReverseProxy{
			Director: func(req *http.Request) {
				q := req.URL.RawQuery
				req.URL = target
				if q != "" {
					req.URL.RawQuery = q
				}
				req.Host = target.Host
			},
			FlushInterval: fi,
		}
		rp.ServeHTTP(w, r)
	}
}
