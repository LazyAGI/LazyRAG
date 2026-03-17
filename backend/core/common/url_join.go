package common

import "strings"

// JoinURL 将 base 与 path 以单个 '/' 拼接，避免出现 '//' 或漏 '/'。
// base 通常为 "http://host:port"；path 通常以 "/" 开头（也兼容不带 "/"）。
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

