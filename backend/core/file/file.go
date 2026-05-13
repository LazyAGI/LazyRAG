package file

import (
	"encoding/json"
	"net/http"
	"os"

	"lazyrag/core/common"
)

// parseServiceURL text Python text（Document）text base URL。
// text LAZYRAG_PARSING_SERVICE_URL text，Default http://localhost:8000。
func parseServiceURL() string {
	if u := os.Getenv("LAZYRAG_PARSING_SERVICE_URL"); u != "" {
		return u
	}
	return "http://localhost:8000"
}

// processorServiceURL textUploadtext base URL（text doc-manager text add_doc）。
// text LAZYRAG_PROCESSOR_SERVICE_URL text，Default http://localhost:8001。
func processorServiceURL() string {
	if u := os.Getenv("LAZYRAG_PROCESSOR_SERVICE_URL"); u != "" {
		return u
	}
	return "http://localhost:8001"
}

// UploadFiles text POST /upload_files text（multipart）。
var UploadFiles = common.Proxy(parseServiceURL()+"/upload_files", 0)

// AddFilesToGroup text POST text upload_and_add（DocumentProcessor add_doc，text doc-manager）。
var AddFilesToGroup = common.Proxy(processorServiceURL()+"/upload_and_add", 0)

// emptyListResp text doc-manager text JSON Response。
var emptyListResp = map[string]interface{}{"code": 200, "msg": "success", "data": []interface{}{}}

// ListFiles text（doc-manager text）。
func ListFiles(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(emptyListResp)
}

// ListFilesInGroup text（doc-manager text）。
func ListFilesInGroup(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(emptyListResp)
}

// ListKBGroups text GET /list_kb_groups text。
var ListKBGroups = common.Proxy(parseServiceURL()+"/list_kb_groups", 0)
