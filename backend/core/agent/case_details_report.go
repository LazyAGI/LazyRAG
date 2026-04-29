package agent

import (
	"bytes"
	"context"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"reflect"
	"sort"
	"strconv"
	"strings"
)

const (
	caseDetailsField        = "case_details"
	caseDetailsCSVFileField = "case_details_csv_file"
	caseDetailsSummaryField = "case_details_summary"
)

type caseDetailsReportOptions struct {
	ThreadID   string
	ResultKind string
}

type caseDetailsSummary struct {
	TotalCount    int                       `json:"total_count"`
	QuestionTypes []caseDetailsQuestionType `json:"question_types"`
	CSVFile       *caseCSVFile              `json:"csv_file,omitempty"`
}

type caseDetailsQuestionType struct {
	QuestionType     int                       `json:"question_type"`
	QuestionTypeKey  string                    `json:"question_type_key"`
	QuestionTypeName string                    `json:"question_type_name"`
	Count            int                       `json:"count"`
	Averages         caseDetailsMetricAverages `json:"averages"`
}

type caseDetailsMetricAverages struct {
	ContextRecall     *float64 `json:"context_recall"`
	DocRecall         *float64 `json:"doc_recall"`
	AnswerCorrectness *float64 `json:"answer_correctness"`
	Faithfulness      *float64 `json:"faithfulness"`
}

type caseDetailsQuestionTypeMeta struct {
	Type int
	Key  string
	Name string
}

type caseDetailsMetricAccumulator struct {
	Sum   float64
	Count int
}

type caseDetailsQuestionTypeAccumulator struct {
	Meta    caseDetailsQuestionTypeMeta
	Count   int
	Metrics map[string]caseDetailsMetricAccumulator
}

var caseDetailsQuestionTypes = []caseDetailsQuestionTypeMeta{
	{Type: 1, Key: "single_hop", Name: "单跳"},
	{Type: 2, Key: "multi_hop", Name: "单文档多跳"},
	{Type: 3, Key: "multi_file", Name: "跨文档多跳"},
	{Type: 4, Key: "table", Name: "表格"},
	{Type: 5, Key: "formula", Name: "公式"},
}

var caseDetailsQuestionTypeByType = map[int]caseDetailsQuestionTypeMeta{
	1: caseDetailsQuestionTypes[0],
	2: caseDetailsQuestionTypes[1],
	3: caseDetailsQuestionTypes[2],
	4: caseDetailsQuestionTypes[3],
	5: caseDetailsQuestionTypes[4],
}

var caseDetailsQuestionTypeByKey = map[string]caseDetailsQuestionTypeMeta{
	"single_hop": caseDetailsQuestionTypes[0],
	"multi_hop":  caseDetailsQuestionTypes[1],
	"multi_file": caseDetailsQuestionTypes[2],
	"table":      caseDetailsQuestionTypes[3],
	"formula":    caseDetailsQuestionTypes[4],
}

var caseDetailsScoreFields = []string{
	"context_recall",
	"doc_recall",
	"answer_correctness",
	"faithfulness",
}

var caseDetailsPreferredFields = []string{
	"case_id",
	"question",
	"question_type",
	"key_points",
	"ground_truth",
	"rag_answer",
	"retrieve_contexts",
	"retrieve_doc",
	"reference_chunk_ids",
	"reference_doc_ids",
	"retrieve_chunk_ids",
	"retrieve_doc_ids",
	"context_recall",
	"doc_recall",
	"answer_correctness",
	"faithfulness",
	"is_correct",
	"reason",
	"trace_id",
	"rag_trace",
	"rag_response",
}

var caseDetailsHeaderLabels = map[string]string{
	"answer_correctness":  "答案正确性",
	"case_id":             "案例ID",
	"context_recall":      "上下文召回率",
	"doc_recall":          "文档召回率",
	"faithfulness":        "忠实度",
	"ground_truth":        "标准答案",
	"is_correct":          "是否正确",
	"key_points":          "关键点",
	"question":            "问题",
	"question_type":       "问题类型",
	"rag_answer":          "RAG回答",
	"rag_response":        "RAG响应",
	"rag_trace":           "RAG追踪",
	"reason":              "评估原因",
	"reference_chunk_ids": "参考分片ID",
	"reference_doc_ids":   "参考文档ID",
	"retrieve_chunk_ids":  "检索分片ID",
	"retrieve_contexts":   "检索上下文",
	"retrieve_doc":        "检索文档",
	"retrieve_doc_ids":    "检索文档ID",
	"trace_id":            "追踪ID",
}

func attachCaseDetailsReportResult(ctx context.Context, payload any, opts caseDetailsReportOptions) (*caseDetailsSummary, bool, error) {
	if ctx != nil {
		select {
		case <-ctx.Done():
			return nil, false, ctx.Err()
		default:
		}
	}
	container, cases, ok := findCaseDetailsContainer(payload)
	if !ok {
		return nil, false, nil
	}
	csvBytes, rowCount, err := buildCaseDetailsCSVBytes(cases)
	if err != nil {
		return nil, true, err
	}
	file, err := writeCaseCSVFile(csvBytes, rowCount, caseDetailsField, opts.ThreadID, opts.ResultKind)
	if err != nil {
		return nil, true, err
	}
	summary, err := buildCaseDetailsSummary(cases)
	if err != nil {
		return nil, true, err
	}
	summary.CSVFile = file
	container[caseDetailsCSVFileField] = file
	container[caseDetailsSummaryField] = summary
	return summary, true, nil
}

func findCaseDetailsContainer(root any) (map[string]any, []any, bool) {
	seen := map[any]struct{}{}
	return findCaseDetailsContainerWalk(root, seen)
}

func findCaseDetailsContainerWalk(root any, seen map[any]struct{}) (map[string]any, []any, bool) {
	switch value := root.(type) {
	case map[string]any:
		ptr := reflect.ValueOf(value).Pointer()
		if _, ok := seen[ptr]; ok {
			return nil, nil, false
		}
		seen[ptr] = struct{}{}
		if child, ok := value[caseDetailsField]; ok {
			if cases, ok := child.([]any); ok {
				return value, cases, true
			}
			return value, nil, true
		}
		for _, key := range []string{"data", "result", "payload"} {
			if child, ok := value[key]; ok {
				if container, cases, ok := findCaseDetailsContainerWalk(child, seen); ok {
					return container, cases, true
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
			if container, cases, ok := findCaseDetailsContainerWalk(value[key], seen); ok {
				return container, cases, true
			}
		}
	case []any:
		for _, child := range value {
			if container, cases, ok := findCaseDetailsContainerWalk(child, seen); ok {
				return container, cases, true
			}
		}
	}
	return nil, nil, false
}

func buildCaseDetailsCSVBytes(cases []any) ([]byte, int, error) {
	rows, err := caseDetailsRows(cases)
	if err != nil {
		return nil, 0, err
	}
	headers := orderedCaseDetailsHeaders(rows)
	headerLabels := make([]string, 0, len(headers))
	for _, header := range headers {
		headerLabels = append(headerLabels, caseDetailsHeaderLabel(header))
	}

	var buf bytes.Buffer
	writer := csv.NewWriter(&buf)
	if err := writer.Write(headerLabels); err != nil {
		return nil, 0, err
	}
	for _, row := range rows {
		record := make([]string, 0, len(headers))
		for _, header := range headers {
			record = append(record, caseDetailsCellString(header, row[header]))
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

func buildCaseDetailsSummary(cases []any) (*caseDetailsSummary, error) {
	rows, err := caseDetailsRows(cases)
	if err != nil {
		return nil, err
	}
	accs := map[int]*caseDetailsQuestionTypeAccumulator{}
	for _, row := range rows {
		meta := caseDetailsQuestionTypeMetaFromValue(row["question_type"])
		acc, ok := accs[meta.Type]
		if !ok {
			acc = &caseDetailsQuestionTypeAccumulator{
				Meta:    meta,
				Metrics: map[string]caseDetailsMetricAccumulator{},
			}
			accs[meta.Type] = acc
		}
		acc.Count++
		for _, field := range caseDetailsScoreFields {
			if value, ok := numberFromAny(row[field]); ok {
				metric := acc.Metrics[field]
				metric.Sum += value
				metric.Count++
				acc.Metrics[field] = metric
			}
		}
	}

	keys := make([]int, 0, len(accs))
	for key := range accs {
		keys = append(keys, key)
	}
	sort.Ints(keys)
	stats := make([]caseDetailsQuestionType, 0, len(keys))
	for _, key := range keys {
		acc := accs[key]
		stats = append(stats, caseDetailsQuestionType{
			QuestionType:     acc.Meta.Type,
			QuestionTypeKey:  acc.Meta.Key,
			QuestionTypeName: acc.Meta.Name,
			Count:            acc.Count,
			Averages: caseDetailsMetricAverages{
				ContextRecall:     averageMetric(acc.Metrics["context_recall"]),
				DocRecall:         averageMetric(acc.Metrics["doc_recall"]),
				AnswerCorrectness: averageMetric(acc.Metrics["answer_correctness"]),
				Faithfulness:      averageMetric(acc.Metrics["faithfulness"]),
			},
		})
	}
	return &caseDetailsSummary{
		TotalCount:    len(rows),
		QuestionTypes: stats,
	}, nil
}

func caseDetailsRows(cases []any) ([]map[string]any, error) {
	if cases == nil {
		return nil, fmt.Errorf("case_details field must be a list")
	}
	rows := make([]map[string]any, 0, len(cases))
	for idx, item := range cases {
		row, ok := item.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("case_details item at index %d must be an object", idx)
		}
		rows = append(rows, row)
	}
	return rows, nil
}

func orderedCaseDetailsHeaders(rows []map[string]any) []string {
	headerSet := map[string]struct{}{}
	for _, row := range rows {
		for key := range row {
			headerSet[key] = struct{}{}
		}
	}
	headers := make([]string, 0, len(headerSet))
	for _, field := range caseDetailsPreferredFields {
		if _, ok := headerSet[field]; ok {
			headers = append(headers, field)
			delete(headerSet, field)
		}
	}
	remaining := make([]string, 0, len(headerSet))
	for key := range headerSet {
		remaining = append(remaining, key)
	}
	sort.Strings(remaining)
	return append(headers, remaining...)
}

func caseDetailsHeaderLabel(key string) string {
	if label := strings.TrimSpace(caseDetailsHeaderLabels[key]); label != "" {
		return label
	}
	return key
}

func caseDetailsCellString(key string, value any) string {
	if key == "question_type" {
		return caseDetailsQuestionTypeMetaFromValue(value).Name
	}
	return caseCSVCellString(value)
}

func caseDetailsQuestionTypeMetaFromValue(value any) caseDetailsQuestionTypeMeta {
	if typeID, ok := questionTypeIDFromAny(value); ok {
		if meta, ok := caseDetailsQuestionTypeByType[typeID]; ok {
			return meta
		}
		return caseDetailsQuestionTypeMeta{Type: typeID, Key: fmt.Sprintf("unknown_%d", typeID), Name: fmt.Sprintf("未知(%d)", typeID)}
	}
	key := strings.TrimSpace(caseCSVScalarString(value))
	if meta, ok := caseDetailsQuestionTypeByKey[key]; ok {
		return meta
	}
	if key == "" {
		return caseDetailsQuestionTypeMeta{Type: 0, Key: "unknown", Name: "未知"}
	}
	return caseDetailsQuestionTypeMeta{Type: 0, Key: key, Name: key}
}

func questionTypeIDFromAny(value any) (int, bool) {
	switch typed := value.(type) {
	case json.Number:
		n, err := typed.Int64()
		if err != nil {
			return 0, false
		}
		return int(n), true
	case float64:
		return int(typed), typed == float64(int(typed))
	case float32:
		return int(typed), typed == float32(int(typed))
	case int:
		return typed, true
	case int8:
		return int(typed), true
	case int16:
		return int(typed), true
	case int32:
		return int(typed), true
	case int64:
		return int(typed), true
	case uint:
		return int(typed), true
	case uint8:
		return int(typed), true
	case uint16:
		return int(typed), true
	case uint32:
		return int(typed), true
	case uint64:
		return int(typed), true
	case string:
		n, err := strconv.Atoi(strings.TrimSpace(typed))
		if err != nil {
			return 0, false
		}
		return n, true
	default:
		return 0, false
	}
}

func numberFromAny(value any) (float64, bool) {
	switch typed := value.(type) {
	case json.Number:
		n, err := typed.Float64()
		return n, err == nil
	case float64:
		return typed, true
	case float32:
		return float64(typed), true
	case int:
		return float64(typed), true
	case int8:
		return float64(typed), true
	case int16:
		return float64(typed), true
	case int32:
		return float64(typed), true
	case int64:
		return float64(typed), true
	case uint:
		return float64(typed), true
	case uint8:
		return float64(typed), true
	case uint16:
		return float64(typed), true
	case uint32:
		return float64(typed), true
	case uint64:
		return float64(typed), true
	case string:
		n, err := strconv.ParseFloat(strings.TrimSpace(typed), 64)
		return n, err == nil
	default:
		return 0, false
	}
}

func averageMetric(metric caseDetailsMetricAccumulator) *float64 {
	if metric.Count == 0 {
		return nil
	}
	avg := metric.Sum / float64(metric.Count)
	return &avg
}
