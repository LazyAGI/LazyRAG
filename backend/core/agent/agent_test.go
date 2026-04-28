package agent

import (
	"bufio"
	"fmt"
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
