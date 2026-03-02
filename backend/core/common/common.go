package common

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"time"
)

// Proxy builds a reverse proxy that forwards to targetURL.
// flushInterval controls how often buffered data is flushed to the client:
//   - 0  → flush only when the upstream response finishes (suitable for plain JSON)
//   - -1 → flush immediately after every write (suitable for SSE / streaming)
func Proxy(targetURL string, flushInterval time.Duration) http.HandlerFunc {
	target, _ := url.Parse(targetURL)
	rp := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL = target
			req.Host = target.Host
		},
		FlushInterval: flushInterval,
	}
	return rp.ServeHTTP
}
