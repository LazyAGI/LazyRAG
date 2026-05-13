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

// ACLCheckItem text ACL text。
type ACLCheckItem struct {
	ResourceType string // kb / db
	ResourceID   string
	NeedPerm     string // read / write
}

// ACLExtractor textRequesttext (userID, items) text ACL text。
// items text nil textAuthorizationtext；text acl.Can，text。
type ACLExtractor func(req *http.Request, body []byte) (userID string, items []ACLCheckItem)

// Proxy text，textRequesttext targetURL。
// flushInterval text：
//   - 0  → textResponsetext（text JSON）
//   - -1 → text（text SSE/text）
func Proxy(targetURL string, flushInterval time.Duration) http.HandlerFunc {
	return ProxyWithACL(targetURL, flushInterval, nil)
}

// ForbiddenBody text 403 Responsetext JSON text，text acl.APIResponse text（code, message, data）。
const ForbiddenBody = `{"code":2000102,"message":"forbidden: no permission for this resource","data":null}`

// ProxyWithACL text ACL text：text body，text extractor text (userID, items)。
// items textAuthorization；text acl.Can，text。extractor text nil text（text Proxy）。
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
			var err error
			body, err = io.ReadAll(r.Body)
			r.Body.Close()
			if err != nil {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":2000103,"message":"read request body failed","data":null}`))
				return
			}
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

// ProxyWithACLDynamicFlush text ProxyWithACL text，textRequest（headers/body）text flush text，
// text。
func ProxyWithACLDynamicFlush(
	targetURL string,
	extractor ACLExtractor,
	flushInterval func(req *http.Request, body []byte) time.Duration,
) http.HandlerFunc {
	target, _ := url.Parse(targetURL)
	return func(w http.ResponseWriter, r *http.Request) {
		var body []byte
		if r.Body != nil {
			var err error
			body, err = io.ReadAll(r.Body)
			r.Body.Close()
			if err != nil {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusBadRequest)
				_, _ = w.Write([]byte(`{"code":2000103,"message":"read request body failed","data":null}`))
				return
			}
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

		// textRequesttext proxy，text FlushInterval textRequesttext。
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
