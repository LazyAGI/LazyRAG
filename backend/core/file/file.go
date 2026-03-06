package file

import (
	"encoding/json"
	"net/http"
	"os"

	"lazyrag/core/common"
)

// Temp file, for testing only, will be removed later

// parseServiceURL returns the base URL of the Python parsing (document) service.
// Override with env LAZYRAG_PARSING_SERVICE_URL (default: http://localhost:8000).
func parseServiceURL() string {
	if u := os.Getenv("LAZYRAG_PARSING_SERVICE_URL"); u != "" {
		return u
	}
	return "http://localhost:8000"
}

// processorServiceURL returns the base URL of the processor upload service (for add_doc without doc-manager).
// Override with env LAZYRAG_PROCESSOR_SERVICE_URL (default: http://localhost:8001).
func processorServiceURL() string {
	if u := os.Getenv("LAZYRAG_PROCESSOR_SERVICE_URL"); u != "" {
		return u
	}
	return "http://localhost:8001"
}

// UploadFiles proxies POST /upload_files to the parsing service (multipart).
var UploadFiles = common.Proxy(parseServiceURL()+"/upload_files", 0)

// AddFilesToGroup proxies POST to processor's upload_and_add (DocumentProcessor add_doc, no doc-manager).
var AddFilesToGroup = common.Proxy(processorServiceURL()+"/upload_and_add", 0)

// emptyListResp is the JSON response for list endpoints when doc-manager is not available.
var emptyListResp = map[string]interface{}{"code": 200, "msg": "success", "data": []interface{}{}}

// ListFiles returns empty list (doc-manager not implemented yet).
func ListFiles(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(emptyListResp)
}

// ListFilesInGroup returns empty list (doc-manager not implemented yet).
func ListFilesInGroup(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(emptyListResp)
}

// ListKBGroups proxies GET /list_kb_groups to the parsing service.
var ListKBGroups = common.Proxy(parseServiceURL()+"/list_kb_groups", 0)
