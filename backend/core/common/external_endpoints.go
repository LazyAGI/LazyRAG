package common

import (
	"os"
	"strings"
)

// AlgoServiceEndpoint 返回算法服务的 base URL（不带 path）。
// 通过环境变量 LAZYRAG_ALGO_SERVICE_URL 配置；未设置时使用默认值，方便本地开发。
func AlgoServiceEndpoint() string {
	if u := strings.TrimSpace(os.Getenv("LAZYRAG_ALGO_SERVICE_URL")); u != "" {
		return strings.TrimRight(u, "/")
	}
	return "http://127.0.0.1:8848"
}

// KbServiceEndpoint 返回 KB/Docs 外部服务的 base URL（不带 path）。
// 通过环境变量 LAZYRAG_KB_SERVICE_URL 配置；未设置时默认沿用 AlgoServiceEndpoint。
func KbServiceEndpoint() string {
	if u := strings.TrimSpace(os.Getenv("LAZYRAG_KB_SERVICE_URL")); u != "" {
		return strings.TrimRight(u, "/")
	}
	return AlgoServiceEndpoint()
}

