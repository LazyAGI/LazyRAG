package agent

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/gorilla/mux"
	"gorm.io/gorm"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/log"
	"lazyrag/core/store"
)

type threadResponse struct {
	ThreadID      string    `json:"thread_id"`
	CurrentTaskID string    `json:"current_task_id,omitempty"`
	Status        string    `json:"status"`
	ThreadPayload any       `json:"thread_payload,omitempty"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

type recordResponse struct {
	ID         string    `json:"id"`
	ThreadID   string    `json:"thread_id"`
	TaskID     string    `json:"task_id,omitempty"`
	StreamKind string    `json:"stream_kind"`
	EventName  string    `json:"event_name,omitempty"`
	Payload    any       `json:"payload"`
	RawFrame   string    `json:"raw_frame"`
	CreatedAt  time.Time `json:"created_at"`
}

type upstreamProxyResponse struct {
	Body        any
	ContentType string
}

type threadFlowStatusResponse struct {
	ThreadID           string   `json:"thread_id,omitempty"`
	Status             string   `json:"status,omitempty"`
	ActiveTaskIDs      []string `json:"active_task_ids,omitempty"`
	LatestAbtestID     any      `json:"latest_abtest_id,omitempty"`
	LatestAbtestStatus any      `json:"latest_abtest_status,omitempty"`
	ReportReady        bool     `json:"report_ready,omitempty"`
}

func CreateThread(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}

	requestPayload, _, err := decodeRequestBody(r)
	if err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "invalid body", err), http.StatusBadRequest)
		return
	}

	var creationGuard *userActiveThreadCreationGuard
	// Temporary integration bypass: comment this guard block to disable single-active-thread enforcement.
	if guard, guardErr := reserveUserActiveThreadCreation(r.Context(), db, r); guardErr != nil {
		replyUserActiveThreadError(w, guardErr)
		return
	} else {
		creationGuard = guard
		defer creationGuard.Abort(db)
	}

	var upstreamRaw json.RawMessage
	headers := forwardedUpstreamHeaders(r)
	if err := common.ApiPost(r.Context(), threadCreateURL(), requestPayload, headers, &upstreamRaw, 30*time.Second); err != nil {
		common.ReplyErrWithData(w, "create upstream thread failed", map[string]any{"detail": err.Error()}, http.StatusBadGateway)
		return
	}

	var upstreamValue any
	if err := json.Unmarshal(upstreamRaw, &upstreamValue); err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "invalid upstream response", err), http.StatusBadGateway)
		return
	}

	threadID := extractStringByKeys(upstreamValue, "thread_id", "id")
	if threadID == "" {
		common.ReplyErr(w, "upstream thread response missing thread_id", http.StatusBadGateway)
		return
	}

	thread, err := upsertThread(db, threadID, "", "created", string(upstreamRaw), "", store.UserID(r), store.UserName(r))
	if err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "save thread failed", err), http.StatusInternalServerError)
		return
	}
	if err := creationGuard.Commit(db, threadID); err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "activate user thread failed", err), http.StatusInternalServerError)
		return
	}

	common.ReplyOK(w, map[string]any{
		"thread":   toThreadResponse(thread),
		"upstream": upstreamValue,
	})
}

func GetThread(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}
	threadID := strings.TrimSpace(mux.Vars(r)["thread_id"])
	thread, err := loadThread(db, threadID)
	if err != nil {
		replyThreadLoadError(w, err)
		return
	}
	common.ReplyOK(w, map[string]any{"thread": toThreadResponse(thread)})
}

func ListThreadRecords(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}
	threadID := strings.TrimSpace(mux.Vars(r)["thread_id"])
	if _, err := loadThread(db, threadID); err != nil {
		replyThreadLoadError(w, err)
		return
	}

	streamKind := strings.TrimSpace(r.URL.Query().Get("stream_kind"))
	afterID := parseAfterID(r)
	limit := parseRecordLimit(r.URL.Query().Get("limit"))

	records, err := listRecords(db, threadID, streamKind, "", afterID, limit+1)
	if err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "list thread records failed", err), http.StatusInternalServerError)
		return
	}

	hasMore := len(records) > limit
	if hasMore {
		records = records[:limit]
	}
	nextAfterID := afterID
	if len(records) > 0 {
		nextAfterID = records[len(records)-1].ID
	}

	items := make([]recordResponse, 0, len(records))
	for _, record := range records {
		items = append(items, toRecordResponse(record))
	}

	common.ReplyOK(w, map[string]any{
		"thread_id":     threadID,
		"stream_kind":   streamKind,
		"items":         items,
		"next_after_id": nextAfterID,
		"has_more":      hasMore,
	})
}

func StreamThreadMessages(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}

	threadID := strings.TrimSpace(mux.Vars(r)["thread_id"])
	thread, err := loadThread(db, threadID)
	if err != nil {
		replyThreadLoadError(w, err)
		return
	}

	afterID := parseAfterID(r)
	resumeOnly := strings.EqualFold(strings.TrimSpace(r.URL.Query().Get("resume_only")), "1") ||
		strings.EqualFold(strings.TrimSpace(r.URL.Query().Get("resume_only")), "true")

	var session *activeMessageStream
	if !resumeOnly {
		_, requestBytes, err := decodeRequestBody(r)
		if err != nil {
			common.ReplyErr(w, fmt.Sprintf("%s: %v", "invalid body", err), http.StatusBadRequest)
			return
		}
		if len(requestBytes) == 0 || string(requestBytes) == "{}" {
			common.ReplyErr(w, "messages request body required", http.StatusBadRequest)
			return
		}

		session, err = ensureMessageStream(db, thread, requestBytes, forwardedUpstreamHeaders(r))
		if err != nil {
			common.ReplyErr(w, err.Error(), http.StatusConflict)
			return
		}
	} else {
		session = activeStreams.get(threadID)
	}

	flusher, ok := ensureSSEHeaders(w)
	if !ok {
		common.ReplyErr(w, "streaming not supported", http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)

	streamStoredRecords(r, w, flusher, db, threadID, streamKindMessage, "", afterID, session)
}

func StreamThreadEvents(w http.ResponseWriter, r *http.Request) {
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}

	threadID := strings.TrimSpace(mux.Vars(r)["thread_id"])
	if _, err := loadThread(db, threadID); err != nil {
		replyThreadLoadError(w, err)
		return
	}

	resp, err := openThreadEventsStream(r.Context(), r, threadID)
	if err != nil {
		common.ReplyErrWithData(w, "open upstream thread events stream failed", map[string]any{"detail": err.Error()}, http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	flusher, ok := ensureSSEHeaders(w)
	if !ok {
		common.ReplyErr(w, "streaming not supported", http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusOK)

	if err := streamUpstreamThreadEvents(r.Context(), w, flusher, db, threadID, resp.Body); err != nil {
		log.Logger.Warn().Err(err).Str("thread_id", threadID).Msg("consume upstream thread events stream failed")
	}
}

func GetThreadResultDatasets(w http.ResponseWriter, r *http.Request) {
	getThreadResults(w, r, "datasets")
}
func GetThreadResultEvalReports(w http.ResponseWriter, r *http.Request) {
	getThreadResults(w, r, "eval-reports")
}
func GetThreadResultAnalysisReports(w http.ResponseWriter, r *http.Request) {
	getThreadResults(w, r, "analysis-reports")
}
func GetThreadResultDiffs(w http.ResponseWriter, r *http.Request) { getThreadResults(w, r, "diffs") }
func GetThreadResultAbtests(w http.ResponseWriter, r *http.Request) {
	getThreadResults(w, r, "abtests")
}
func StartThread(w http.ResponseWriter, r *http.Request)  { postThreadAction(w, r, "start") }
func PauseThread(w http.ResponseWriter, r *http.Request)  { postThreadAction(w, r, "pause") }
func CancelThread(w http.ResponseWriter, r *http.Request) { postThreadAction(w, r, "cancel") }
func RetryThread(w http.ResponseWriter, r *http.Request)  { postThreadAction(w, r, "retry") }

func GetReportContent(w http.ResponseWriter, r *http.Request) {
	reportID := strings.TrimSpace(mux.Vars(r)["report_id"])
	if reportID == "" {
		common.ReplyErr(w, "report_id required", http.StatusBadRequest)
		return
	}
	proxy, statusCode, err := fetchUpstreamProxy(r.Context(), r, reportContentURL(reportID, strings.TrimSpace(r.URL.Query().Get("fmt"))))
	if err != nil {
		common.ReplyErrWithData(w, "fetch report content failed", map[string]any{"detail": err.Error()}, statusCode)
		return
	}
	writeProxyResponse(w, proxy)
}

func GetDiffContent(w http.ResponseWriter, r *http.Request) {
	applyID := strings.TrimSpace(mux.Vars(r)["apply_id"])
	filename := strings.TrimSpace(mux.Vars(r)["filename"])
	if applyID == "" || filename == "" {
		common.ReplyErr(w, "apply_id and filename required", http.StatusBadRequest)
		return
	}
	proxy, statusCode, err := fetchUpstreamProxy(r.Context(), r, diffContentURL(applyID, filename))
	if err != nil {
		common.ReplyErrWithData(w, "fetch diff content failed", map[string]any{"detail": err.Error()}, statusCode)
		return
	}
	writeProxyResponse(w, proxy)
}

func GetAgentFileContent(w http.ResponseWriter, r *http.Request) {
	body, _, err := decodeRequestBody(r)
	if err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "invalid body", err), http.StatusBadRequest)
		return
	}
	path := strings.TrimSpace(caseCSVScalarString(body["path"]))
	if path == "" {
		common.ReplyErr(w, "path required", http.StatusBadRequest)
		return
	}
	result, err := buildAgentFileContentResult(path)
	if err != nil {
		common.ReplyErrWithData(w, "read agent file content failed", map[string]any{"detail": err.Error()}, http.StatusInternalServerError)
		return
	}
	common.ReplyJSON(w, result)
}

func getThreadResults(w http.ResponseWriter, r *http.Request, resultKind string) {
	threadID := strings.TrimSpace(mux.Vars(r)["thread_id"])
	if threadID == "" {
		common.ReplyErr(w, "thread_id required", http.StatusBadRequest)
		return
	}
	proxy, statusCode, err := fetchUpstreamProxy(r.Context(), r, threadResultsURL(threadID, resultKind))
	if err != nil {
		common.ReplyErrWithData(w, "fetch thread results failed", map[string]any{"detail": err.Error()}, statusCode)
		return
	}
	if proxy != nil {
		switch resultKind {
		case "datasets":
			if strings.Contains(proxy.ContentType, "application/json") {
				if _, found, csvErr := attachCaseCSVFileURL(r.Context(), proxy.Body, caseCSVOptions{
					ThreadID:   threadID,
					ResultKind: resultKind,
					FieldNames: []string{"case", "cases", "eval_data", "data", "items", "records"},
				}); csvErr != nil {
					log.Logger.Warn().Err(csvErr).Str("thread_id", threadID).Str("result_kind", resultKind).Bool("case_field_found", found).Msg("attach case csv file url failed")
				}
			}
		case "eval-reports", "abtests":
			if strings.Contains(proxy.ContentType, "application/json") {
				if _, found, reportErr := attachCaseDetailsReportResult(r.Context(), proxy.Body, caseDetailsReportOptions{
					ThreadID:   threadID,
					ResultKind: resultKind,
				}); reportErr != nil {
					log.Logger.Warn().Err(reportErr).Str("thread_id", threadID).Str("result_kind", resultKind).Bool("case_details_found", found).Msg("attach case details report result failed")
				}
			}
		case "analysis-reports":
			body, found, resultErr := buildAnalysisMarkdownResult(proxy.Body)
			if resultErr != nil {
				common.ReplyErrWithData(w, "read analysis report content failed", map[string]any{"detail": resultErr.Error()}, http.StatusInternalServerError)
				return
			}
			if found {
				proxy.Body = body
				proxy.ContentType = "application/json"
			}
		case "diffs":
			body, found, resultErr := buildDiffJSONResult(proxy.Body)
			if resultErr != nil {
				common.ReplyErrWithData(w, "read diff result content failed", map[string]any{"detail": resultErr.Error()}, http.StatusInternalServerError)
				return
			}
			if found {
				proxy.Body = body
				proxy.ContentType = "application/json"
			}
		}
	}
	writeProxyResponse(w, proxy)
}

func postThreadAction(w http.ResponseWriter, r *http.Request, action string) {
	threadID := strings.TrimSpace(mux.Vars(r)["thread_id"])
	if threadID == "" {
		common.ReplyErr(w, "thread_id required", http.StatusBadRequest)
		return
	}
	proxy, statusCode, err := postUpstreamProxy(r.Context(), r, threadActionURL(threadID, action))
	if err != nil {
		common.ReplyErrWithData(w, "post thread action failed", map[string]any{"detail": err.Error()}, statusCode)
		return
	}
	writeProxyResponse(w, proxy)
}

type fetchedThreadEvent struct {
	TaskID    string
	EventName string
	RawFrame  string
}

func openThreadEventsStream(ctx context.Context, r *http.Request, threadID string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, threadEventsURL(threadID), nil)
	if err != nil {
		return nil, err
	}
	for key, value := range forwardedUpstreamHeaders(r) {
		if strings.EqualFold(key, "Accept") {
			continue
		}
		req.Header.Set(key, value)
	}
	req.Header.Set("Accept", "text/event-stream")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		defer resp.Body.Close()
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("upstream returned status %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}

	return resp, nil
}

func streamUpstreamThreadEvents(
	ctx context.Context,
	w http.ResponseWriter,
	flusher http.Flusher,
	db *gorm.DB,
	threadID string,
	body io.Reader,
) error {
	reader := bufio.NewReader(body)
	for {
		frame, err := readSSEFrame(reader)
		if err != nil {
			if err == io.EOF || ctx.Err() != nil {
				return nil
			}
			return err
		}
		event, ok := fetchedThreadEventFromSSEFrame(frame)
		if !ok {
			if strings.TrimSpace(frame.Data) == "[DONE]" {
				return nil
			}
			continue
		}

		logUpstreamSSEData(":events", threadID, "", event.TaskID, event.EventName, event.RawFrame)
		if _, _, saveErr := saveThreadRecord(
			db,
			threadID,
			"",
			event.TaskID,
			streamKindThreadEvent,
			event.EventName,
			event.RawFrame,
			event.RawFrame,
		); saveErr != nil {
			log.Logger.Warn().Err(saveErr).Str("thread_id", threadID).Msg("save thread event record failed")
		}

		updates := map[string]any{
			"status":     "event_streaming",
			"updated_at": time.Now().UTC(),
		}
		if event.TaskID != "" {
			updates["current_task_id"] = event.TaskID
		}
		_ = db.Model(&orm.AgentThread{}).Where("thread_id = ?", threadID).Updates(updates).Error

		_, _ = io.WriteString(w, buildThreadEventFrame(event.RawFrame))
		flusher.Flush()
	}
}

func fetchedThreadEventFromSSEFrame(frame *sseFrame) (fetchedThreadEvent, bool) {
	if frame == nil {
		return fetchedThreadEvent{}, false
	}
	rawData := strings.TrimSpace(frame.Data)
	if rawData == "" || rawData == "[DONE]" {
		return fetchedThreadEvent{}, false
	}
	payload := parseJSONValue(rawData)
	eventName := strings.TrimSpace(frame.Event)
	taskID := ""
	if payload != nil {
		taskID = extractStringByExactKeys(payload, "task_id", "current_task_id")
		if name := extractStringByExactKeys(payload, "kind", "event", "type"); name != "" {
			eventName = name
		}
	}
	if shouldSkipStreamData(eventName, payload, rawData) {
		return fetchedThreadEvent{}, false
	}
	return fetchedThreadEvent{
		TaskID:    taskID,
		EventName: eventName,
		RawFrame:  rawData,
	}, true
}

func buildFetchedThreadEvents(events []map[string]any) ([]fetchedThreadEvent, error) {
	result := make([]fetchedThreadEvent, 0, len(events))
	for _, item := range events {
		if item == nil {
			continue
		}
		rawJSON, err := json.Marshal(item)
		if err != nil {
			return nil, err
		}
		eventName := extractStringByExactKeys(item, "kind", "event", "type")
		if shouldSkipStreamData(eventName, item, string(rawJSON)) {
			continue
		}
		result = append(result, fetchedThreadEvent{
			TaskID:    extractStringByExactKeys(item, "task_id", "current_task_id"),
			EventName: eventName,
			RawFrame:  string(rawJSON),
		})
	}
	return result, nil
}

func shouldSkipStreamData(eventName string, payload any, rawData string) bool {
	rawData = strings.TrimSpace(rawData)
	if rawData == "" || rawData == "[DONE]" || rawData == "null" {
		return true
	}
	if strings.EqualFold(strings.TrimSpace(eventName), "heartbeat") {
		return true
	}
	switch value := payload.(type) {
	case map[string]any:
		return len(value) == 0
	case []any:
		return len(value) == 0
	default:
		return false
	}
}

func fetchThreadFlowStatus(ctx context.Context, r *http.Request, threadID string) (*threadFlowStatusResponse, error) {
	headers := forwardedUpstreamHeaders(r)
	var flowStatus threadFlowStatusResponse
	if err := common.ApiGet(ctx, threadFlowStatusURL(threadID), headers, &flowStatus, 15*time.Second); err != nil {
		return nil, err
	}
	return &flowStatus, nil
}

func fetchUpstreamProxy(ctx context.Context, r *http.Request, targetURL string) (*upstreamProxyResponse, int, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, targetURL, nil)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	for key, value := range forwardedUpstreamHeaders(r) {
		req.Header.Set(key, value)
	}

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, http.StatusBadGateway, err
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, http.StatusBadGateway, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, http.StatusBadGateway, fmt.Errorf("%s", strings.TrimSpace(string(bodyBytes)))
	}

	contentType := resp.Header.Get("Content-Type")
	if strings.Contains(contentType, "application/json") {
		var payload any
		if err := json.Unmarshal(bodyBytes, &payload); err == nil {
			return &upstreamProxyResponse{Body: payload, ContentType: "application/json"}, http.StatusOK, nil
		}
	}
	return &upstreamProxyResponse{Body: string(bodyBytes), ContentType: contentType}, http.StatusOK, nil
}

func postUpstreamProxy(ctx context.Context, r *http.Request, targetURL string) (*upstreamProxyResponse, int, error) {
	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil {
		return nil, http.StatusBadRequest, err
	}
	body := strings.TrimSpace(string(bodyBytes))
	var reqBody io.Reader = http.NoBody
	if body != "" {
		reqBody = strings.NewReader(body)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, targetURL, reqBody)
	if err != nil {
		return nil, http.StatusInternalServerError, err
	}
	for key, value := range forwardedUpstreamHeaders(r) {
		req.Header.Set(key, value)
	}
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, http.StatusBadGateway, err
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, http.StatusBadGateway, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, http.StatusBadGateway, fmt.Errorf("%s", strings.TrimSpace(string(respBody)))
	}

	contentType := resp.Header.Get("Content-Type")
	if strings.Contains(contentType, "application/json") {
		var payload any
		if err := json.Unmarshal(respBody, &payload); err == nil {
			return &upstreamProxyResponse{Body: payload, ContentType: "application/json"}, http.StatusOK, nil
		}
	}
	return &upstreamProxyResponse{Body: string(respBody), ContentType: contentType}, http.StatusOK, nil
}

func writeProxyResponse(w http.ResponseWriter, proxy *upstreamProxyResponse) {
	if proxy == nil {
		common.ReplyOK(w, map[string]any{})
		return
	}
	if strings.Contains(proxy.ContentType, "application/json") {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(proxy.Body)
		return
	}
	if proxy.ContentType != "" {
		w.Header().Set("Content-Type", proxy.ContentType)
	} else {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	}
	_, _ = io.WriteString(w, fmt.Sprint(proxy.Body))
}

func streamStoredRecords(
	r *http.Request,
	w http.ResponseWriter,
	flusher http.Flusher,
	db *gorm.DB,
	threadID, streamKind, roundID, afterID string,
	session *activeMessageStream,
) {
	lastSent := afterID

	for {
		if r.Context().Err() != nil {
			return
		}

		records, err := listRecords(db, threadID, streamKind, roundID, lastSent, 200)
		if err != nil {
			log.Logger.Warn().Err(err).Str("thread_id", threadID).Str("stream_kind", streamKind).Msg("load stored stream records failed")
			time.Sleep(500 * time.Millisecond)
			continue
		}
		if len(records) > 0 {
			for _, record := range records {
				lastSent = record.ID
				if shouldSkipStreamRecord(record) {
					continue
				}
				writeReplayFrame(w, flusher, record)
			}
			continue
		}

		if session == nil {
			return
		}
		select {
		case <-session.done:
			if session.Err() != nil {
				return
			}
			if trailing, err := listRecords(db, threadID, streamKind, roundID, lastSent, 200); err == nil {
				for _, record := range trailing {
					lastSent = record.ID
					if shouldSkipStreamRecord(record) {
						continue
					}
					writeReplayFrame(w, flusher, record)
				}
			}
			return
		default:
		}

		time.Sleep(500 * time.Millisecond)
	}
}

func shouldSkipStreamRecord(record orm.AgentThreadRecord) bool {
	rawData := record.RawFrame
	if record.StreamKind == streamKindMessage {
		rawData = recordDataPayload(record)
	}
	return shouldSkipStreamData(record.EventName, parseJSONValue(rawData), rawData)
}

func decodeRequestBody(r *http.Request) (map[string]any, []byte, error) {
	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil {
		return nil, nil, err
	}
	bodyBytes = []byte(strings.TrimSpace(string(bodyBytes)))
	if len(bodyBytes) == 0 {
		return map[string]any{}, []byte("{}"), nil
	}
	var payload map[string]any
	if err := json.Unmarshal(bodyBytes, &payload); err != nil {
		return nil, nil, err
	}
	return payload, bodyBytes, nil
}

func loadThread(db *gorm.DB, threadID string) (orm.AgentThread, error) {
	if threadID == "" {
		return orm.AgentThread{}, errors.New("thread_id required")
	}
	var thread orm.AgentThread
	if err := db.Where("thread_id = ?", threadID).First(&thread).Error; err != nil {
		return orm.AgentThread{}, err
	}
	return thread, nil
}

func upsertThread(
	db *gorm.DB,
	threadID, currentTaskID, status, threadPayload, requestHash, userID, userName string,
) (orm.AgentThread, error) {
	now := time.Now().UTC()
	var thread orm.AgentThread
	err := db.Where("thread_id = ?", threadID).First(&thread).Error
	if err != nil && !errors.Is(err, gorm.ErrRecordNotFound) {
		return orm.AgentThread{}, err
	}
	if errors.Is(err, gorm.ErrRecordNotFound) {
		thread = orm.AgentThread{
			ThreadID:               threadID,
			CurrentTaskID:          currentTaskID,
			Status:                 status,
			ThreadPayload:          threadPayload,
			LastMessageRequestHash: requestHash,
			CreateUserID:           userID,
			CreateUserName:         userName,
			CreatedAt:              now,
			UpdatedAt:              now,
		}
		return thread, db.Create(&thread).Error
	}

	if currentTaskID != "" {
		thread.CurrentTaskID = currentTaskID
	}
	if status != "" {
		thread.Status = status
	}
	if threadPayload != "" {
		thread.ThreadPayload = threadPayload
	}
	if requestHash != "" {
		thread.LastMessageRequestHash = requestHash
	}
	if userID != "" {
		thread.CreateUserID = userID
	}
	if userName != "" {
		thread.CreateUserName = userName
	}
	thread.UpdatedAt = now
	return thread, db.Save(&thread).Error
}

func toThreadResponse(thread orm.AgentThread) threadResponse {
	return threadResponse{
		ThreadID:      thread.ThreadID,
		CurrentTaskID: thread.CurrentTaskID,
		Status:        thread.Status,
		ThreadPayload: threadPayloadValue(thread),
		CreatedAt:     thread.CreatedAt,
		UpdatedAt:     thread.UpdatedAt,
	}
}

func toRecordResponse(record orm.AgentThreadRecord) recordResponse {
	return recordResponse{
		ID:         record.ID,
		ThreadID:   record.ThreadID,
		TaskID:     record.TaskID,
		StreamKind: record.StreamKind,
		EventName:  record.EventName,
		Payload:    recordPayloadValue(record),
		RawFrame:   record.RawFrame,
		CreatedAt:  record.CreatedAt,
	}
}

func replyThreadLoadError(w http.ResponseWriter, err error) {
	switch {
	case err == nil:
		return
	case errors.Is(err, gorm.ErrRecordNotFound):
		common.ReplyErr(w, "thread not found", http.StatusNotFound)
	case err.Error() == "thread_id required":
		common.ReplyErr(w, err.Error(), http.StatusBadRequest)
	default:
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "load thread failed", err), http.StatusInternalServerError)
	}
}
