package chat

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
	"gorm.io/gorm"

	"lazyrag/core/common"
	"lazyrag/core/common/orm"
)

const (
	maxConversationIDLength          = 36
	maxConversationDisplayNameLength = 255
	maxTopK                          = 10
	defaultTopK                      = 3
)

// newID text history text ID。
func newID(prefix string) string {
	return prefix + strconvBase36(time.Now().UnixNano())
}

func strconvBase36(v int64) string {
	const chars = "0123456789abcdefghijklmnopqrstuvwxyz"
	if v == 0 {
		return "0"
	}
	neg := v < 0
	if neg {
		v = -v
	}
	var b [32]byte
	i := len(b)
	for v > 0 && i > 0 {
		i--
		b[i] = chars[v%36]
		v /= 36
	}
	if neg && i > 0 {
		i--
		b[i] = '-'
	}
	return string(b[i:])
}

// GetDefaultDisplayName:
// 1. Use the first non-empty "text" from input.
// 2. Otherwise use the first non-empty "uri".
// 3. Otherwise fall back to conversationID.
// 4. Truncate to at most 255 runes.
func GetDefaultDisplayName(conversationID string, input []map[string]any) string {
	tempContent := ""
	for _, q := range input {
		if t, ok := q["text"].(string); ok && strings.TrimSpace(t) != "" {
			tempContent = strings.TrimSpace(t)
			break
		}
		if tempContent == "" {
			if u, ok := q["uri"].(string); ok && strings.TrimSpace(u) != "" {
				tempContent = strings.TrimSpace(u)
			}
		}
	}
	if tempContent == "" {
		tempContent = conversationID
	}
	runes := []rune(tempContent)
	if len(runes) > maxConversationDisplayNameLength {
		return string(runes[:maxConversationDisplayNameLength])
	}
	return string(runes)
}

func newConversationID() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	out := make([]byte, 36)
	hex.Encode(out[0:8], b[0:4])
	out[8] = '-'
	hex.Encode(out[9:13], b[4:6])
	out[13] = '-'
	hex.Encode(out[14:18], b[6:8])
	out[18] = '-'
	hex.Encode(out[19:23], b[8:10])
	out[23] = '-'
	hex.Encode(out[24:36], b[10:16])
	return string(out)
}

func conversationIDFromName(name string) string {
	name = strings.TrimSpace(name)
	name = strings.TrimPrefix(name, "conversations/")
	name = strings.TrimPrefix(name, "/")
	if idx := strings.Index(name, ":"); idx >= 0 {
		name = name[:idx]
	}
	return name
}

// ensureConversation textCreatetextUsertextConversation，textConversation、text history text seq、error
func ensureConversation(db *gorm.DB, convID, displayName string, searchConfig json.RawMessage, models json.RawMessage, userID, userName string) (*orm.Conversation, int, error) {
	now := time.Now()
	var c orm.Conversation
	err := db.Where("id = ? AND create_user_id = ?", convID, userID).First(&c).Error
	if err == nil {
		var count int64
		db.Model(&orm.ChatHistory{}).Where("conversation_id = ?", convID).Count(&count)

		updates := map[string]any{}
		if len(searchConfig) > 0 && (len(c.SearchConfig) == 0 || string(c.SearchConfig) == "{}") {
			updates["search_config"] = searchConfig
		}
		if len(models) > 0 && len(c.Models) == 0 {
			updates["models"] = models
		}
		if displayName != "" && c.DisplayName == "" {
			updates["display_name"] = displayName
		}
		if len(updates) > 0 {
			db.Model(&orm.Conversation{}).Where("id = ?", c.ID).Updates(updates)
		}

		return &c, int(count) + 1, nil
	}
	if err != gorm.ErrRecordNotFound {
		return nil, 0, err
	}
	c = orm.Conversation{
		ID:           convID,
		DisplayName:  displayName,
		ChannelID:    "default",
		SearchConfig: searchConfig,
		Models:       models,
		ChatTimes:    0,
		BaseModel: orm.BaseModel{
			CreateUserID:   userID,
			CreateUserName: userName,
			CreatedAt:      now,
			UpdatedAt:      now,
		},
	}
	if err := db.Create(&c).Error; err != nil {
		return nil, 0, err
	}
	return &c, 1, nil
}

func buildHistoryMessages(histories []orm.ChatHistory) []map[string]string {
	if len(histories) == 0 {
		return nil
	}
	out := make([]map[string]string, 0, len(histories)*2)
	for _, h := range histories {
		out = append(out, map[string]string{"role": "user", "content": h.RawContent})
		out = append(out, map[string]string{"role": "assistant", "content": h.Result})
	}
	return out
}

const chatActionRegeneration = "CHAT_ACTION_REGENERATION"

type chatPersistTarget struct {
	HistoryID      string
	Seq            int
	Existing       *orm.ChatHistory
	IsRegeneration bool
}

func parseChatAction(raw map[string]any) string {
	if action, ok := raw["action"].(string); ok {
		return strings.TrimSpace(action)
	}
	return ""
}

func resolvePersistTarget(histories []orm.ChatHistory, raw map[string]any, nextSeq int) chatPersistTarget {
	target := chatPersistTarget{Seq: nextSeq}
	if parseChatAction(raw) != chatActionRegeneration || len(histories) == 0 {
		return target
	}
	last := histories[len(histories)-1]
	target.HistoryID = last.ID
	target.Seq = last.Seq
	target.IsRegeneration = true
	target.Existing = &last
	return target
}

func historiesForUpstream(histories []orm.ChatHistory, target chatPersistTarget) []orm.ChatHistory {
	if !target.IsRegeneration || len(histories) == 0 {
		return histories
	}
	return histories[:len(histories)-1]
}

func setConversationDefaultValue(raw map[string]any) {
	if raw["conversation"] == nil {
		raw["conversation"] = map[string]any{}
	}
	conv, _ := raw["conversation"].(map[string]any)
	if conv["search_config"] == nil {
		conv["search_config"] = map[string]any{}
	}
	sc, _ := conv["search_config"].(map[string]any)
	if topK, ok := sc["top_k"].(float64); !ok || topK < 1 || topK > maxTopK {
		sc["top_k"] = defaultTopK
	}
	if conf, ok := sc["confidence"].(float64); !ok || conf < 0 || conf > 1 {
		sc["confidence"] = 0.5
	}
}

func checkInput(raw map[string]any) bool {
	in, ok := raw["input"].([]any)
	if !ok || len(in) == 0 {
		return raw["query"] != nil || raw["content"] != nil
	}
	for _, it := range in {
		m, _ := it.(map[string]any)
		if m == nil {
			continue
		}
		if s, _ := m["text"].(string); strings.TrimSpace(s) != "" {
			return true
		}
		if s, _ := m["content"].(string); strings.TrimSpace(s) != "" {
			return true
		}
		if _, hasURI := m["uri"]; hasURI {
			return true
		}
	}
	return false
}

func checkSearchConfig(raw map[string]any) bool {
	conv, _ := raw["conversation"].(map[string]any)
	if conv == nil {
		return true
	}
	sc, _ := conv["search_config"].(map[string]any)
	if sc == nil {
		return true
	}
	if topK, ok := sc["top_k"].(float64); ok && (topK < 1 || topK > maxTopK) {
		return false
	}
	if conf, ok := sc["confidence"].(float64); ok && (conf < 0 || conf > 1) {
		return false
	}
	return true
}

func buildChatRequestBody(convID, query string, histories []orm.ChatHistory, raw map[string]any) map[string]any {
	body := map[string]any{
		"query":           query,
		"session_id":      convID,
		"history":         buildHistoryMessages(histories),
		"filters":         raw["filters"],
		"files":           raw["files"],
		"databases":       raw["databases"],
		"debug":           raw["debug"],
		"reasoning":       raw["reasoning"],
		"priority":        raw["priority"],
		"enable_thinking": raw["enable_thinking"],
	}
	if body["filters"] == nil {
		conv, _ := raw["conversation"].(map[string]any)
		if conv != nil {
			if sc, _ := conv["search_config"].(map[string]any); sc != nil {
				if ids, ok := sc["dataset_ids"].([]any); ok && len(ids) > 0 {
					kbID := make([]string, 0, len(ids))
					for _, id := range ids {
						if s, ok := id.(string); ok {
							kbID = append(kbID, s)
						}
					}
					body["filters"] = map[string]any{"kb_id": kbID}
				}
			}
		}
	}
	return body
}

func handleNonStreamChat(
	w http.ResponseWriter,
	reqCtx context.Context,
	db *gorm.DB,
	rdb *redis.Client,
	baseURL string,
	reqBody map[string]any,
	convID, query string,
	target chatPersistTarget,
) {
	pyBody, _ := json.Marshal(reqBody)
	upstreamURL := baseURL + "/api/chat"
	fmt.Printf("DEBUG upstream request url=%s params=%+v\n", upstreamURL, reqBody)
	respBytes, statusCode, err := common.HTTPPost(reqCtx, upstreamURL, "application/json", pyBody)
	if err != nil {
		fmt.Println("DEBUG upstream request failed url=", upstreamURL, " err=", err)
		common.ReplyErr(w, fmt.Sprintf("%s: %v", "chat service unavailable", err), http.StatusBadGateway)
		return
	}
	fmt.Println("DEBUG upstream response url=", upstreamURL, " status=", statusCode)
	var pyResp struct {
		Code int             `json:"code"`
		Msg  string          `json:"msg"`
		Data json.RawMessage `json:"data"`
	}
	_ = json.Unmarshal(respBytes, &pyResp)
	answer := ""
	if pyResp.Code == 200 && len(pyResp.Data) > 0 {
		var data struct {
			Text string `json:"text"`
		}
		if json.Unmarshal(pyResp.Data, &data) == nil {
			answer = strings.TrimSpace(data.Text)
		}
		if answer == "" {
			answer = strings.TrimSpace(string(pyResp.Data))
		}
	}
	if pyResp.Code != 200 {
		answer = "error: " + pyResp.Msg
	}
	historyID := target.HistoryID
	if historyID == "" {
		historyID = newID("h_")
	}
	now := time.Now()
	hist := orm.ChatHistory{
		ID:             historyID,
		Seq:            target.Seq,
		ConversationID: convID,
		RawContent:     query,
		Content:        query,
		Result:         answer,
		FeedBack:       0,
		Reason:         "",
		ExpectedAnswer: "",
		Ext:            nil,
		TimeMixin:      orm.TimeMixin{CreateTime: now, UpdateTime: now},
	}
	if target.IsRegeneration && target.Existing != nil {
		hist.TimeMixin.CreateTime = target.Existing.CreateTime
		if err := db.Model(&orm.ChatHistory{}).Where("id = ?", historyID).Updates(map[string]any{
			"seq":              target.Seq,
			"raw_content":      query,
			"content":          query,
			"result":           answer,
			"retrieval_result": nil,
			"feed_back":        0,
			"reason":           "",
			"expected_answer":  "",
			"ext":              nil,
			"update_time":      now,
		}).Error; err != nil {
			common.ReplyErr(w, "failed to update history", http.StatusInternalServerError)
			return
		}
	} else {
		if err := db.Create(&hist).Error; err != nil {
			common.ReplyErr(w, fmt.Sprintf("%s: %v", "failed to save history", err), http.StatusInternalServerError)
			return
		}
	}
	if rdb != nil {
		_ = setChatStatus(reqCtx, rdb, convID, historyID, "completed", answer)
	}
	db.Model(&orm.Conversation{}).Where("id = ?", convID).Update("updated_at", now)
	if !target.IsRegeneration {
		if !target.IsRegeneration {
			db.Model(&orm.Conversation{}).Where("id = ?", convID).UpdateColumn("chat_times", gorm.Expr("chat_times + ?", 1))
		}
	}
	common.ReplyOK(w, map[string]any{
		"conversation_id": convID,
		"seq":             target.Seq,
		"message":         answer,
		"delta":           "",
		"finish_reason":   "FINISH_REASON_STOP",
		"history_id":      historyID,
	})
}

func handleStreamChat(
	w http.ResponseWriter,
	r *http.Request,
	db *gorm.DB,
	rdb *redis.Client,
	baseURL string,
	reqBody map[string]any,
	convID, query string,
	target chatPersistTarget,
	dualReply bool,
) {
	reqCtx := r.Context()
	flusher, ok := w.(http.Flusher)
	if !ok {
		common.ReplyErr(w, "streaming not supported", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.WriteHeader(http.StatusOK)

	historyID := target.HistoryID
	if historyID == "" {
		historyID = newID("h_")
	}
	secondaryHistoryID := ""
	if dualReply {
		secondaryHistoryID = newID("h_")
	}
	chatCtx, chatCancel := context.WithCancel(context.Background())
	defer chatCancel()
	if rdb != nil {
		if target.IsRegeneration {
			_ = clearChatData(chatCtx, rdb, convID, historyID)
		}
		_ = setChatInput(chatCtx, rdb, convID, historyID, query, target.Seq)
		_ = setChatStatus(chatCtx, rdb, convID, historyID, "generating", "")
		if dualReply {
			_ = setChatStatus(chatCtx, rdb, convID, secondaryHistoryID, "generating", "")
			_ = setMultiAnswerInfo(chatCtx, rdb, convID, historyID, secondaryHistoryID, target.Seq)
		}
		go func() {
			_ = watchChatCancelSignal(chatCtx, rdb, convID, historyID)
			chatCancel()
		}()
	}

	if !dualReply {
		streamSingleAnswer(chatCtx, reqCtx, w, flusher, db, rdb, baseURL, reqBody, convID, query, historyID, target)
		return
	}
	streamDualAnswer(chatCtx, reqCtx, w, flusher, db, rdb, baseURL, reqBody, convID, query, historyID, secondaryHistoryID, target)
}

func streamSingleAnswer(
	chatCtx, reqCtx context.Context,
	w http.ResponseWriter,
	flusher http.Flusher,
	db *gorm.DB,
	rdb *redis.Client,
	baseURL string,
	reqBody map[string]any,
	convID, query, historyID string,
	target chatPersistTarget,
) {
	seq := target.Seq
	ch, err := StreamChatUpstream(chatCtx, baseURL, reqBody)
	if err != nil {
		if rdb != nil {
			_ = setChatStatus(chatCtx, rdb, convID, historyID, "failed", "")
		}
		writeSSEChunk(w, flusher, &ChatChunkResponse{
			ConversationID:    convID,
			Seq:               int32(seq),
			Message:           "",
			Delta:             "",
			FinishReason:      "FINISH_REASON_UNKNOWN",
			HistoryID:         historyID,
			Sources:           nil,
			PromptQuestions:   []string{},
			ReasoningContent:  "",
			ThinkingDurationS: 0,
		})
		return
	}
	var fullText string
	var fullReasoning string
	var sources []any
	thinkingDone := false
	thinkStart := time.Now()
	// text：textConversation/text，finish_reason text UNSPECIFIED
	writeSSEChunk(w, flusher, &ChatChunkResponse{
		ConversationID:    convID,
		Seq:               int32(seq),
		Message:           "",
		Delta:             "",
		FinishReason:      "FINISH_REASON_UNSPECIFIED",
		HistoryID:         historyID,
		Sources:           nil,
		PromptQuestions:   []string{},
		ReasoningContent:  "",
		ThinkingDurationS: 0,
	})
	for d := range ch {
		fullText += d.Text
		fullReasoning += d.ReasoningText
		if len(d.Sources) > 0 {
			sources = d.Sources
		}
		if d.Text != "" && !thinkingDone {
			thinkingDone = true
		}
		thinkingDurationS := int64(0)
		if thinkingDone {
			thinkingDurationS = int64(time.Since(thinkStart).Seconds())
		}
		deltaToSend := d.Text
		if !thinkingDone {
			deltaToSend = ""
		}
		chunk := &ChatChunkResponse{
			ConversationID:    convID,
			Seq:               int32(seq),
			Message:           "",
			Delta:             deltaToSend,
			FinishReason:      "FINISH_REASON_UNSPECIFIED",
			HistoryID:         historyID,
			Sources:           sources,
			PromptQuestions:   []string{},
			ReasoningContent:  d.ReasoningText,
			ThinkingDurationS: thinkingDurationS,
		}
		if reqCtx.Err() == nil {
			writeSSEChunk(w, flusher, chunk)
		}
		if rdb != nil {
			_ = appendChatChunk(chatCtx, rdb, convID, historyID, chunk)
		}
	}
	now := time.Now()
	extPayload, _ := json.Marshal(map[string]any{
		"reasoning_content": fullReasoning,
	})
	if target.IsRegeneration && target.Existing != nil {
		_ = db.Model(&orm.ChatHistory{}).Where("id = ?", historyID).Updates(map[string]any{
			"seq":              seq,
			"raw_content":      query,
			"content":          query,
			"result":           fullText,
			"retrieval_result": nil,
			"feed_back":        0,
			"reason":           "",
			"expected_answer":  "",
			"ext":              extPayload,
			"update_time":      now,
		}).Error
	} else {
		_ = db.Create(&orm.ChatHistory{
			ID:             historyID,
			Seq:            seq,
			ConversationID: convID,
			RawContent:     query,
			Content:        query,
			Result:         fullText,
			Ext:            extPayload,
			TimeMixin:      orm.TimeMixin{CreateTime: now, UpdateTime: now},
		}).Error
	}
	if rdb != nil {
		_ = setChatStatus(context.Background(), rdb, convID, historyID, "completed", fullText)
	}
	db.Model(&orm.Conversation{}).Where("id = ?", convID).Update("updated_at", now)
	if !target.IsRegeneration {
		db.Model(&orm.Conversation{}).Where("id = ?", convID).UpdateColumn("chat_times", gorm.Expr("chat_times + ?", 1))
	}
	if reqCtx.Err() == nil {
		// text：message text，finish_reason text STOP
		writeSSEChunk(w, flusher, &ChatChunkResponse{
			ConversationID:    convID,
			Seq:               int32(seq),
			Message:           fullText,
			Delta:             "",
			FinishReason:      "FINISH_REASON_STOP",
			HistoryID:         historyID,
			Sources:           sources,
			PromptQuestions:   []string{},
			ReasoningContent:  fullReasoning,
			ThinkingDurationS: int64(time.Since(thinkStart).Seconds()),
		})
		_, _ = w.Write([]byte("data: [DONE]\n\n"))
		flusher.Flush()
	}
}

func streamDualAnswer(
	chatCtx, reqCtx context.Context,
	w http.ResponseWriter,
	flusher http.Flusher,
	db *gorm.DB,
	rdb *redis.Client,
	baseURL string,
	reqBody map[string]any,
	convID, query, historyID, secondaryHistoryID string,
	target chatPersistTarget,
) {
	seq := target.Seq
	primaryCh, err1 := StreamChatUpstream(chatCtx, baseURL, reqBody)
	secondaryReq := make(map[string]any)
	for k, v := range reqBody {
		secondaryReq[k] = v
	}
	if sc, ok := secondaryReq["filters"].(map[string]any); ok {
		sc["kb_id"] = nil
	}
	secondaryCh, err2 := StreamChatUpstream(chatCtx, baseURL, secondaryReq)
	if err1 != nil && err2 != nil {
		if rdb != nil {
			_ = setChatStatus(chatCtx, rdb, convID, historyID, "failed", "")
			_ = setChatStatus(chatCtx, rdb, convID, secondaryHistoryID, "failed", "")
		}
		writeSSEChunk(w, flusher, map[string]any{"finish_reason": "FINISH_REASON_UNKNOWN"})
		return
	}
	if err1 != nil {
		primaryCh = nil
	}
	if err2 != nil {
		secondaryCh = nil
	}
	writeSSEChunk(w, flusher, map[string]any{"conversation_id": convID, "seq": seq, "delta": "", "history_id": historyID})
	writeSSEChunk(w, flusher, map[string]any{"conversation_id": convID, "seq": seq, "delta": "", "history_id": secondaryHistoryID})

	var primaryResult, secondaryResult string
	primaryDone := primaryCh == nil
	secondaryDone := secondaryCh == nil
	var writeMu sync.Mutex
	appendPrimary := func(delta, reasoning string, sources []any) {
		primaryResult += delta
		if reqCtx.Err() == nil {
			writeMu.Lock()
			writeSSEChunk(w, flusher, map[string]any{
				"conversation_id": convID, "seq": seq, "delta": delta, "history_id": historyID,
				"reasoning_content": reasoning, "sources": sources,
			})
			writeMu.Unlock()
		}
		if rdb != nil {
			_ = appendChatChunk(chatCtx, rdb, convID, historyID, &ChatChunkResponse{
				ConversationID: convID, Seq: int32(seq), Delta: delta, HistoryID: historyID,
				ReasoningContent: reasoning, Sources: sources,
			})
		}
	}
	appendSecondary := func(delta, reasoning string, sources []any) {
		secondaryResult += delta
		if reqCtx.Err() == nil {
			writeMu.Lock()
			writeSSEChunk(w, flusher, map[string]any{
				"conversation_id": convID, "seq": seq, "delta": delta, "history_id": secondaryHistoryID,
				"reasoning_content": reasoning, "sources": sources,
			})
			writeMu.Unlock()
		}
		if rdb != nil {
			_ = appendChatChunk(chatCtx, rdb, convID, secondaryHistoryID, &ChatChunkResponse{
				ConversationID: convID, Seq: int32(seq), Delta: delta, HistoryID: secondaryHistoryID,
				ReasoningContent: reasoning, Sources: sources,
			})
		}
	}
	for !primaryDone || !secondaryDone {
		select {
		case d, ok := <-primaryCh:
			if !ok {
				primaryDone = true
				continue
			}
			appendPrimary(d.Text, d.ReasoningText, d.Sources)
		case d, ok := <-secondaryCh:
			if !ok {
				secondaryDone = true
				continue
			}
			appendSecondary(d.Text, d.ReasoningText, d.Sources)
		case <-reqCtx.Done():
			bg := context.Background()
			for !primaryDone || !secondaryDone {
				select {
				case d, ok := <-primaryCh:
					if !ok {
						primaryDone = true
						primaryCh = nil
					} else {
						primaryResult += d.Text
						if rdb != nil {
							_ = appendChatChunk(bg, rdb, convID, historyID, &ChatChunkResponse{
								ConversationID: convID, Seq: int32(seq), Delta: d.Text, HistoryID: historyID,
								ReasoningContent: d.ReasoningText, Sources: d.Sources,
							})
						}
					}
				case d, ok := <-secondaryCh:
					if !ok {
						secondaryDone = true
						secondaryCh = nil
					} else {
						secondaryResult += d.Text
						if rdb != nil {
							_ = appendChatChunk(bg, rdb, convID, secondaryHistoryID, &ChatChunkResponse{
								ConversationID: convID, Seq: int32(seq), Delta: d.Text, HistoryID: secondaryHistoryID,
								ReasoningContent: d.ReasoningText, Sources: d.Sources,
							})
						}
					}
				}
			}
			goto dualPersist
		}
	}
dualPersist:
	now := time.Now()
	_ = db.Create(&orm.MultiAnswersChatHistory{
		ID: historyID, Seq: seq, ConversationID: convID, RawContent: query, Content: query, Result: primaryResult,
		TimeMixin: orm.TimeMixin{CreateTime: now, UpdateTime: now},
	}).Error
	_ = db.Create(&orm.MultiAnswersChatHistory{
		ID: secondaryHistoryID, Seq: seq, ConversationID: convID, RawContent: query, Content: query, Result: secondaryResult,
		TimeMixin: orm.TimeMixin{CreateTime: now, UpdateTime: now},
	}).Error
	if rdb != nil {
		_ = setChatStatus(context.Background(), rdb, convID, historyID, "completed", primaryResult)
		_ = setChatStatus(context.Background(), rdb, convID, secondaryHistoryID, "completed", secondaryResult)
	}
	db.Model(&orm.Conversation{}).Where("id = ?", convID).Update("updated_at", now)
	if !target.IsRegeneration {
		db.Model(&orm.Conversation{}).Where("id = ?", convID).UpdateColumn("chat_times", gorm.Expr("chat_times + ?", 1))
	}
	if reqCtx.Err() == nil {
		writeSSEChunk(w, flusher, map[string]any{"finish_reason": "FINISH_REASON_STOP", "history_id": historyID})
		writeSSEChunk(w, flusher, map[string]any{"finish_reason": "FINISH_REASON_STOP", "history_id": secondaryHistoryID})
		_, _ = w.Write([]byte("data: [DONE]\n\n"))
		flusher.Flush()
	}
}
