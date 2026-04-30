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

var defaultCaseJSONPathKeys = []string{
	"path",
	"json_path",
	"file_path",
	"result_path",
	"dataset_path",
	"eval_data_path",
	"report_path",
	"report_json_path",
	"eval_report_path",
	"case_details_path",
	"abtest_path",
	"abtest_json_path",
}

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
	FileURL         string `json:"-"`
	ContentURL      string `json:"-"`
	PreviewURL      string `json:"-"`
	DownloadURL     string `json:"-"`
	DownloadFileURL string `json:"-"`
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
		return attachCaseCSVFileURLFromJSONPaths(ctx, payload, opts, fieldNames, attachmentKey)
	}
	csvBytes, rowCount, err := buildCaseCSVBytes(cases)
	if err != nil {
		return nil, true, err
	}
	file, err := writeCaseCSVFile(csvBytes, rowCount, fieldName, opts.ThreadID, opts.ResultKind)
	if err != nil {
		return nil, true, err
	}
	attachCSVFileToContainer(container, attachmentKey, file)
	return file, true, nil
}

func attachCaseCSVFileURLFromJSONPaths(ctx context.Context, payload any, opts caseCSVOptions, fieldNames []string, attachmentKey string) (*caseCSVFile, bool, error) {
	var first *caseCSVFile
	found := false
	var firstErr error

	visitJSONPathContainers(payload, defaultCaseJSONPathKeys, func(container map[string]any, path string) bool {
		if ctx != nil {
			select {
			case <-ctx.Done():
				firstErr = ctx.Err()
				return false
			default:
			}
		}

		filePayload, err := readAgentResultJSONFile(path)
		if err != nil {
			firstErr = err
			return false
		}
		fieldName, cases, ok := caseFieldFromPayload(filePayload, fieldNames)
		if !ok {
			return true
		}
		csvBytes, rowCount, err := buildCaseCSVBytes(cases)
		if err != nil {
			firstErr = err
			return false
		}
		file, err := writeCaseCSVFile(csvBytes, rowCount, fieldName, opts.ThreadID, opts.ResultKind)
		if err != nil {
			firstErr = err
			return false
		}
		attachCSVFileToContainer(container, attachmentKey, file)
		if first == nil {
			first = file
		}
		found = true
		return true
	})
	if firstErr != nil {
		return first, found, firstErr
	}
	return first, found, nil
}

func caseFieldFromPayload(payload any, fieldNames []string) (string, []any, bool) {
	if cases, ok := payload.([]any); ok && looksLikeCaseRows(cases) {
		return "items", cases, true
	}
	_, fieldName, cases, ok := findCaseFieldContainer(payload, fieldNames)
	if ok {
		return fieldName, cases, true
	}
	return "", nil, false
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
				if isCaseFieldWrapper(fieldName) {
					if container, nestedFieldName, cases, ok := findCaseFieldContainerWalk(child, fieldNames, seen); ok {
						return container, nestedFieldName, cases, true
					}
					continue
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

func isCaseFieldWrapper(fieldName string) bool {
	switch strings.TrimSpace(fieldName) {
	case "data", "result", "payload":
		return true
	default:
		return false
	}
}

func looksLikeCaseRows(items []any) bool {
	if len(items) == 0 {
		return true
	}
	for _, item := range items {
		if _, ok := item.(map[string]any); !ok {
			return false
		}
	}
	return true
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

func attachCSVFileToContainer(container map[string]any, attachmentKey string, file *caseCSVFile) {
	if container == nil || file == nil {
		return
	}
	container["file_url"] = file.FileURL
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
	csvBytes = ensureCSVUTF8BOM(csvBytes)
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

func ensureCSVUTF8BOM(csvBytes []byte) []byte {
	bom := []byte{0xEF, 0xBB, 0xBF}
	if bytes.HasPrefix(csvBytes, bom) {
		return csvBytes
	}
	withBOM := make([]byte, 0, len(bom)+len(csvBytes))
	withBOM = append(withBOM, bom...)
	withBOM = append(withBOM, csvBytes...)
	return withBOM
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
