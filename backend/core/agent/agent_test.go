package agent

import (
	"bufio"
	"bytes"
	"context"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"math"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"lazyrag/core/common/orm"
)

func newAgentTestDB(t *testing.T) *orm.DB {
	t.Helper()

	dsn := fmt.Sprintf("file:%s_%d?mode=memory&cache=shared", strings.ReplaceAll(t.Name(), "/", "_"), time.Now().UnixNano())
	db, err := orm.Connect(orm.DriverSQLite, dsn)
	if err != nil {
		t.Fatalf("connect sqlite: %v", err)
	}
	if err := db.AutoMigrate(&orm.AgentThread{}, &orm.AgentThreadRecord{}, &orm.AgentThreadRound{}); err != nil {
		t.Fatalf("auto migrate: %v", err)
	}
	return db
}

func assertSignedStaticFileExists(t *testing.T, uploadRoot string, file *caseCSVFile) {
	t.Helper()
	if file == nil {
		t.Fatalf("expected csv file metadata")
	}
	parsed, err := url.Parse(file.FileURL)
	if err != nil {
		t.Fatalf("parse file url: %v", err)
	}
	rel, ok := strings.CutPrefix(parsed.Path, "/static-files/")
	if !ok {
		t.Fatalf("expected static file url, got %q", file.FileURL)
	}
	rel, err = url.PathUnescape(rel)
	if err != nil {
		t.Fatalf("unescape static file path: %v", err)
	}
	expectedPath := filepath.Clean(filepath.Join(uploadRoot, filepath.FromSlash(rel)))
	if filepath.Clean(file.StoredPath) != expectedPath {
		t.Fatalf("file url points to %q, but csv was stored at %q", expectedPath, file.StoredPath)
	}
	stat, err := os.Stat(expectedPath)
	if err != nil {
		t.Fatalf("expected csv file behind file_url to exist: %v", err)
	}
	if stat.Size() != file.FileSize {
		t.Fatalf("unexpected csv file size: metadata=%d actual=%d", file.FileSize, stat.Size())
	}
	raw, err := os.ReadFile(expectedPath)
	if err != nil {
		t.Fatalf("read csv file behind file_url: %v", err)
	}
	if !bytes.HasPrefix(raw, []byte{0xEF, 0xBB, 0xBF}) {
		t.Fatalf("expected csv file to start with UTF-8 BOM for Excel compatibility")
	}
}

func assertOnlyTopLevelFileURL(t *testing.T, payload any) {
	t.Helper()
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	body := string(raw)
	if count := strings.Count(body, `"file_url"`); count != 1 {
		t.Fatalf("expected exactly one file_url in response payload, got %d: %s", count, body)
	}
	for _, key := range []string{`"content_url"`, `"preview_url"`, `"download_url"`, `"download_file_url"`} {
		if strings.Contains(body, key) {
			t.Fatalf("unexpected extra url field %s in response payload: %s", key, body)
		}
	}
	for _, key := range []string{`"case_csv_file"`, `"case_details_csv_file"`, `"csv_file"`} {
		if strings.Contains(body, key) {
			t.Fatalf("unexpected generated metadata field %s in response payload: %s", key, body)
		}
	}
}

func TestDecodeJSONArrayObjectsSupportsNestedEnvelope(t *testing.T) {
	body := []byte(`{"data":{"items":[{"seq":1,"kind":"user.message"},{"seq":2,"kind":"assistant.reply"}]}}`)

	items, err := decodeJSONArrayObjects(body)
	if err != nil {
		t.Fatalf("decodeJSONArrayObjects returned error: %v", err)
	}
	if len(items) != 2 {
		t.Fatalf("expected 2 items, got %d", len(items))
	}
	if got := extractStringByKeys(items[1], "kind"); got != "assistant.reply" {
		t.Fatalf("unexpected second item kind: %q", got)
	}
}

func TestDecodeJSONArrayObjectsAllowsEmptyBody(t *testing.T) {
	items, err := decodeJSONArrayObjects([]byte(""))
	if err != nil {
		t.Fatalf("decodeJSONArrayObjects returned error for empty body: %v", err)
	}
	if len(items) != 0 {
		t.Fatalf("expected empty slice for empty body, got %d items", len(items))
	}
}

func TestThreadEventsURLUsesSinceZeroStreamFlag(t *testing.T) {
	t.Setenv("LAZYRAG_EVO_SERVICE_URL", "http://evo-service:8048/")

	got := threadEventsURL("thr/1")
	want := "http://evo-service:8048/v1/evo/threads/thr%2F1/events?since=0"
	if got != want {
		t.Fatalf("unexpected thread events URL:\nwant: %q\ngot:  %q", want, got)
	}
}

func TestBuildFetchedThreadEventsPreservesRawFrames(t *testing.T) {
	events := []map[string]any{
		{"kind": "user.message", "payload": map[string]any{"content": "a"}},
		{"kind": "assistant.reply", "payload": map[string]any{"content": "b"}},
	}

	result, err := buildFetchedThreadEvents(events)
	if err != nil {
		t.Fatalf("buildFetchedThreadEvents returned error: %v", err)
	}
	if len(result) != 2 {
		t.Fatalf("expected 2 events, got %d", len(result))
	}
	if strings.Contains(result[0].RawFrame, `"seq"`) || strings.Contains(result[1].RawFrame, `"seq"`) {
		t.Fatalf("expected backend not to inject seq into raw frames: %#v", result)
	}
}

func TestFetchedThreadEventFromSSEFrameUsesFrameData(t *testing.T) {
	event, ok := fetchedThreadEventFromSSEFrame(&sseFrame{
		Event: "message",
		Data:  `{"kind":"task.running","payload":{"task_id":"task_1"}}`,
		Raw:   `id: 1\nevent: message\ndata: {"kind":"task.running","payload":{"task_id":"task_1"}}`,
	})
	if !ok {
		t.Fatalf("expected SSE frame to produce a fetched event")
	}
	if event.EventName != "task.running" {
		t.Fatalf("expected event name task.running, got %q", event.EventName)
	}
	if event.TaskID != "task_1" {
		t.Fatalf("expected task id task_1, got %q", event.TaskID)
	}
	if event.RawFrame != `{"kind":"task.running","payload":{"task_id":"task_1"}}` {
		t.Fatalf("expected raw frame to use data JSON, got %q", event.RawFrame)
	}
}

func TestFetchedThreadEventFromSSEFrameSkipsHeartbeatAndEmptyData(t *testing.T) {
	cases := []*sseFrame{
		{Event: "heartbeat", Data: `{}`, Raw: "event: heartbeat\ndata: {}"},
		{Event: "message", Data: `{}`, Raw: "data: {}"},
		{Event: "message", Data: `{"event":"heartbeat","ts":"2026-04-29T09:32:55Z"}`, Raw: `data: {"event":"heartbeat"}`},
	}

	for _, frame := range cases {
		if event, ok := fetchedThreadEventFromSSEFrame(frame); ok {
			t.Fatalf("expected heartbeat/empty frame to be skipped, got %#v", event)
		}
	}
}

func TestBuildFetchedThreadEventsSkipsHeartbeatAndEmptyItems(t *testing.T) {
	events := []map[string]any{
		{},
		{"event": "heartbeat"},
		{"kind": "dataset_gen.start", "task_id": "task_1"},
	}

	result, err := buildFetchedThreadEvents(events)
	if err != nil {
		t.Fatalf("buildFetchedThreadEvents returned error: %v", err)
	}
	if len(result) != 1 {
		t.Fatalf("expected only one valid event, got %#v", result)
	}
	if result[0].EventName != "dataset_gen.start" || result[0].TaskID != "task_1" {
		t.Fatalf("unexpected valid event: %#v", result[0])
	}
}

func TestReadSSEFrameParsesMultilineData(t *testing.T) {
	reader := bufio.NewReader(strings.NewReader("event: answer\ndata: {\"delta\":\"hello\"}\ndata: {\"delta\":\"world\"}\n\n"))

	frame, err := readSSEFrame(reader)
	if err != nil {
		t.Fatalf("readSSEFrame returned error: %v", err)
	}
	if frame.Event != "answer" {
		t.Fatalf("expected event answer, got %q", frame.Event)
	}
	if frame.Data != "{\"delta\":\"hello\"}\n{\"delta\":\"world\"}" {
		t.Fatalf("unexpected frame data: %q", frame.Data)
	}
}

func TestBuildCaseCSVBytesJoinsListValues(t *testing.T) {
	csvBytes, rowCount, err := buildCaseCSVBytes([]any{
		map[string]any{
			"question":      "q1",
			"reference_doc": []any{"a.pdf", "b.pdf"},
			"score":         1.5,
			"meta":          map[string]any{"source": "doc"},
		},
		map[string]any{
			"question":      "q2",
			"reference_doc": []any{"c.pdf"},
			"score":         2,
			"extra":         true,
		},
	})
	if err != nil {
		t.Fatalf("buildCaseCSVBytes returned error: %v", err)
	}
	if rowCount != 2 {
		t.Fatalf("expected row count 2, got %d", rowCount)
	}

	reader := csv.NewReader(bytes.NewReader(csvBytes))
	reader.FieldsPerRecord = -1
	records, err := reader.ReadAll()
	if err != nil {
		t.Fatalf("read csv: %v", err)
	}
	if len(records) != 3 {
		t.Fatalf("expected header plus 2 rows, got %d", len(records))
	}
	expectedHeader := []string{"extra", "meta", "question", "reference_doc", "score"}
	if strings.Join(records[0], ",") != strings.Join(expectedHeader, ",") {
		t.Fatalf("unexpected header: %#v", records[0])
	}
	if records[1][3] != "a.pdf\nb.pdf" {
		t.Fatalf("expected list cell to be joined with newlines, got %q", records[1][3])
	}
	if records[1][1] != `{"source":"doc"}` {
		t.Fatalf("expected object cell to be json encoded, got %q", records[1][1])
	}
}

func TestAttachCaseCSVFileURLAddsDownloadableAttachment(t *testing.T) {
	uploadRoot := t.TempDir()
	t.Setenv("LAZYRAG_UPLOAD_ROOT", uploadRoot)
	payload := map[string]any{
		"data": map[string]any{
			"cases": []any{
				map[string]any{
					"question":      "q1",
					"reference_doc": []any{"a.pdf", "b.pdf"},
				},
			},
		},
	}

	file, found, err := attachCaseCSVFileURL(context.Background(), payload, caseCSVOptions{
		ThreadID:   "thr/1",
		ResultKind: "datasets",
	})
	if err != nil {
		t.Fatalf("attachCaseCSVFileURL returned error: %v", err)
	}
	if !found {
		t.Fatalf("expected cases field to be found")
	}
	if file == nil || file.RowCount != 1 {
		t.Fatalf("unexpected attachment: %#v", file)
	}
	if _, err := os.Stat(file.StoredPath); err != nil {
		t.Fatalf("expected csv file to exist: %v", err)
	}
	assertSignedStaticFileExists(t, uploadRoot, file)
	if !strings.Contains(file.FileURL, "/static-files/agent-results/thr_1/datasets/") || !strings.Contains(file.FileURL, "sig=") {
		t.Fatalf("unexpected file url: %q", file.FileURL)
	}
	if !strings.Contains(file.DownloadURL, "download=1") || file.DownloadURL == file.FileURL {
		t.Fatalf("unexpected download url: %q", file.DownloadURL)
	}
	data := payload["data"].(map[string]any)
	if _, ok := data[defaultCaseCSVField]; ok {
		t.Fatalf("expected only file_url to be attached to data payload")
	}
	assertOnlyTopLevelFileURL(t, data)
}

func TestAttachCaseCSVFileURLReadsCasesFromJSONPath(t *testing.T) {
	uploadRoot := t.TempDir()
	t.Setenv("LAZYRAG_UPLOAD_ROOT", uploadRoot)
	tmpDir := t.TempDir()
	jsonPath := filepath.Join(tmpDir, "eval_data.json")
	if err := os.WriteFile(jsonPath, []byte(`{"data":[{"question":"q1","answer":"a1"}]}`), 0o644); err != nil {
		t.Fatalf("write eval data json: %v", err)
	}
	item := map[string]any{
		"case_count": float64(1),
		"dataset_id": "eval_1",
		"path":       jsonPath,
	}
	payload := []any{item}

	file, found, err := attachCaseCSVFileURL(context.Background(), payload, caseCSVOptions{
		ThreadID:   "thr-1",
		ResultKind: "datasets",
		FieldNames: []string{"case", "cases", "eval_data", "data", "items", "records"},
	})
	if err != nil {
		t.Fatalf("attachCaseCSVFileURL returned error: %v", err)
	}
	if !found || file == nil || file.RowCount != 1 {
		t.Fatalf("expected csv attachment from json path, got file=%#v found=%v", file, found)
	}
	if item["file_url"] != file.FileURL {
		t.Fatalf("expected top-level file_url to point at csv file, got %#v", item["file_url"])
	}
	if _, ok := item[defaultCaseCSVField]; ok {
		t.Fatalf("expected only file_url to be attached to result item")
	}
	assertSignedStaticFileExists(t, uploadRoot, file)
	if !strings.Contains(file.FileURL, "/static-files/agent-results/thr-1/datasets/") || !strings.Contains(file.FileURL, "sig=") {
		t.Fatalf("unexpected file url: %q", file.FileURL)
	}
	assertOnlyTopLevelFileURL(t, item)
}

func TestBuildCaseDetailsCSVBytesUsesChineseHeadersAndQuestionTypeNames(t *testing.T) {
	csvBytes, rowCount, err := buildCaseDetailsCSVBytes([]any{
		map[string]any{
			"case_id":            "case-1",
			"question":           "q1",
			"question_type":      1,
			"key_points":         []any{"要点一", "要点二"},
			"context_recall":     1.0,
			"answer_correctness": 0.5,
		},
	})
	if err != nil {
		t.Fatalf("buildCaseDetailsCSVBytes returned error: %v", err)
	}
	if rowCount != 1 {
		t.Fatalf("expected row count 1, got %d", rowCount)
	}
	reader := csv.NewReader(bytes.NewReader(csvBytes))
	reader.FieldsPerRecord = -1
	records, err := reader.ReadAll()
	if err != nil {
		t.Fatalf("read csv: %v", err)
	}
	expectedHeader := []string{"案例ID", "问题", "问题类型", "关键点", "上下文召回率", "答案正确性"}
	if strings.Join(records[0], ",") != strings.Join(expectedHeader, ",") {
		t.Fatalf("unexpected case details header: %#v", records[0])
	}
	if records[1][2] != "单跳" {
		t.Fatalf("expected question_type to be mapped to 单跳, got %q", records[1][2])
	}
	if records[1][3] != "要点一\n要点二" {
		t.Fatalf("expected list value to be joined with newlines, got %q", records[1][3])
	}
}

func TestAttachCaseDetailsReportResultAddsSummaryAndCSVFile(t *testing.T) {
	uploadRoot := t.TempDir()
	t.Setenv("LAZYRAG_UPLOAD_ROOT", uploadRoot)
	payload := map[string]any{
		"data": map[string]any{
			"case_details": []any{
				map[string]any{
					"question_type":      1,
					"context_recall":     1.0,
					"doc_recall":         1.0,
					"answer_correctness": 0.5,
					"faithfulness":       1.0,
				},
				map[string]any{
					"question_type":      1,
					"context_recall":     0.5,
					"doc_recall":         1.0,
					"answer_correctness": 1.0,
					"faithfulness":       0.5,
				},
				map[string]any{
					"question_type":      2,
					"context_recall":     0.25,
					"doc_recall":         0.5,
					"answer_correctness": 1.0,
					"faithfulness":       1.0,
				},
			},
		},
	}

	summary, found, err := attachCaseDetailsReportResult(context.Background(), payload, caseDetailsReportOptions{
		ThreadID:   "thr/1",
		ResultKind: "eval-reports",
	})
	if err != nil {
		t.Fatalf("attachCaseDetailsReportResult returned error: %v", err)
	}
	if !found {
		t.Fatalf("expected case_details field to be found")
	}
	if summary == nil || summary.TotalCount != 3 || summary.CSVFile == nil {
		t.Fatalf("unexpected summary: %#v", summary)
	}
	if _, err := os.Stat(summary.CSVFile.StoredPath); err != nil {
		t.Fatalf("expected csv file to exist: %v", err)
	}
	assertSignedStaticFileExists(t, uploadRoot, summary.CSVFile)
	if !strings.Contains(summary.CSVFile.FileURL, "/static-files/agent-results/thr_1/eval-reports/") {
		t.Fatalf("unexpected file url: %q", summary.CSVFile.FileURL)
	}
	if len(summary.QuestionTypes) != 2 {
		t.Fatalf("expected 2 question type stats, got %#v", summary.QuestionTypes)
	}
	first := summary.QuestionTypes[0]
	if first.QuestionType != 1 || first.QuestionTypeKey != "single_hop" || first.QuestionTypeName != "单跳" || first.Count != 2 {
		t.Fatalf("unexpected first question type stat: %#v", first)
	}
	if first.Averages.ContextRecall == nil || math.Abs(*first.Averages.ContextRecall-0.75) > 0.000001 {
		t.Fatalf("unexpected context_recall average: %#v", first.Averages.ContextRecall)
	}
	if first.Averages.AnswerCorrectness == nil || math.Abs(*first.Averages.AnswerCorrectness-0.75) > 0.000001 {
		t.Fatalf("unexpected answer_correctness average: %#v", first.Averages.AnswerCorrectness)
	}
	data := payload["data"].(map[string]any)
	if _, ok := data[caseDetailsCSVFileField]; ok {
		t.Fatalf("expected only file_url to be attached to payload")
	}
	responseSummary, ok := data[caseDetailsSummaryField].(*caseDetailsSummary)
	if !ok || responseSummary == nil {
		t.Fatalf("expected summary with averages to remain in response payload")
	}
	if responseSummary.CSVFile != nil {
		t.Fatalf("expected summary to omit csv file metadata")
	}
	if responseSummary.TotalCount != summary.TotalCount || len(responseSummary.QuestionTypes) != len(summary.QuestionTypes) {
		t.Fatalf("unexpected response summary: %#v", responseSummary)
	}
	assertOnlyTopLevelFileURL(t, data)
}

func TestAttachCaseDetailsReportResultReadsCaseDetailsFromJSONPath(t *testing.T) {
	uploadRoot := t.TempDir()
	t.Setenv("LAZYRAG_UPLOAD_ROOT", uploadRoot)
	tmpDir := t.TempDir()
	jsonPath := filepath.Join(tmpDir, "eval_report.json")
	if err := os.WriteFile(jsonPath, []byte(`{"case_details":[{"question":"q1","question_type":1,"context_recall":1}]}`), 0o644); err != nil {
		t.Fatalf("write eval report json: %v", err)
	}
	item := map[string]any{
		"report_id": "report_1",
		"path":      jsonPath,
	}
	payload := []any{item}

	summary, found, err := attachCaseDetailsReportResult(context.Background(), payload, caseDetailsReportOptions{
		ThreadID:   "thr-1",
		ResultKind: "eval-reports",
	})
	if err != nil {
		t.Fatalf("attachCaseDetailsReportResult returned error: %v", err)
	}
	if !found || summary == nil || summary.TotalCount != 1 || summary.CSVFile == nil {
		t.Fatalf("expected case details summary from json path, got summary=%#v found=%v", summary, found)
	}
	if item["file_url"] != summary.CSVFile.FileURL {
		t.Fatalf("expected top-level file_url to point at csv file, got %#v", item["file_url"])
	}
	if _, ok := item[caseDetailsCSVFileField]; ok {
		t.Fatalf("expected only file_url to be attached to result item")
	}
	responseSummary, ok := item[caseDetailsSummaryField].(*caseDetailsSummary)
	if !ok || responseSummary == nil {
		t.Fatalf("expected summary with averages to remain in response item")
	}
	if responseSummary.CSVFile != nil {
		t.Fatalf("expected summary to omit csv file metadata")
	}
	if responseSummary.TotalCount != summary.TotalCount || len(responseSummary.QuestionTypes) != len(summary.QuestionTypes) {
		t.Fatalf("unexpected response summary: %#v", responseSummary)
	}
	assertSignedStaticFileExists(t, uploadRoot, summary.CSVFile)
	if !strings.Contains(summary.CSVFile.FileURL, "/static-files/agent-results/thr-1/eval-reports/") || !strings.Contains(summary.CSVFile.FileURL, "sig=") {
		t.Fatalf("unexpected file url: %q", summary.CSVFile.FileURL)
	}
	assertOnlyTopLevelFileURL(t, item)
}

func TestAttachCaseDetailsReportResultReadsABTestCaseDetailsFromJSONPath(t *testing.T) {
	uploadRoot := t.TempDir()
	t.Setenv("LAZYRAG_UPLOAD_ROOT", uploadRoot)
	tmpDir := t.TempDir()
	jsonPath := filepath.Join(tmpDir, "abtest_report.json")
	if err := os.WriteFile(jsonPath, []byte(`{"case_details":[{"question":"q1","question_type":2,"doc_recall":0.5,"answer_correctness":1}]}`), 0o644); err != nil {
		t.Fatalf("write abtest report json: %v", err)
	}
	item := map[string]any{
		"abtest_id": "abtest_1",
		"path":      jsonPath,
	}
	payload := []any{item}

	summary, found, err := attachCaseDetailsReportResult(context.Background(), payload, caseDetailsReportOptions{
		ThreadID:   "thr-1",
		ResultKind: "abtests",
	})
	if err != nil {
		t.Fatalf("attachCaseDetailsReportResult returned error: %v", err)
	}
	if !found || summary == nil || summary.TotalCount != 1 || summary.CSVFile == nil {
		t.Fatalf("expected abtest case details summary from json path, got summary=%#v found=%v", summary, found)
	}
	if item["file_url"] != summary.CSVFile.FileURL {
		t.Fatalf("expected top-level file_url to point at csv file, got %#v", item["file_url"])
	}
	responseSummary, ok := item[caseDetailsSummaryField].(*caseDetailsSummary)
	if !ok || responseSummary == nil {
		t.Fatalf("expected summary with averages to remain in abtest response item")
	}
	if responseSummary.CSVFile != nil {
		t.Fatalf("expected summary to omit csv file metadata")
	}
	if responseSummary.TotalCount != 1 || len(responseSummary.QuestionTypes) != 1 {
		t.Fatalf("unexpected abtest response summary: %#v", responseSummary)
	}
	assertSignedStaticFileExists(t, uploadRoot, summary.CSVFile)
	if !strings.Contains(summary.CSVFile.FileURL, "/static-files/agent-results/thr-1/abtests/") || !strings.Contains(summary.CSVFile.FileURL, "sig=") {
		t.Fatalf("unexpected abtest file url: %q", summary.CSVFile.FileURL)
	}
	assertOnlyTopLevelFileURL(t, item)
}

func TestSaveThreadRecordKeepsDuplicateThreadEventFrames(t *testing.T) {
	db := newAgentTestDB(t)

	first, created, err := saveThreadRecord(db.DB, "thr_1", "round_1", "task_1", streamKindThreadEvent, "dataset.complete", `{"seq":1}`, `{"seq":1}`)
	if err != nil {
		t.Fatalf("first save returned error: %v", err)
	}
	if !created {
		t.Fatalf("expected first save to create record")
	}

	second, created, err := saveThreadRecord(db.DB, "thr_1", "round_1", "task_1", streamKindThreadEvent, "dataset.complete", `{"seq":1}`, `{"seq":1}`)
	if err != nil {
		t.Fatalf("second save returned error: %v", err)
	}
	if !created {
		t.Fatalf("expected duplicate thread event frame to be preserved")
	}
	if first.ID == second.ID {
		t.Fatalf("expected duplicate thread event frame to get a new record id")
	}
}

func TestSaveThreadRecordKeepsDuplicateMessageFrames(t *testing.T) {
	db := newAgentTestDB(t)

	first, created, err := saveThreadRecord(db.DB, "thr_1", "round_1", "task_1", streamKindMessage, "message", `{"delta":"same"}`, `data: {"delta":"same"}`)
	if err != nil {
		t.Fatalf("first save returned error: %v", err)
	}
	if !created {
		t.Fatalf("expected first save to create record")
	}

	second, created, err := saveThreadRecord(db.DB, "thr_1", "round_1", "task_1", streamKindMessage, "message", `{"delta":"same"}`, `data: {"delta":"same"}`)
	if err != nil {
		t.Fatalf("second save returned error: %v", err)
	}
	if !created {
		t.Fatalf("expected duplicate message frame to be preserved")
	}
	if first.ID == second.ID {
		t.Fatalf("expected duplicate message frame to get a new record id")
	}
}

func TestBuildReplayFrameForMessageOmitsSSEIDAndUsesDataOnly(t *testing.T) {
	record := orm.AgentThreadRecord{
		ID:          "0001",
		ThreadID:    "thr_1",
		RoundID:     "round_1",
		StreamKind:  streamKindMessage,
		EventName:   "message",
		PayloadText: `{"delta":"hi"}`,
		RawFrame:    "id: upstream-1\nevent: message\ndata: {\"delta\":\"hi\"}",
		CreatedAt:   time.Now().UTC(),
	}

	frame := buildReplayFrame(record)
	expected := "data: {\"delta\":\"hi\"}\n\n"
	if frame != expected {
		t.Fatalf("unexpected message replay frame:\nwant: %q\ngot:  %q", expected, frame)
	}
	if strings.Contains(frame, "\nid:") || strings.HasPrefix(frame, "id:") || strings.Contains(frame, "\nevent:") || strings.HasPrefix(frame, "event:") {
		t.Fatalf("message replay frame must only include data: %q", frame)
	}
}

func TestShouldSkipStreamRecordSkipsMessageHeartbeatAndEmptyData(t *testing.T) {
	cases := []orm.AgentThreadRecord{
		{StreamKind: streamKindMessage, EventName: "heartbeat", PayloadText: `{}`, RawFrame: "event: heartbeat\ndata: {}"},
		{StreamKind: streamKindMessage, EventName: "message", PayloadText: `{}`, RawFrame: "data: {}"},
		{StreamKind: streamKindMessage, EventName: "message", PayloadText: `[]`, RawFrame: "data: []"},
		{StreamKind: streamKindMessage, EventName: "message", PayloadText: `[DONE]`, RawFrame: "data: [DONE]"},
	}

	for _, record := range cases {
		if !shouldSkipStreamRecord(record) {
			t.Fatalf("expected message stream record to be skipped: %#v", record)
		}
	}

	valid := orm.AgentThreadRecord{
		StreamKind:  streamKindMessage,
		EventName:   "message",
		PayloadText: `{"delta":"hi"}`,
		RawFrame:    `data: {"delta":"hi"}`,
	}
	if shouldSkipStreamRecord(valid) {
		t.Fatalf("expected valid message stream record to be returned")
	}
}

func TestBuildReplayFrameForThreadEventUsesJSONLineData(t *testing.T) {
	record := orm.AgentThreadRecord{
		ID:         "0001",
		ThreadID:   "thr_1",
		TaskID:     "task_1",
		StreamKind: streamKindThreadEvent,
		RawFrame:   `{"seq":1,"kind":"user.message"}`,
		CreatedAt:  time.Now().UTC(),
	}

	frame := buildReplayFrame(record)
	expected := "data: {\"seq\":1,\"kind\":\"user.message\"}\n\n"
	if frame != expected {
		t.Fatalf("unexpected task event replay frame:\nwant: %q\ngot:  %q", expected, frame)
	}
	if strings.Contains(frame, "\nid:") || strings.HasPrefix(frame, "id:") {
		t.Fatalf("thread event replay frame must not include SSE id: %q", frame)
	}
}

func TestBuildThreadEventFrameOmitsSSEID(t *testing.T) {
	frame := buildThreadEventFrame(`{"seq":1,"kind":"dataset_gen.start"}`)
	expected := "data: {\"seq\":1,\"kind\":\"dataset_gen.start\"}\n\n"
	if frame != expected {
		t.Fatalf("unexpected thread event frame:\nwant: %q\ngot:  %q", expected, frame)
	}
	if strings.Contains(frame, "\nid:") || strings.HasPrefix(frame, "id:") {
		t.Fatalf("thread event frame must not include SSE id: %q", frame)
	}
}

func TestStreamUpstreamThreadEventsForwardsDuplicateFrames(t *testing.T) {
	db := newAgentTestDB(t)
	rec := httptest.NewRecorder()
	body := strings.NewReader(strings.Join([]string{
		"event: message\ndata: {\"kind\":\"task.running\",\"task_id\":\"task_1\"}\n\n",
		"event: message\ndata: {\"kind\":\"task.running\",\"task_id\":\"task_1\"}\n\n",
	}, ""))

	if err := streamUpstreamThreadEvents(context.Background(), rec, rec, db.DB, "thr_1", body); err != nil {
		t.Fatalf("streamUpstreamThreadEvents returned error: %v", err)
	}

	want := "data: {\"kind\":\"task.running\",\"task_id\":\"task_1\"}\n\n" +
		"data: {\"kind\":\"task.running\",\"task_id\":\"task_1\"}\n\n"
	if got := rec.Body.String(); got != want {
		t.Fatalf("unexpected forwarded stream:\nwant: %q\ngot:  %q", want, got)
	}

	var count int64
	if err := db.DB.Model(&orm.AgentThreadRecord{}).
		Where("thread_id = ? AND stream_kind = ?", "thr_1", streamKindThreadEvent).
		Count(&count).Error; err != nil {
		t.Fatalf("count saved records: %v", err)
	}
	if count != 2 {
		t.Fatalf("expected both duplicate thread event frames to be saved, got %d", count)
	}
}

func TestBuildAnalysisMarkdownResultReadsMarkdownPath(t *testing.T) {
	tmpDir := t.TempDir()
	mdPath := filepath.Join(tmpDir, "analysis.md")
	if err := os.WriteFile(mdPath, []byte("# 分析报告\n\nhello"), 0o644); err != nil {
		t.Fatalf("write markdown: %v", err)
	}
	payload := map[string]any{"data": map[string]any{"analysis_report_path": mdPath}}

	body, found, err := buildAnalysisMarkdownResult(payload)
	if err != nil {
		t.Fatalf("buildAnalysisMarkdownResult returned error: %v", err)
	}
	if !found {
		t.Fatalf("expected markdown path to be found")
	}
	result := body.(map[string]any)
	if result["markdown"] != "# 分析报告\n\nhello" {
		t.Fatalf("unexpected markdown content: %#v", result["markdown"])
	}
	if result["markdown_path"] != mdPath {
		t.Fatalf("unexpected markdown path: %#v", result["markdown_path"])
	}
}

func TestBuildDiffJSONResultReadsJSONPath(t *testing.T) {
	tmpDir := t.TempDir()
	jsonPath := filepath.Join(tmpDir, "diffs.json")
	if err := os.WriteFile(jsonPath, []byte(`{"files":[{"path":"pipelines/naive.py","status":"modified"}]}`), 0o644); err != nil {
		t.Fatalf("write json: %v", err)
	}
	payload := map[string]any{"diff_json_path": jsonPath}

	body, found, err := buildDiffJSONResult(payload)
	if err != nil {
		t.Fatalf("buildDiffJSONResult returned error: %v", err)
	}
	if !found {
		t.Fatalf("expected json path to be found")
	}
	result := body.(map[string]any)
	files, ok := result["files"].([]any)
	if !ok || len(files) != 1 {
		t.Fatalf("unexpected decoded json result: %#v", result)
	}
	if result["json_path"] != jsonPath {
		t.Fatalf("unexpected json path: %#v", result["json_path"])
	}
}

func TestBuildAgentFileContentResultReturnsDiffContentDict(t *testing.T) {
	tmpDir := t.TempDir()
	diffPath := filepath.Join(tmpDir, "naive.py.diff")
	diffContent := "diff --git a/pipelines/naive.py b/pipelines/naive.py\n+hello\n"
	if err := os.WriteFile(diffPath, []byte(diffContent), 0o644); err != nil {
		t.Fatalf("write diff: %v", err)
	}

	result, err := buildAgentFileContentResult(diffPath)
	if err != nil {
		t.Fatalf("buildAgentFileContentResult returned error: %v", err)
	}
	if result.Path != diffPath || result.Filename != "naive.py.diff" || result.Content != diffContent {
		t.Fatalf("unexpected file content result: %#v", result)
	}
}

func TestDeleteThreadHistoryRemovesThreadRoundsAndRecords(t *testing.T) {
	db := newAgentTestDB(t)
	now := time.Now().UTC()

	if err := db.DB.Create(&orm.AgentThread{
		ThreadID:       "thr_1",
		Status:         "completed",
		CreateUserID:   "u1",
		CreateUserName: "tester",
		CreatedAt:      now,
		UpdatedAt:      now,
	}).Error; err != nil {
		t.Fatalf("create thread: %v", err)
	}
	if err := db.DB.Create(&orm.AgentThreadRound{
		RoundID:          "round_1",
		ThreadID:         "thr_1",
		Status:           "completed",
		UserMessage:      "hello",
		AssistantMessage: "world",
		CreatedAt:        now,
		UpdatedAt:        now,
	}).Error; err != nil {
		t.Fatalf("create round: %v", err)
	}
	if err := db.DB.Create(&orm.AgentThreadRecord{
		ID:          "record_1",
		ThreadID:    "thr_1",
		RoundID:     "round_1",
		StreamKind:  streamKindMessage,
		RecordKey:   "rk1",
		EventName:   "message",
		PayloadText: `{"delta":"hi"}`,
		RawFrame:    `data: {"delta":"hi"}`,
		CreatedAt:   now,
		UpdatedAt:   now,
	}).Error; err != nil {
		t.Fatalf("create record: %v", err)
	}

	result, err := deleteThreadHistory(db.DB, "thr_1")
	if err != nil {
		t.Fatalf("deleteThreadHistory: %v", err)
	}
	if result["deleted_threads"] != int64(1) {
		t.Fatalf("expected deleted_threads=1, got %#v", result["deleted_threads"])
	}
	if result["deleted_rounds"] != int64(1) {
		t.Fatalf("expected deleted_rounds=1, got %#v", result["deleted_rounds"])
	}
	if result["deleted_records"] != int64(1) {
		t.Fatalf("expected deleted_records=1, got %#v", result["deleted_records"])
	}
}
