package agent

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"gorm.io/gorm"

	"lazyrag/core/common/orm"
	"lazyrag/core/log"
)

type activeMessageStream struct {
	threadID    string
	roundID     string
	requestHash string
	done        chan struct{}

	mu  sync.RWMutex
	err error
}

func (s *activeMessageStream) setErr(err error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.err = err
}

func (s *activeMessageStream) Err() error {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.err
}

type messageStreamRegistry struct {
	mu       sync.Mutex
	sessions map[string]*activeMessageStream
}

var activeStreams = &messageStreamRegistry{
	sessions: make(map[string]*activeMessageStream),
}

func (r *messageStreamRegistry) get(threadID string) *activeMessageStream {
	r.mu.Lock()
	defer r.mu.Unlock()
	session := r.sessions[threadID]
	if session == nil {
		return nil
	}
	select {
	case <-session.done:
		delete(r.sessions, threadID)
		return nil
	default:
		return session
	}
}

func (r *messageStreamRegistry) put(threadID string, session *activeMessageStream) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	if current := r.sessions[threadID]; current != nil {
		select {
		case <-current.done:
			delete(r.sessions, threadID)
		default:
			return false
		}
	}
	r.sessions[threadID] = session
	return true
}

func (r *messageStreamRegistry) delete(threadID string, session *activeMessageStream) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if current := r.sessions[threadID]; current == session {
		delete(r.sessions, threadID)
	}
}

func ensureMessageStream(
	db *gorm.DB,
	thread orm.AgentThread,
	requestBody []byte,
	headers map[string]string,
) (*activeMessageStream, error) {
	requestHash := sha256Hex(string(requestBody))
	if existing := activeStreams.get(thread.ThreadID); existing != nil {
		if existing.requestHash != requestHash {
			return nil, fmt.Errorf("thread already has an active messages stream")
		}
		return existing, nil
	}

	resp, err := openMessageStream(thread.ThreadID, requestBody, headers)
	if err != nil {
		return nil, err
	}

	round, err := createThreadRound(db, thread.ThreadID, requestHash, requestBody)
	if err != nil {
		_ = resp.Body.Close()
		return nil, err
	}

	session := &activeMessageStream{
		threadID:    thread.ThreadID,
		roundID:     round.RoundID,
		requestHash: requestHash,
		done:        make(chan struct{}),
	}
	if !activeStreams.put(thread.ThreadID, session) {
		_ = resp.Body.Close()
		if existing := activeStreams.get(thread.ThreadID); existing != nil {
			if existing.requestHash != requestHash {
				return nil, fmt.Errorf("thread already has an active messages stream")
			}
			return existing, nil
		}
		return ensureMessageStream(db, thread, requestBody, headers)
	}

	now := time.Now().UTC()
	_ = db.Model(&orm.AgentThread{}).
		Where("thread_id = ?", thread.ThreadID).
		Updates(map[string]any{
			"status":                    "message_streaming",
			"last_message_request_hash": requestHash,
			"updated_at":                now,
		}).Error

	go consumeMessageStream(db, session, thread.ThreadID, resp)
	return session, nil
}

func openMessageStream(threadID string, requestBody []byte, headers map[string]string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(context.Background(), http.MethodPost, threadMessagesURL(threadID), bytes.NewReader(requestBody))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")
	for key, value := range headers {
		if strings.EqualFold(key, "Accept") {
			continue
		}
		req.Header.Set(key, value)
	}

	client := &http.Client{Timeout: 10 * time.Minute}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		defer resp.Body.Close()
		var payload any
		if err := json.NewDecoder(resp.Body).Decode(&payload); err == nil {
			return nil, fmt.Errorf("upstream messages request failed: %v", payload)
		}
		return nil, fmt.Errorf("upstream messages request failed with status %d", resp.StatusCode)
	}
	return resp, nil
}

func consumeMessageStream(db *gorm.DB, session *activeMessageStream, threadID string, resp *http.Response) {
	defer func() {
		_ = resp.Body.Close()
		activeStreams.delete(threadID, session)
		close(session.done)
	}()

	reader := bufio.NewReader(resp.Body)
	status := "completed"
	var assistantMessage strings.Builder
	for {
		frame, err := readSSEFrame(reader)
		if err != nil {
			if err != io.EOF {
				status = "failed"
				session.setErr(err)
				log.Logger.Error().Err(err).Str("thread_id", threadID).Msg("consume upstream message stream failed")
			}
			break
		}

		taskID := ""
		if payload := parseJSONValue(frame.Data); payload != nil {
			taskID = extractStringByKeys(payload, "task_id", "current_task_id")
		}
		if delta := extractAssistantTextFromFrameData(frame.Data); delta != "" {
			assistantMessage.WriteString(delta)
		}
		if _, _, saveErr := saveThreadRecord(db, threadID, session.roundID, taskID, streamKindMessage, frame.Event, frame.Data, frame.Raw); saveErr != nil {
			status = "failed"
			session.setErr(saveErr)
			log.Logger.Error().Err(saveErr).Str("thread_id", threadID).Msg("save message stream record failed")
			break
		}

		updates := map[string]any{
			"status":     "message_streaming",
			"updated_at": time.Now().UTC(),
		}
		if taskID != "" {
			updates["current_task_id"] = taskID
		}
		_ = db.Model(&orm.AgentThread{}).Where("thread_id = ?", threadID).Updates(updates).Error

		roundUpdates := map[string]any{
			"assistant_message": assistantMessage.String(),
			"status":            "streaming",
			"updated_at":        time.Now().UTC(),
		}
		if taskID != "" {
			roundUpdates["task_id"] = taskID
		}
		_ = db.Model(&orm.AgentThreadRound{}).Where("round_id = ?", session.roundID).Updates(roundUpdates).Error

		if strings.TrimSpace(frame.Data) == "[DONE]" {
			break
		}
	}

	updates := map[string]any{
		"status":     status,
		"updated_at": time.Now().UTC(),
	}
	_ = db.Model(&orm.AgentThread{}).Where("thread_id = ?", threadID).Updates(updates).Error
	_ = db.Model(&orm.AgentThreadRound{}).Where("round_id = ?", session.roundID).Updates(map[string]any{
		"assistant_message": assistantMessage.String(),
		"status":            status,
		"updated_at":        time.Now().UTC(),
	}).Error
}
