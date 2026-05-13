package common

import "strings"

// JoinURL text base text path text '/' text，text '//' text '/'。
// base text "http://host:port"；path text "/" text（text "/"）。
func JoinURL(base, path string) string {
	base = strings.TrimRight(strings.TrimSpace(base), "/")
	path = strings.TrimLeft(strings.TrimSpace(path), "/")
	if base == "" {
		return "/" + path
	}
	if path == "" {
		return base
	}
	return base + "/" + path
}
