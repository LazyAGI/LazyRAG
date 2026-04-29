package agent

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strconv"
	"strings"
	"time"

	"lazyrag/core/doc"
)

const defaultCaseCSVField = "case_csv_file"

type caseCSVOptions struct {
	ThreadID      string
	ResultKind    string
	FieldNames    []string
	AttachmentKey string
}

type caseCSVFile struct {
	Field           string `json:"field"`
	Filename        string `json:"filename"`
	ContentType     string `json:"content_type"`
	RowCount        int    `json:"row_count"`
	FileSize        int64  `json:"file_size"`
	FileURL         string `json:"file_url"`
	ContentURL      string `json:"content_url"`
	PreviewURL      string `json:"preview_url"`
	DownloadURL     string `json:"download_url"`
	DownloadFileURL string `json:"download_file_url"`
	StoredPath      string `json:"-"`
}

func attachCaseCSVFileURL(ctx context.Context, payload any, opts caseCSVOptions) (*caseCSVFile, bool, error) {
	if ctx != nil {
		select {
		case <-ctx.Done():
			return nil, false, ctx.Err()
		default:
		}
	}
	fieldNames := opts.FieldNames
	if len(fieldNames) == 0 {
		fieldNames = []string{"case", "cases"}
	}
	attachmentKey := strings.TrimSpace(opts.AttachmentKey)
	if attachmentKey == "" {
		attachmentKey = defaultCaseCSVField
	}

	container, fieldName, cases, ok := findCaseFieldContainer(payload, fieldNames)
	if !ok {
		return nil, false, nil
	}
	csvBytes, rowCount, err := buildCaseCSVBytes(cases)
	if err != nil {
		return nil, true, err
	}
	file, err := writeCaseCSVFile(csvBytes, rowCount, fieldName, opts.ThreadID, opts.ResultKind)
	if err != nil {
		return nil, true, err
	}
	container[attachmentKey] = file
	return file, true, nil
}

func findCaseFieldContainer(root any, fieldNames []string) (map[string]any, string, []any, bool) {
	seen := map[any]struct{}{}
	return findCaseFieldContainerWalk(root, normalizeCaseFieldNames(fieldNames), seen)
}

func normalizeCaseFieldNames(fieldNames []string) []string {
	normalized := make([]string, 0, len(fieldNames))
	seen := map[string]struct{}{}
	for _, fieldName := range fieldNames {
		fieldName = strings.TrimSpace(fieldName)
		if fieldName == "" {
			continue
		}
		if _, ok := seen[fieldName]; ok {
			continue
		}
		seen[fieldName] = struct{}{}
		normalized = append(normalized, fieldName)
	}
	return normalized
}

func findCaseFieldContainerWalk(root any, fieldNames []string, seen map[any]struct{}) (map[string]any, string, []any, bool) {
	switch value := root.(type) {
	case map[string]any:
		ptr := reflect.ValueOf(value).Pointer()
		if _, ok := seen[ptr]; ok {
			return nil, "", nil, false
		}
		seen[ptr] = struct{}{}
		for _, fieldName := range fieldNames {
			if child, ok := value[fieldName]; ok {
				if cases, ok := child.([]any); ok {
					return value, fieldName, cases, true
				}
				return value, fieldName, nil, true
			}
		}
		for _, key := range []string{"data", "result", "payload"} {
			if child, ok := value[key]; ok {
				if container, fieldName, cases, ok := findCaseFieldContainerWalk(child, fieldNames, seen); ok {
					return container, fieldName, cases, true
				}
			}
		}
		keys := make([]string, 0, len(value))
		for key := range value {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		for _, key := range keys {
			if key == "data" || key == "result" || key == "payload" {
				continue
			}
			if container, fieldName, cases, ok := findCaseFieldContainerWalk(value[key], fieldNames, seen); ok {
				return container, fieldName, cases, true
			}
		}
	case []any:
		for _, child := range value {
			if container, fieldName, cases, ok := findCaseFieldContainerWalk(child, fieldNames, seen); ok {
				return container, fieldName, cases, true
			}
		}
	}
	return nil, "", nil, false
}

func buildCaseCSVBytes(cases []any) ([]byte, int, error) {
	if cases == nil {
		return nil, 0, fmt.Errorf("case field must be a list")
	}
	rows := make([]map[string]any, 0, len(cases))
	headerSet := map[string]struct{}{}
	for idx, item := range cases {
		row, ok := item.(map[string]any)
		if !ok {
			return nil, 0, fmt.Errorf("case item at index %d must be an object", idx)
		}
		rows = append(rows, row)
		for key := range row {
			headerSet[key] = struct{}{}
		}
	}
	headers := make([]string, 0, len(headerSet))
	for key := range headerSet {
		headers = append(headers, key)
	}
	sort.Strings(headers)

	var buf bytes.Buffer
	writer := csv.NewWriter(&buf)
	if err := writer.Write(headers); err != nil {
		return nil, 0, err
	}
	for _, row := range rows {
		record := make([]string, 0, len(headers))
		for _, header := range headers {
			record = append(record, caseCSVCellString(row[header]))
		}
		if err := writer.Write(record); err != nil {
			return nil, 0, err
		}
	}
	writer.Flush()
	if err := writer.Error(); err != nil {
		return nil, 0, err
	}
	return buf.Bytes(), len(rows), nil
}

func caseCSVCellString(value any) string {
	if value == nil {
		return ""
	}
	if isSliceValue(value) {
		values := reflect.ValueOf(value)
		parts := make([]string, 0, values.Len())
		for i := 0; i < values.Len(); i++ {
			parts = append(parts, caseCSVScalarString(values.Index(i).Interface()))
		}
		return strings.Join(parts, "\n")
	}
	return caseCSVScalarString(value)
}

func caseCSVScalarString(value any) string {
	switch typed := value.(type) {
	case nil:
		return ""
	case string:
		return typed
	case json.Number:
		return typed.String()
	case bool:
		return strconv.FormatBool(typed)
	case float32:
		return strconv.FormatFloat(float64(typed), 'f', -1, 32)
	case float64:
		return strconv.FormatFloat(typed, 'f', -1, 64)
	case int:
		return strconv.Itoa(typed)
	case int8, int16, int32, int64:
		return fmt.Sprintf("%d", typed)
	case uint, uint8, uint16, uint32, uint64:
		return fmt.Sprintf("%d", typed)
	default:
		if bytesValue, ok := value.([]byte); ok {
			return string(bytesValue)
		}
		if isJSONLike(value) {
			if encoded, err := json.Marshal(value); err == nil {
				return string(encoded)
			}
		}
		return fmt.Sprint(value)
	}
}

func isSliceValue(value any) bool {
	if value == nil {
		return false
	}
	if _, ok := value.([]byte); ok {
		return false
	}
	kind := reflect.TypeOf(value).Kind()
	return kind == reflect.Slice || kind == reflect.Array
}

func isJSONLike(value any) bool {
	if value == nil {
		return false
	}
	kind := reflect.TypeOf(value).Kind()
	return kind == reflect.Map || kind == reflect.Slice || kind == reflect.Array || kind == reflect.Struct
}

func writeCaseCSVFile(csvBytes []byte, rowCount int, fieldName, threadID, resultKind string) (*caseCSVFile, error) {
	if len(csvBytes) == 0 {
		return nil, fmt.Errorf("csv content is empty")
	}
	sum := sha256.Sum256(csvBytes)
	digest := hex.EncodeToString(sum[:])
	filename := fmt.Sprintf("%s_%s.csv", safeAgentResultPathPart(fieldName), digest[:12])
	dir := filepath.Join(
		doc.UploadRoot(),
		"agent-results",
		safeAgentResultPathPart(firstNonEmptyString(threadID, "thread")),
		safeAgentResultPathPart(firstNonEmptyString(resultKind, "result")),
		time.Now().UTC().Format("20060102"),
	)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("create csv directory failed: %w", err)
	}
	fullPath := filepath.Join(dir, filename)
	if err := os.WriteFile(fullPath, csvBytes, 0o644); err != nil {
		return nil, fmt.Errorf("write csv file failed: %w", err)
	}
	fileURL := doc.StaticFileURLFromFullPath(fullPath)
	if fileURL == "" {
		return nil, fmt.Errorf("build csv file url failed")
	}
	downloadURL := signedFileDownloadURL(fileURL)
	return &caseCSVFile{
		Field:           fieldName,
		Filename:        filename,
		ContentType:     "text/csv; charset=utf-8",
		RowCount:        rowCount,
		FileSize:        int64(len(csvBytes)),
		FileURL:         fileURL,
		ContentURL:      fileURL,
		PreviewURL:      fileURL,
		DownloadURL:     downloadURL,
		DownloadFileURL: downloadURL,
		StoredPath:      fullPath,
	}, nil
}

func signedFileDownloadURL(fileURL string) string {
	if strings.TrimSpace(fileURL) == "" {
		return ""
	}
	if strings.Contains(fileURL, "?") {
		return fileURL + "&download=1"
	}
	return fileURL + "?download=1"
}

func safeAgentResultPathPart(value string) string {
	value = strings.TrimSpace(value)
	value = strings.ReplaceAll(value, "..", "")
	value = strings.ReplaceAll(value, "\\", "/")
	value = strings.Trim(value, "/")
	if value == "" {
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
	return replacer.Replace(value)
}

func firstNonEmptyString(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}
