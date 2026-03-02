package retrieval

import (
	"encoding/json"
	"net/http"
)

func replyJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// 以下为 RetrievalService（search/QA）接口桩，TODO 稍后实现。

func AllSearchHistory(w http.ResponseWriter, r *http.Request)   { replyJSON(w, map[string]any{}); /* TODO */ }
func SearchKnowledge(w http.ResponseWriter, r *http.Request)   { replyJSON(w, map[string]any{}); /* TODO */ }
func DeleteSearchHistory(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK); /* TODO */ }
