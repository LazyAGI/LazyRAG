package chat

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/mux"
	"github.com/redis/go-redis/v9"
	"gorm.io/gorm"

	"lazyrag/core/acl"
	"lazyrag/core/common"
	"lazyrag/core/common/orm"
	"lazyrag/core/store"
)

// writeSSEChunk 写一条 SSE 行： data: {json}\n\n
func writeSSEChunk(w http.ResponseWriter, flusher http.Flusher, v any) {
	b, _ := json.Marshal(v)
	_, _ = w.Write([]byte("data: "))
	_, _ = w.Write(b)
	_, _ = w.Write([]byte("\n\n"))
	if flusher != nil {
		flusher.Flush()
	}
}

// Chat 对齐 neutrino 的 chat 主入口；当前复用 conversations:chat 能力，作为统一实现。
func Chat(w http.ResponseWriter, r *http.Request) {
	ChatConversations(w, r)
}

// ChatConversations 对应 POST /api/v1/conversations:chat
// 1:1 复刻 neutrino ragservice 逻辑：流式/非流式、双回复、刷新不断流（与 ResumeChat/StopChatGeneration 配合）
func ChatConversations(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		common.ReplyErr(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	bodyBytes, err := io.ReadAll(r.Body)
	if err != nil {
		common.ReplyErr(w, "read body failed", http.StatusBadRequest)
		return
	}
	_ = r.Body.Close()

	_, items := extractMessageForACL(r, bodyBytes)
	if len(items) > 0 {
		uid := int64(0)
		if s := r.Header.Get("X-User-Id"); s != "" {
			uid, _ = strconv.ParseInt(s, 10, 64)
		}
		for _, it := range items {
			if it.NeedPerm == "" || !acl.Can(uid, it.ResourceType, it.ResourceID, it.NeedPerm) {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusForbidden)
				_, _ = w.Write([]byte(common.ForbiddenBody))
				return
			}
		}
	}

	var raw map[string]any
	if json.Unmarshal(bodyBytes, &raw) != nil {
		common.ReplyErr(w, "invalid json", http.StatusBadRequest)
		return
	}
	setConversationDefaultValue(raw)
	if !checkInput(raw) {
		common.ReplyErr(w, "input required", http.StatusBadRequest)
		return
	}
	if !checkSearchConfig(raw) {
		common.ReplyErr(w, "invalid search_config (top_k 1-10, confidence 0-1)", http.StatusBadRequest)
		return
	}

	convID, _ := raw["conversation_id"].(string)
	if convID == "" {
		convID = newID("c_")
	}
	if len(convID) > maxConversationIDLength {
		common.ReplyErr(w, "conversation_id too long", http.StatusBadRequest)
		return
	}
	conv, _ := raw["conversation"].(map[string]any)
	displayName := ""
	if conv != nil {
		displayName, _ = conv["display_name"].(string)
	}
	if len([]rune(displayName)) > maxConversationDisplayNameLength {
		common.ReplyErr(w, "display_name too long", http.StatusBadRequest)
		return
	}

	stream, _ := raw["stream"].(bool)
	models, _ := raw["models"].([]any)
	modelStrs := make([]string, 0, len(models))
	for _, m := range models {
		if s, ok := m.(string); ok && s != "" {
			modelStrs = append(modelStrs, s)
		}
	}
	dualReply := stream && len(modelStrs) >= 2

	query := ""
	if v, ok := raw["query"].(string); ok && strings.TrimSpace(v) != "" {
		query = strings.TrimSpace(v)
	}
	if query == "" {
		if v, ok := raw["content"].(string); ok && strings.TrimSpace(v) != "" {
			query = strings.TrimSpace(v)
		}
	}
	if query == "" {
		if in, ok := raw["input"].([]any); ok && len(in) > 0 {
			if m, ok2 := in[0].(map[string]any); ok2 {
				if s, ok3 := m["text"].(string); ok3 {
					query = strings.TrimSpace(s)
				}
				if query == "" {
					query, _ = m["content"].(string)
					query = strings.TrimSpace(query)
				}
			}
		}
	}
	if query == "" {
		common.ReplyErr(w, "query required", http.StatusBadRequest)
		return
	}

	userID := store.UserID(r)
	userName := store.UserName(r)
	if userID == "" {
		userID = "0"
	}
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}
	_, seq, err := ensureConversation(db, convID, displayName, userID, userName)
	if err != nil {
		common.ReplyErr(w, "failed to ensure conversation", http.StatusInternalServerError)
		return
	}

	var histories []orm.ChatHistory
	db.Where("conversation_id = ?", convID).Order("seq ASC").Find(&histories)
	reqBody := buildChatRequestBody(convID, query, histories, raw)
	baseURL := chatServiceURL()
	reqCtx := r.Context()
	rdb := store.Redis()

	if !stream {
		handleNonStreamChat(w, reqCtx, db, rdb, baseURL, reqBody, convID, query, seq)
		return
	}

	handleStreamChat(w, r, db, rdb, baseURL, reqBody, convID, query, seq, dualReply)
}

// ResumeChat 对应 POST /api/v1/conversations:resumeChat
func ResumeChat(w http.ResponseWriter, r *http.Request) {
	resumeChatStream(w, r)
}

func resumeChatStream(w http.ResponseWriter, r *http.Request) {
	var body struct {
		ConversationID string `json:"conversation_id"`
		HistoryID      string `json:"history_id"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	convID := strings.TrimSpace(body.ConversationID)
	historyID := strings.TrimSpace(body.HistoryID)
	if convID == "" {
		common.ReplyErr(w, "conversation_id required", http.StatusBadRequest)
		return
	}

	userID := store.UserID(r)
	if userID == "" {
		userID = "0"
	}
	db := store.DB()
	if db == nil {
		common.ReplyErr(w, "store not initialized", http.StatusInternalServerError)
		return
	}
	var conv orm.Conversation
	if err := db.Where("id = ? AND create_user_id = ?", convID, userID).First(&conv).Error; err != nil {
		common.ReplyErr(w, "conversation not found", http.StatusNotFound)
		return
	}

	flusher, ok := w.(http.Flusher)
	if !ok {
		common.ReplyErr(w, "streaming not supported", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.WriteHeader(http.StatusOK)

	ctx := r.Context()
	rdb := store.Redis()
	if rdb == nil {
		resumeFromDBOnly(db, convID, flusher, w)
		return
	}

	generatingIDs, _ := getGeneratingHistoryIDs(ctx, rdb, convID)
	if len(generatingIDs) == 0 {
		resumeCompletedFromDB(db, convID, flusher, w)
		return
	}

	var multiInfo *MultiAnswerInfo
	for _, id := range generatingIDs {
		info, err := getMultiAnswerInfo(ctx, rdb, convID, id)
		if err == nil && info != nil {
			multiInfo = info
			break
		}
	}

	if multiInfo != nil {
		resumeMultiAnswerChat(ctx, rdb, convID, multiInfo, w, flusher)
		return
	}

	targetHistoryID := historyID
	if targetHistoryID == "" {
		targetHistoryID = generatingIDs[0]
	}
	resumeSingleAnswerChat(ctx, rdb, convID, targetHistoryID, w, flusher)
}

func resumeFromDBOnly(db *gorm.DB, convID string, flusher http.Flusher, w http.ResponseWriter) {
	var last orm.ChatHistory
	if err := db.Where("conversation_id = ?", convID).Order("seq DESC").First(&last).Error; err != nil || last.ID == "" {
		writeSSEChunk(w, flusher, map[string]any{"finish_reason": "FINISH_REASON_UNKNOWN"})
		return
	}
	writeSSEChunk(w, flusher, map[string]any{
		"conversation_id": convID,
		"seq":             last.Seq,
		"message":         last.Result,
		"delta":           last.Result,
		"finish_reason":   "FINISH_REASON_STOP",
		"history_id":      last.ID,
	})
}

func resumeCompletedFromDB(db *gorm.DB, convID string, flusher http.Flusher, w http.ResponseWriter) {
	var last orm.ChatHistory
	if err := db.Where("conversation_id = ?", convID).Order("seq DESC").First(&last).Error; err == nil && last.ID != "" {
		writeSSEChunk(w, flusher, map[string]any{
			"conversation_id": convID,
			"seq":             last.Seq,
			"message":         last.Result,
			"delta":           last.Result,
			"finish_reason":   "FINISH_REASON_STOP",
			"history_id":      last.ID,
		})
		return
	}

	var mh []orm.MultiAnswersChatHistory
	if err := db.Where("conversation_id = ?", convID).Order("seq DESC, create_time DESC").Limit(2).Find(&mh).Error; err != nil || len(mh) == 0 {
		writeSSEChunk(w, flusher, map[string]any{"finish_reason": "FINISH_REASON_UNKNOWN"})
		return
	}
	for i, h := range mh {
		finish := ""
		if i == len(mh)-1 {
			finish = "FINISH_REASON_STOP"
		}
		writeSSEChunk(w, flusher, map[string]any{
			"conversation_id": convID,
			"seq":             h.Seq,
			"message":         h.Result,
			"delta":           h.Result,
			"finish_reason":   finish,
			"history_id":      h.ID,
		})
	}
}

func mergeChunksToFirstChunk(chunks []*ChatChunkResponse) *ChatChunkResponse {
	if len(chunks) == 0 {
		return nil
	}
	var fullDelta, fullReasoning string
	last := chunks[len(chunks)-1]
	for _, ch := range chunks {
		if ch == nil {
			continue
		}
		fullDelta += ch.Delta
		fullReasoning += ch.ReasoningContent
	}
	if last == nil {
		return nil
	}
	return &ChatChunkResponse{
		ConversationID:   last.ConversationID,
		Seq:              last.Seq,
		HistoryID:        last.HistoryID,
		Delta:            fullDelta,
		ReasoningContent: fullReasoning,
		Sources:          last.Sources,
		FinishReason:     last.FinishReason,
	}
}

func sendChunk(w http.ResponseWriter, flusher http.Flusher, ch *ChatChunkResponse) {
	if ch == nil {
		return
	}
	writeSSEChunk(w, flusher, map[string]any{
		"conversation_id":   ch.ConversationID,
		"seq":               ch.Seq,
		"message":           ch.Message,
		"delta":             ch.Delta,
		"finish_reason":     ch.FinishReason,
		"history_id":        ch.HistoryID,
		"reasoning_content": ch.ReasoningContent,
		"sources":           ch.Sources,
	})
}

func resumeSingleAnswerChat(ctx context.Context, rdb *redis.Client, convID, historyID string, w http.ResponseWriter, flusher http.Flusher) {
	status, _ := getChatStatus(ctx, rdb, convID, historyID)
	chunks, _ := getChatChunks(ctx, rdb, convID, historyID)

	first := mergeChunksToFirstChunk(chunks)
	if first != nil {
		sendChunk(w, flusher, first)
	}

	if status != nil && (status.Status == "completed" || status.Status == "stopped" || status.Status == "failed") {
		full := strings.TrimSpace(status.CurrentResult)
		seq := int32(0)
		var sources []any
		if first != nil {
			seq = first.Seq
			sources = first.Sources
		}
		if full != "" {
			current := ""
			if first != nil {
				current = first.Delta
			}
			if len(full) > len(current) && strings.HasPrefix(full, current) {
				sendChunk(w, flusher, &ChatChunkResponse{
					ConversationID: convID,
					Seq:            seq,
					HistoryID:      historyID,
					Delta:          full[len(current):],
					Sources:        sources,
				})
			}
		}
		sendChunk(w, flusher, &ChatChunkResponse{
			ConversationID: convID,
			Seq:            seq,
			HistoryID:      historyID,
			FinishReason:   "FINISH_REASON_STOP",
		})
		_ = clearChatData(context.Background(), rdb, convID, historyID)
		return
	}

	lastIdx := int64(len(chunks) - 1)
	if lastIdx < 0 {
		lastIdx = -1
	}
	err := watchChatChunks(ctx, rdb, convID, historyID, lastIdx, func(ch *ChatChunkResponse) error {
		sendChunk(w, flusher, ch)
		return nil
	})
	if err != nil && !errors.Is(err, context.Canceled) {
		return
	}

	finalStatus, _ := getChatStatus(context.Background(), rdb, convID, historyID)
	if finalStatus != nil && (finalStatus.Status == "completed" || finalStatus.Status == "stopped") {
		sendChunk(w, flusher, &ChatChunkResponse{
			ConversationID: convID,
			HistoryID:      historyID,
			FinishReason:   "FINISH_REASON_STOP",
		})
		_ = clearChatData(context.Background(), rdb, convID, historyID)
	}
}

func resumeMultiAnswerChat(ctx context.Context, rdb *redis.Client, convID string, info *MultiAnswerInfo, w http.ResponseWriter, flusher http.Flusher) {
	primaryChunks, _ := getChatChunks(ctx, rdb, convID, info.PrimaryHistoryID)
	secondaryChunks, _ := getChatChunks(ctx, rdb, convID, info.SecondaryHistoryID)

	for _, ch := range primaryChunks {
		if ch != nil {
			ch.FinishReason = ""
			sendChunk(w, flusher, ch)
		}
	}
	for _, ch := range secondaryChunks {
		if ch != nil {
			ch.FinishReason = ""
			sendChunk(w, flusher, ch)
		}
	}

	primaryStatus, _ := getChatStatus(ctx, rdb, convID, info.PrimaryHistoryID)
	secondaryStatus, _ := getChatStatus(ctx, rdb, convID, info.SecondaryHistoryID)

	var wg sync.WaitGroup
	var writeMu sync.Mutex
	watchOne := func(historyID string, startIdx int64) {
		defer wg.Done()
		_ = watchChatChunks(ctx, rdb, convID, historyID, startIdx, func(ch *ChatChunkResponse) error {
			if ch == nil {
				return nil
			}
			ch.FinishReason = ""
			writeMu.Lock()
			sendChunk(w, flusher, ch)
			writeMu.Unlock()
			return nil
		})
	}

	if primaryStatus != nil && primaryStatus.Status == "generating" {
		wg.Add(1)
		go watchOne(info.PrimaryHistoryID, int64(len(primaryChunks)-1))
	}
	if secondaryStatus != nil && secondaryStatus.Status == "generating" {
		wg.Add(1)
		go watchOne(info.SecondaryHistoryID, int64(len(secondaryChunks)-1))
	}
	wg.Wait()

	patchTail := func(historyID string) {
		st, _ := getChatStatus(context.Background(), rdb, convID, historyID)
		if st == nil || st.CurrentResult == "" {
			return
		}
		list, _ := getChatChunks(context.Background(), rdb, convID, historyID)
		merged := mergeChunksToFirstChunk(list)
		current := ""
		seq := int32(info.Seq)
		var sources []any
		if merged != nil {
			current = merged.Delta
			seq = merged.Seq
			sources = merged.Sources
		}
		full := st.CurrentResult
		if len(full) > len(current) && strings.HasPrefix(full, current) {
			sendChunk(w, flusher, &ChatChunkResponse{
				ConversationID: convID,
				Seq:            seq,
				HistoryID:      historyID,
				Delta:          full[len(current):],
				Sources:        sources,
			})
		}
	}
	patchTail(info.PrimaryHistoryID)
	patchTail(info.SecondaryHistoryID)

	sendChunk(w, flusher, &ChatChunkResponse{
		ConversationID: convID,
		Seq:            int32(info.Seq),
		HistoryID:      info.PrimaryHistoryID,
		FinishReason:   "FINISH_REASON_STOP",
	})
	sendChunk(w, flusher, &ChatChunkResponse{
		ConversationID: convID,
		Seq:            int32(info.Seq),
		HistoryID:      info.SecondaryHistoryID,
		FinishReason:   "FINISH_REASON_STOP",
	})

	_ = clearChatData(context.Background(), rdb, convID, info.PrimaryHistoryID)
	_ = clearChatData(context.Background(), rdb, convID, info.SecondaryHistoryID)
}

// StopChatGeneration 对应 POST /api/v1/conversations:stopChatGeneration
func StopChatGeneration(w http.ResponseWriter, r *http.Request) {
	var body struct {
		ConversationID string `json:"conversation_id"`
		HistoryID      string `json:"history_id"`
	}
	_ = json.NewDecoder(r.Body).Decode(&body)
	convID := strings.TrimSpace(body.ConversationID)
	historyID := strings.TrimSpace(body.HistoryID)
	if convID == "" {
		common.ReplyErr(w, "conversation_id required", http.StatusBadRequest)
		return
	}

	userID := store.UserID(r)
	if userID == "" {
		userID = "0"
	}
	var conv orm.Conversation
	if err := store.DB().Where("id = ? AND create_user_id = ?", convID, userID).First(&conv).Error; err != nil {
		common.ReplyErr(w, "conversation not found", http.StatusNotFound)
		return
	}

	rdb := store.Redis()
	if rdb != nil {
		ids, _ := getGeneratingHistoryIDs(r.Context(), rdb, convID)
		if len(ids) == 0 && historyID != "" {
			ids = append(ids, historyID)
		}
		for _, hid := range ids {
			_ = setChatCancelSignal(r.Context(), rdb, convID, hid)
		}
	}
	common.ReplyOK(w, nil)
}

// GetChatStatus 对应 GET /api/v1/conversations/{conversation_id}:status
func GetChatStatus(w http.ResponseWriter, r *http.Request) {
	convID := mux.Vars(r)["conversation_id"]
	if convID == "" {
		common.ReplyErr(w, "conversation_id required", http.StatusBadRequest)
		return
	}
	userID := store.UserID(r)
	if userID == "" {
		userID = "0"
	}
	var conv orm.Conversation
	if err := store.DB().Where("id = ? AND create_user_id = ?", convID, userID).First(&conv).Error; err != nil {
		common.ReplyErr(w, "conversation not found", http.StatusNotFound)
		return
	}
	isGenerating := false
	rdb := store.Redis()
	if rdb != nil {
		ids, _ := getGeneratingHistoryIDs(r.Context(), rdb, convID)
		isGenerating = len(ids) > 0
	}
	common.ReplyOK(w, map[string]any{"is_generating": isGenerating})
}

// GetConversation 对应 GET /api/v1/conversations/{name}
func GetConversation(w http.ResponseWriter, r *http.Request) {
	name := mux.Vars(r)["name"]
	convID := conversationIDFromName(name)
	if convID == "" {
		common.ReplyErr(w, "invalid conversation name", http.StatusBadRequest)
		return
	}
	userID := store.UserID(r)
	if userID == "" {
		userID = "0"
	}
	var c orm.Conversation
	if err := store.DB().Where("id = ? AND create_user_id = ?", convID, userID).First(&c).Error; err != nil {
		common.ReplyErr(w, "conversation not found", http.StatusNotFound)
		return
	}
	common.ReplyOK(w, map[string]any{
		"name":            "conversations/" + c.ID,
		"conversation_id": c.ID,
		"display_name":    c.DisplayName,
		"create_time":     c.CreatedAt.Unix(),
		"update_time":     c.UpdatedAt.Unix(),
	})
}

// GetConversationDetail 对应 GET /api/v1/conversations/{name}:detail
func GetConversationDetail(w http.ResponseWriter, r *http.Request) {
	name := mux.Vars(r)["name"]
	convID := conversationIDFromName(name)
	if convID == "" {
		common.ReplyErr(w, "invalid conversation name", http.StatusBadRequest)
		return
	}
	userID := store.UserID(r)
	if userID == "" {
		userID = "0"
	}
	var c orm.Conversation
	if err := store.DB().Where("id = ? AND create_user_id = ?", convID, userID).First(&c).Error; err != nil {
		common.ReplyErr(w, "conversation not found", http.StatusNotFound)
		return
	}
	var histories []orm.ChatHistory
	store.DB().Where("conversation_id = ?", convID).Order("seq ASC").Find(&histories)

	rdb := store.Redis()
	if rdb != nil {
		ids, _ := getGeneratingHistoryIDs(r.Context(), rdb, convID)
		exists := make(map[string]struct{}, len(histories))
		for _, h := range histories {
			exists[h.ID] = struct{}{}
		}
		for _, hid := range ids {
			if _, ok := exists[hid]; ok {
				continue
			}
			in, err := getChatInput(r.Context(), rdb, convID, hid)
			if err != nil || in == nil || strings.TrimSpace(in.RawContent) == "" {
				continue
			}
			ct := time.UnixMilli(in.CreatedAt)
			histories = append(histories, orm.ChatHistory{
				ID:             hid,
				Seq:            in.Seq,
				ConversationID: convID,
				RawContent:     in.RawContent,
				Content:        in.RawContent,
				Result:         "",
				TimeMixin:      orm.TimeMixin{CreateTime: ct, UpdateTime: ct},
			})
		}
		sort.Slice(histories, func(i, j int) bool { return histories[i].Seq < histories[j].Seq })
	}

	list := make([]map[string]any, 0, len(histories))
	for _, h := range histories {
		list = append(list, map[string]any{
			"seq":             h.Seq,
			"query":           h.RawContent,
			"result":          h.Result,
			"id":              h.ID,
			"reason":          h.Reason,
			"expected_answer": h.ExpectedAnswer,
			"create_time":     h.CreateTime.Unix(),
		})
	}
	common.ReplyOK(w, map[string]any{
		"conversation": map[string]any{
			"name":            "conversations/" + c.ID,
			"conversation_id": c.ID,
			"display_name":    c.DisplayName,
			"create_time":     c.CreatedAt.Unix(),
			"update_time":     c.UpdatedAt.Unix(),
		},
		"history": list,
	})
}

// DeleteConversation 对应 DELETE /api/v1/conversations/{name}
func DeleteConversation(w http.ResponseWriter, r *http.Request) {
	name := mux.Vars(r)["name"]
	convID := conversationIDFromName(name)
	if convID == "" {
		common.ReplyErr(w, "invalid conversation name", http.StatusBadRequest)
		return
	}
	userID := store.UserID(r)
	if userID == "" {
		userID = "0"
	}
	db := store.DB()
	res := db.Where("id = ? AND create_user_id = ?", convID, userID).Delete(&orm.Conversation{})
	if res.RowsAffected == 0 {
		common.ReplyErr(w, "conversation not found", http.StatusNotFound)
		return
	}
	db.Where("conversation_id = ?", convID).Delete(&orm.ChatHistory{})
	db.Where("conversation_id = ?", convID).Delete(&orm.MultiAnswersChatHistory{})
	common.ReplyOK(w, nil)
}

// ListConversations 对应 GET /api/v1/conversations
func ListConversations(w http.ResponseWriter, r *http.Request) {
	userID := store.UserID(r)
	if userID == "" {
		userID = "0"
	}
	keyword := strings.TrimSpace(r.URL.Query().Get("keyword"))
	pageSize := 20
	if s := r.URL.Query().Get("page_size"); s != "" {
		if n, _ := strconv.Atoi(s); n > 0 && n <= 100 {
			pageSize = n
		}
	}
	offset := 0
	if s := r.URL.Query().Get("page_token"); s != "" {
		if n, _ := strconv.Atoi(s); n > 0 {
			offset = n
		}
	}

	db := store.DB()
	q := db.Model(&orm.Conversation{}).Where("create_user_id = ?", userID)
	if keyword != "" {
		q = q.Where("display_name LIKE ?", "%"+keyword+"%")
	}
	var total int64
	q.Count(&total)
	var list []orm.Conversation
	q.Order("updated_at DESC").Offset(offset).Limit(pageSize).Find(&list)
	items := make([]map[string]any, 0, len(list))
	for _, c := range list {
		items = append(items, map[string]any{
			"name":            "conversations/" + c.ID,
			"conversation_id": c.ID,
			"display_name":    c.DisplayName,
			"create_time":     c.CreatedAt.Unix(),
			"update_time":     c.UpdatedAt.Unix(),
		})
	}
	nextToken := ""
	if offset+len(list) < int(total) {
		nextToken = strconv.Itoa(offset + len(list))
	}
	common.ReplyOK(w, map[string]any{
		"conversations":   items,
		"total_size":      total,
		"next_page_token": nextToken,
	})
}

// SetChatHistory 对应 POST /api/v1/conversations:setChatHistory
func SetChatHistory(w http.ResponseWriter, r *http.Request) {
	var body struct {
		SetHistoryID     string `json:"set_history_id"`
		DeletedHistoryID string `json:"deleted_history_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if body.SetHistoryID == "" {
		common.ReplyErr(w, "set_history_id required", http.StatusBadRequest)
		return
	}
	if body.DeletedHistoryID == "" {
		common.ReplyErr(w, "deleted_history_id required", http.StatusBadRequest)
		return
	}

	db := store.DB()
	now := time.Now()

	var selected orm.MultiAnswersChatHistory
	if err := db.Where("id = ?", body.SetHistoryID).First(&selected).Error; err != nil {
		common.ReplyErr(w, "set_history_id not found", http.StatusNotFound)
		return
	}
	var deleted orm.MultiAnswersChatHistory
	if err := db.Where("id = ?", body.DeletedHistoryID).First(&deleted).Error; err != nil {
		common.ReplyErr(w, "deleted_history_id not found", http.StatusNotFound)
		return
	}
	if selected.ConversationID == "" || selected.ConversationID != deleted.ConversationID {
		common.ReplyErr(w, "history ids are not in same conversation", http.StatusBadRequest)
		return
	}
	userID := store.UserID(r)
	if userID == "" {
		userID = "0"
	}
	var conv orm.Conversation
	if err := db.Where("id = ? AND create_user_id = ?", selected.ConversationID, userID).First(&conv).Error; err != nil {
		common.ReplyErr(w, "conversation not found", http.StatusNotFound)
		return
	}

	var exists orm.ChatHistory
	if err := db.Where("id = ?", body.SetHistoryID).First(&exists).Error; err != nil {
		target := orm.ChatHistory{
			ID:              selected.ID,
			Seq:             selected.Seq,
			ConversationID:  selected.ConversationID,
			RawContent:      selected.RawContent,
			RetrievalResult: selected.RetrievalResult,
			Content:         selected.Content,
			Result:          selected.Result,
			FeedBack:        selected.FeedBack,
			Reason:          selected.Reason,
			Ext:             selected.Ext,
			Version:         "2.3",
			TimeMixin:       orm.TimeMixin{CreateTime: now, UpdateTime: now},
		}
		if err := db.Create(&target).Error; err != nil {
			common.ReplyErr(w, "set history failed", http.StatusInternalServerError)
			return
		}
	}

	_ = db.Where("id IN ?", []string{body.SetHistoryID, body.DeletedHistoryID}).Delete(&orm.MultiAnswersChatHistory{}).Error
	common.ReplyOK(w, map[string]any{"history_id": body.SetHistoryID})
}

// FeedBackChatHistory 对应 POST /api/v1/conversations:feedBackChatHistory
func FeedBackChatHistory(w http.ResponseWriter, r *http.Request) {
	var body struct {
		HistoryID      string `json:"history_id"`
		Type           int32  `json:"type"`
		Reason         string `json:"reason,omitempty"`
		ExpectedAnswer string `json:"expected_answer,omitempty"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if body.HistoryID == "" {
		common.ReplyErr(w, "history_id required", http.StatusBadRequest)
		return
	}
	db := store.DB()
	res := db.Model(&orm.ChatHistory{}).Where("id = ?", body.HistoryID).Updates(map[string]any{
		"feed_back":       body.Type,
		"reason":          body.Reason,
		"expected_answer": body.ExpectedAnswer,
		"update_time":     time.Now(),
	})
	if res.RowsAffected == 0 {
		common.ReplyErr(w, "history not found", http.StatusNotFound)
		return
	}
	common.ReplyOK(w, nil)
}

// GetMultiAnswersSwitchStatus 对应 GET /api/v1/conversation:switchStatus
func GetMultiAnswersSwitchStatus(w http.ResponseWriter, r *http.Request) {
	userID := store.UserID(r)
	if userID == "" {
		userID = "0"
	}
	var row orm.MultiAnswersSwitch
	err := store.DB().Where("create_user_id = ?", userID).First(&row).Error
	st := int32(0)
	if err == nil {
		st = row.Status
	}
	common.ReplyOK(w, map[string]any{"status": st})
}

// SetMultiAnswersSwitchStatus 对应 POST /api/v1/conversation:switchStatus
func SetMultiAnswersSwitchStatus(w http.ResponseWriter, r *http.Request) {
	userID := store.UserID(r)
	userName := store.UserName(r)
	if userID == "" {
		userID = "0"
	}
	var body struct {
		Status int32 `json:"status"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		common.ReplyErr(w, "invalid body", http.StatusBadRequest)
		return
	}
	if body.Status != 0 && body.Status != 1 {
		common.ReplyErr(w, "status must be 0 or 1", http.StatusBadRequest)
		return
	}
	db := store.DB()
	now := time.Now()
	var row orm.MultiAnswersSwitch
	if db.Where("create_user_id = ?", userID).First(&row).Error != nil {
		row = orm.MultiAnswersSwitch{
			Status: body.Status,
			BaseModel: orm.BaseModel{
				CreateUserID:   userID,
				CreateUserName: userName,
				CreatedAt:      now,
				UpdatedAt:      now,
			},
		}
		db.Create(&row)
	} else {
		db.Model(&row).Updates(map[string]any{"status": body.Status, "updated_at": now})
	}
	common.ReplyOK(w, map[string]any{"status": body.Status})
}
