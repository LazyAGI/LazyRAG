package common

import (
	"os"
	"strings"
)

// AlgoServiceEndpoint text base URL（text path）。
// text LAZYRAG_ALGO_SERVICE_URL text；textSettextDefaulttext，text。
func AlgoServiceEndpoint() string {
	if u := strings.TrimSpace(os.Getenv("LAZYRAG_ALGO_SERVICE_URL")); u != "" {
		return strings.TrimRight(u, "/")
	}
	return "http://10.119.24.129:8850"
}

