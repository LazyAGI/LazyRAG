package agent

import (
	"bufio"
	"bytes"
	"context"
	"encoding/csv"
	"fmt"
	"math"
	"os"
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
	t.Setenv("LAZYRAG_UPLOAD_ROOT", t.TempDir())
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
	if !strings.Contains(file.FileURL, "/static-files/agent-results/thr_1/datasets/") || !strings.Contains(file.FileURL, "sig=") {
		t.Fatalf("unexpected file url: %q", file.FileURL)
	}
	if !strings.Contains(file.DownloadURL, "download=1") || file.DownloadURL == file.FileURL {
		t.Fatalf("unexpected download url: %q", file.DownloadURL)
	}
	data := payload["data"].(map[string]any)
	if data[defaultCaseCSVField] != file {
		t.Fatalf("expected attachment to be added to data payload")
	}
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
	t.Setenv("LAZYRAG_UPLOAD_ROOT", t.TempDir())
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
	if data[caseDetailsCSVFileField] != summary.CSVFile {
		t.Fatalf("expected csv file to be attached to payload")
	}
	if data[caseDetailsSummaryField] != summary {
		t.Fatalf("expected summary to be attached to payload")
	}
}

func TestSaveThreadRecordDeduplicatesSameRawFrame(t *testing.T) {
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
	if created {
		t.Fatalf("expected duplicate save to be deduplicated")
	}
	if first.ID != second.ID {
		t.Fatalf("expected duplicate save to return original record id, got %q vs %q", first.ID, second.ID)
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
	expected := "id: 0001\ndata: {\"seq\":1,\"kind\":\"user.message\"}\n\n"
	if frame != expected {
		t.Fatalf("unexpected task event replay frame:\nwant: %q\ngot:  %q", expected, frame)
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
