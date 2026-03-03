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

// ACLCheckItem represents one resource to check for ACL.
type ACLCheckItem struct {
	ResourceType string // kb / db
	ResourceID   string
	NeedPerm     string // read / write
}

// ACLExtractor extracts (userID, items) from the request for ACL check.
// When items is nil or empty: skip auth, direct pass.
// When items has entries: loop acl.Can for each; all must pass for request to pass.
type ACLExtractor func(req *http.Request, body []byte) (userID int64, items []ACLCheckItem)

// Proxy builds a reverse proxy that forwards to targetURL.
// flushInterval controls how often buffered data is flushed to the client:
//   - 0  → flush only when the upstream response finishes (suitable for plain JSON)
//   - -1 → flush immediately after every write (suitable for SSE / streaming)
func Proxy(targetURL string, flushInterval time.Duration) http.HandlerFunc {
	return ProxyWithACL(targetURL, flushInterval, nil)
}

// ForbiddenBody is the JSON body for 403 responses. Matches acl.APIResponse shape (code, message, data).
const ForbiddenBody = `{"code":1,"message":"forbidden: no permission for this resource","data":null}`

// ProxyWithACL wraps the reverse proxy with ACL check. Before forwarding, body is read,
// extractor is called to get (userID, items). When items is empty, skip auth. Otherwise
// acl.Can is invoked for each item; all must pass for request to pass.
// Pass nil as extractor to skip check (same as Proxy).
func ProxyWithACL(targetURL string, flushInterval time.Duration, extractor ACLExtractor) http.HandlerFunc {
	target, _ := url.Parse(targetURL)
	rp := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL = target
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
