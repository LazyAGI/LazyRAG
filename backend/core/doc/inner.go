package doc

import (
	"net/http"
)

// 以下为 Internal 接口桩，TODO 稍后实现。

func GetDatasetInternal(w http.ResponseWriter, r *http.Request) {
	replyJSON(w, map[string]any{}) /* TODO */
}
func KnowledgeRetrieve(w http.ResponseWriter, r *http.Request) {
	replyJSON(w, map[string]any{}) /* TODO */
}
