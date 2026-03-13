package file

import (
	"encoding/json"
	"net/http"
	"os"

	"lazyrag/core/common"
)

// parseServiceURL 返回 Python 解析（文档）服务的 base URL。
// 可通过环境变量 LAZYRAG_PARSING_SERVICE_URL 覆盖，默认 http://localhost:8000。
func parseServiceURL() string {
	if u := os.Getenv("LAZYRAG_PARSING_SERVICE_URL"); u != "" {
		return u
	}
	return "http://localhost:8000"
}

// processorServiceURL 返回处理器上传服务的 base URL（用于无 doc-manager 的 add_doc）。
// 可通过环境变量 LAZYRAG_PROCESSOR_SERVICE_URL 覆盖，默认 http://localhost:8001。
func processorServiceURL() string {
	if u := os.Getenv("LAZYRAG_PROCESSOR_SERVICE_URL"); u != "" {
		return u
	}
	return "http://localhost:8001"
}

// UploadFiles 将 POST /upload_files 代理到解析服务（multipart）。
var UploadFiles = common.Proxy(parseServiceURL()+"/upload_files", 0)

// AddFilesToGroup 将 POST 代理到处理器的 upload_and_add（DocumentProcessor add_doc，无 doc-manager）。
var AddFilesToGroup = common.Proxy(processorServiceURL()+"/upload_and_add", 0)

// emptyListResp 为 doc-manager 未实现时列表接口返回的 JSON 响应。
var emptyListResp = map[string]interface{}{"code": 200, "msg": "success", "data": []interface{}{}}

// ListFiles 返回空列表（doc-manager 尚未实现）。
func ListFiles(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(emptyListResp)
}

// ListFilesInGroup 返回空列表（doc-manager 尚未实现）。
func ListFilesInGroup(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(emptyListResp)
}

// ListKBGroups 将 GET /list_kb_groups 代理到解析服务。
var ListKBGroups = common.Proxy(parseServiceURL()+"/list_kb_groups", 0)
