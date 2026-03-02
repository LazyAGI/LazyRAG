package member

import (
	"encoding/json"
	"net/http"
)

func replyJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// 以下为 DatasetMemberService 接口桩，TODO 稍后实现。

func ListDatasetMembers(w http.ResponseWriter, r *http.Request)   { replyJSON(w, map[string]any{}); /* TODO */ }
func GetDatasetMember(w http.ResponseWriter, r *http.Request)     { replyJSON(w, map[string]any{}); /* TODO */ }
func DeleteDatasetMember(w http.ResponseWriter, r *http.Request)  { w.WriteHeader(http.StatusOK); /* TODO */ }
func UpdateDatasetMember(w http.ResponseWriter, r *http.Request)  { replyJSON(w, map[string]any{}); /* TODO */ }
func SearchDatasetMember(w http.ResponseWriter, r *http.Request)  { replyJSON(w, map[string]any{}); /* TODO */ }
func BatchAddDatasetMember(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
