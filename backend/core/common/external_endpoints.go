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
	return "http://10.119.24.129:8850"
}

