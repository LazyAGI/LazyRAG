package agent

import (
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/gorilla/mux"
	"gorm.io/gorm"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/store"
)

type threadRoundResponse struct {
	RoundID          string           `json:"round_id"`
	ThreadID         string           `json:"thread_id"`
	TaskID           string           `json:"task_id,omitempty"`
	Status           string           `json:"status"`
	UserMessage      string           `json:"user_message,omitempty"`
	AssistantMessage string           `json:"assistant_message,omitempty"`
	RequestPayload   any              `json:"request_payload,omitempty"`
	Records          []recordResponse `json:"records,omitempty"`
	CreatedAt        time.Time        `json:"created_at"`
	UpdatedAt        time.Time        `json:"updated_at"`
}

type threadEventHistoryResponse struct {
	ThreadID  string `json:"thread_id"`
	TaskID    string `json:"task_id,omitempty"`
	EventName string `json:"event_name,omitempty"`
	Payload   any    `json:"payload"`
	RawFrame  string `json:"raw_frame"`
}

type threadHistoryResponse struct {
	ThreadID     string                       `json:"thread_id"`
	Rounds       []threadRoundResponse        `json:"rounds"`
	ThreadEvents []threadEventHistoryResponse `json:"thread_events"`
}

func GetThreadHistory(w http.ResponseWriter, r *http.Request) {
	listThreadHistory(w, r)
}

func ListThreadRounds(w http.ResponseWriter, r *http.Request) {
	listThreadHistory(w, r)
}

func listThreadHistory(w http.ResponseWriter, r *http.Request) {
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

	rounds, err := listThreadRounds(db, threadID)
	if err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "list thread rounds failed", err), http.StatusInternalServerError)
		return
	}

	roundIDs := make([]string, 0, len(rounds))
	for _, round := range rounds {
		roundIDs = append(roundIDs, round.RoundID)
	}
	recordsByRound, err := listRoundRecords(db, roundIDs)
	if err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "list round records failed", err), http.StatusInternalServerError)
		return
	}

	items := make([]threadRoundResponse, 0, len(rounds))
	for _, round := range rounds {
		records := recordsByRound[round.RoundID]
		recordItems := make([]recordResponse, 0, len(records))
		for _, record := range records {
			recordItems = append(recordItems, toRecordResponse(record))
		}
		items = append(items, threadRoundResponse{
			RoundID:          round.RoundID,
			ThreadID:         round.ThreadID,
			TaskID:           round.TaskID,
			Status:           round.Status,
			UserMessage:      round.UserMessage,
			AssistantMessage: round.AssistantMessage,
			RequestPayload:   parseJSONValue(round.RequestPayload),
			Records:          recordItems,
			CreatedAt:        round.CreatedAt,
			UpdatedAt:        round.UpdatedAt,
		})
	}

	threadEvents := loadThreadHistoryEvents(db, threadID)

	common.ReplyOK(w, threadHistoryResponse{
		ThreadID:     threadID,
		Rounds:       items,
		ThreadEvents: threadEvents,
	})
}

func DeleteThreadHistory(w http.ResponseWriter, r *http.Request) {
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

	if stream := activeStreams.get(threadID); stream != nil {
		common.ReplyErr(w, "thread has active message stream", http.StatusConflict)
		return
	}

	result, err := deleteThreadHistory(db, threadID)
	if err != nil {
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "delete thread history failed", err), http.StatusInternalServerError)
		return
	}
	common.ReplyOK(w, result)
}

func createThreadRound(db *gorm.DB, threadID, requestHash string, requestBody []byte) (orm.AgentThreadRound, error) {
	now := time.Now().UTC()
	round := orm.AgentThreadRound{
		RoundID:        newStreamRecordID(),
		ThreadID:       threadID,
		RequestHash:    requestHash,
		Status:         "streaming",
		UserMessage:    extractUserMessageFromRequestBody(requestBody),
		RequestPayload: strings.TrimSpace(string(requestBody)),
		CreatedAt:      now,
		UpdatedAt:      now,
	}
	return round, db.Create(&round).Error
}

func listThreadRounds(db *gorm.DB, threadID string) ([]orm.AgentThreadRound, error) {
	var rounds []orm.AgentThreadRound
	if err := db.Where("thread_id = ?", threadID).Order("created_at ASC").Find(&rounds).Error; err != nil {
		return nil, err
	}
	return rounds, nil
}

func loadThreadHistoryEvents(db *gorm.DB, threadID string) []threadEventHistoryResponse {
	var records []orm.AgentThreadRecord
	if dbErr := db.Where("thread_id = ? AND stream_kind = ?", threadID, streamKindThreadEvent).Order("id ASC").Find(&records).Error; dbErr != nil {
		return nil
	}
	items := make([]threadEventHistoryResponse, 0, len(records))
	for _, record := range records {
		items = append(items, threadEventHistoryResponse{
			ThreadID:  threadID,
			TaskID:    record.TaskID,
			EventName: record.EventName,
			Payload:   recordPayloadValue(record),
			RawFrame:  record.RawFrame,
		})
	}
	return items
}

func deleteThreadHistory(db *gorm.DB, threadID string) (map[string]any, error) {
	result := map[string]any{"thread_id": threadID}
	err := db.Transaction(func(tx *gorm.DB) error {
		var recordDeleted int64
		if deleted := tx.Where("thread_id = ?", threadID).Delete(&orm.AgentThreadRecord{}); deleted.Error != nil {
			return deleted.Error
		} else {
			recordDeleted = deleted.RowsAffected
		}

		var roundDeleted int64
		if deleted := tx.Where("thread_id = ?", threadID).Delete(&orm.AgentThreadRound{}); deleted.Error != nil {
			return deleted.Error
		} else {
			roundDeleted = deleted.RowsAffected
		}

		var threadDeleted int64
		if deleted := tx.Where("thread_id = ?", threadID).Delete(&orm.AgentThread{}); deleted.Error != nil {
			return deleted.Error
		} else {
			threadDeleted = deleted.RowsAffected
		}

		result["deleted_records"] = recordDeleted
		result["deleted_rounds"] = roundDeleted
		result["deleted_threads"] = threadDeleted
		return nil
	})
	if err != nil {
		return nil, err
	}
	return result, nil
}
