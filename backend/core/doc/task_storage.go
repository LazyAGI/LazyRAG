package doc

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"lazyrag/core/common"
)

func uploadRoot() string {
	if v := strings.TrimSpace(os.Getenv("LAZYRAG_UPLOAD_ROOT")); v != "" {
		return strings.TrimRight(v, "/")
	}
	return "/var/lib/lazyrag/uploads"
}

func parsingServiceEndpoint() string {
	if v := strings.TrimSpace(os.Getenv("LAZYRAG_DOCUMENT_SERVICE_URL")); v != "" {
		return strings.TrimRight(v, "/")
	}
	return common.AlgoServiceEndpoint()
}

func safePathPart(s string) string {
	s = strings.TrimSpace(s)
	s = strings.ReplaceAll(s, "..", "")
	s = strings.ReplaceAll(s, "\\", "/")
	s = strings.Trim(s, "/")
	if s == "" {
		return "root"
	}
	replacer := strings.NewReplacer(
		"/", "_",
		":", "_",
		"*", "_",
		"?", "_",
		"\"", "_",
		"<", "_",
		">", "_",
		"|", "_",
	)
	return replacer.Replace(s)
}

func buildDatasetDocDir(tenantID, datasetID, relativePath string) string {
	parts := []string{uploadRoot(), "tenants", safePathPart(tenantID), "datasets", safePathPart(datasetID), "docs"}
	if rp := safePathPart(relativePath); rp != "root" {
		parts = append(parts, strings.Split(rp, "_")...)
	}
	return filepath.Join(parts...)
}

func buildDatasetDocFileDir(tenantID, datasetID, relativePath, fileID string) string {
	baseDir := buildDatasetDocDir(tenantID, datasetID, relativePath)
	if strings.TrimSpace(fileID) == "" {
		return filepath.Join(baseDir, "files", "root")
	}
	return filepath.Join(baseDir, "files", safePathPart(fileID))
}

func buildTaskUploadDir(tenantID, datasetID, taskID, uploadID string) string {
	return filepath.Join(uploadRoot(), "tenants", safePathPart(tenantID), "datasets", safePathPart(datasetID), "tmp", "tasks", safePathPart(taskID), "uploads", safePathPart(uploadID))
}

func buildDatasetUploadDir(tenantID, datasetID, uploadID string) string {
	return filepath.Join(uploadRoot(), "tenants", safePathPart(tenantID), "datasets", safePathPart(datasetID), "tmp", "uploads", safePathPart(uploadID))
}

func buildTempUploadDir(userID, uploadID string) string {
	return filepath.Join(uploadRoot(), "tmp", "users", safePathPart(userID), "uploads", safePathPart(uploadID))
}

func buildTempUploadFileDir(userID, uploadID string) string {
	return filepath.Join(uploadRoot(), "tmp", "users", safePathPart(userID), "files", safePathPart(uploadID))
}

func storedFileName(filename, documentID string) string {
	ext := filepath.Ext(filename)
	base := strings.TrimSuffix(filename, ext)
	base = safePathPart(base)
	if base == "" || base == "root" {
		base = safePathPart(documentID)
	}
	if ext == "" {
		return base
	}
	return fmt.Sprintf("%s%s", base, ext)
}

func parseStoredNameFromSource(storedName string) string {
	storedName = strings.TrimSpace(storedName)
	if storedName == "" {
		return ""
	}
	ext := filepath.Ext(storedName)
	base := strings.TrimSuffix(storedName, ext)
	if base == "" {
		base = storedName
	}
	return base + ".__parsed__.pdf"
}

func mustJSON(v any) json.RawMessage {
	b, _ := json.Marshal(v)
	return b
}
