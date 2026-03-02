package document

import (
	"encoding/json"
	"net/http"
)

func replyJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// 以下为 DocumentService 接口桩，TODO 稍后实现。

func ListDocuments(w http.ResponseWriter, r *http.Request)    { replyJSON(w, map[string]any{}); /* TODO */ }
func CreateDocument(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
func GetDocument(w http.ResponseWriter, r *http.Request)     { replyJSON(w, map[string]any{}); /* TODO */ }
func DeleteDocument(w http.ResponseWriter, r *http.Request)  { w.WriteHeader(http.StatusOK); /* TODO */ }
func UpdateDocument(w http.ResponseWriter, r *http.Request)  { replyJSON(w, map[string]any{}); /* TODO */ }
func SearchDocuments(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
func SearchAllDocuments(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
func BatchDeleteDocument(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK); /* TODO */ }
func AllDocumentCreators(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
func AllDocumentTags(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
func AddTableData(w http.ResponseWriter, r *http.Request)    { w.WriteHeader(http.StatusOK); /* TODO */ }
func BatchDeleteTableData(w http.ResponseWriter, r *http.Request) { w.WriteHeader(http.StatusOK); /* TODO */ }
func ModifyTableData(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
func SearchTableData(w http.ResponseWriter, r *http.Request) { replyJSON(w, map[string]any{}); /* TODO */ }
