package inner

import (
	"encoding/json"
	"net/http"
)

func replyJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// 以下为 Internal 接口桩，TODO 稍后实现。

func GetDataset(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}) /* TODO */ }
func KnowledgeRetrieve(w http.ResponseWriter, r *http.Request) {
	replyJSON(w, map[string]any{}) /* TODO */
}
