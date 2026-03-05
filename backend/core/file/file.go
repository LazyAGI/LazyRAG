package file

import (
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

// UploadFiles proxies POST /upload_files to the parsing service (multipart).
var UploadFiles = common.Proxy(parseServiceURL()+"/upload_files", 0)

// AddFilesToGroup proxies POST /add_files_to_group to the parsing service (multipart).
var AddFilesToGroup = common.Proxy(parseServiceURL()+"/add_files_to_group", 0)

// ListFiles proxies GET /list_files to the parsing service.
var ListFiles = common.Proxy(parseServiceURL()+"/list_files", 0)

// ListFilesInGroup proxies GET /list_files_in_group to the parsing service.
var ListFilesInGroup = common.Proxy(parseServiceURL()+"/list_files_in_group", 0)

// ListKBGroups proxies GET /list_kb_groups to the parsing service.
var ListKBGroups = common.Proxy(parseServiceURL()+"/list_kb_groups", 0)
