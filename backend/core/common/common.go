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

// ACLExtractor extracts (userID, kbID, needPerm) from the request for ACL check.
// needPerm is passed to acl.Can (e.g. "read", "write"). Return empty needPerm to deny.
type ACLExtractor func(req *http.Request, body []byte) (userID, kbID int64, needPerm string)

// Proxy builds a reverse proxy that forwards to targetURL.
// flushInterval controls how often buffered data is flushed to the client:
//   - 0  → flush only when the upstream response finishes (suitable for plain JSON)
//   - -1 → flush immediately after every write (suitable for SSE / streaming)
func Proxy(targetURL string, flushInterval time.Duration) http.HandlerFunc {
	return ProxyWithACL(targetURL, flushInterval, nil)
}

// ProxyWithACL wraps the reverse proxy with ACL check. Before forwarding, body is read,
// extractor is called to get (userID, kbID, needPerm); then acl.Can(userID, kbID, needPerm)
// is invoked. If false or needPerm is empty, respond 403. Otherwise restore body and proxy.
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
			userID, kbID, needPerm := extractor(r, body)
			if needPerm == "" || !acl.Can(userID, kbID, needPerm) {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusForbidden)
				_, _ = w.Write([]byte(`{"code":1,"message":"forbidden: no permission for this knowledge base","data":null}`))
				return
			}
		}
		if len(body) > 0 {
			r.Body = io.NopCloser(bytes.NewReader(body))
			r.ContentLength = int64(len(body))
		}
		rp.ServeHTTP(w, r)
	}
}
