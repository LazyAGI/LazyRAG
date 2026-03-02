package dataset

import (
	"encoding/json"
	"net/http"
)

func replyJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// 以下为 DatasetService 接口桩，TODO 稍后实现。

func ListAlgos(w http.ResponseWriter, r *http.Request)       { replyJSON(w, map[string]any{}); /* TODO */ }
func AllDatasetTags(w http.ResponseWriter, r *http.Request)   { replyJSON(w, map[string]any{}); /* TODO */ }
func ListDatasets(w http.ResponseWriter, r *http.Request)      { replyJSON(w, map[string]any{}); /* TODO */ }
func CreateDataset(w http.ResponseWriter, r *http.Request)     { replyJSON(w, map[string]any{}); /* TODO */ }
func GetDataset(w http.ResponseWriter, r *http.Request)        { replyJSON(w, map[string]any{}); /* TODO */ }
func DeleteDataset(w http.ResponseWriter, r *http.Request)    { w.WriteHeader(http.StatusOK); /* TODO */ }
func UpdateDataset(w http.ResponseWriter, r *http.Request)    { replyJSON(w, map[string]any{}); /* TODO */ }
func SetDefault(w http.ResponseWriter, r *http.Request)        { replyJSON(w, map[string]any{}); /* TODO */ }
func UnsetDefault(w http.ResponseWriter, r *http.Request)      { replyJSON(w, map[string]any{}); /* TODO */ }
func AllDefaultDatasets(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
func PresignUploadCoverImageURL(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
func SearchDatasets(w http.ResponseWriter, r *http.Request)   { replyJSON(w, map[string]any{}); /* TODO */ }
func CallbackTask(w http.ResponseWriter, r *http.Request)      { w.WriteHeader(http.StatusOK); /* TODO */ }
