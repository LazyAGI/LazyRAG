package segment

import (
	"encoding/json"
	"net/http"
)

func replyJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// 以下为 SegmentService 接口桩，TODO 稍后实现。

func ListSegments(w http.ResponseWriter, r *http.Request)      { replyJSON(w, map[string]any{}); /* TODO */ }
func GetSegment(w http.ResponseWriter, r *http.Request)        { replyJSON(w, map[string]any{}); /* TODO */ }
func EditSegment(w http.ResponseWriter, r *http.Request)      { replyJSON(w, map[string]any{}); /* TODO */ }
func ModifyStatus(w http.ResponseWriter, r *http.Request)     { w.WriteHeader(http.StatusOK); /* TODO */ }
func SearchSegments(w http.ResponseWriter, r *http.Request)   { replyJSON(w, map[string]any{}); /* TODO */ }
func DeleteSegment(w http.ResponseWriter, r *http.Request)    { w.WriteHeader(http.StatusOK); /* TODO */ }
func BatchSignImageURI(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
func BulkDelete(w http.ResponseWriter, r *http.Request)        { w.WriteHeader(http.StatusOK); /* TODO */ }
func HybridSearchSegments(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
func ScrollSegments(w http.ResponseWriter, r *http.Request)    { replyJSON(w, map[string]any{}); /* TODO */ }
