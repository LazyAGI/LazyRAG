package server

import (
	"bytes"
	"context"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"go.uber.org/zap"
	"gorm.io/gorm"

	"github.com/lazyrag/scan_control_plane/internal/coreclient"
	"github.com/lazyrag/scan_control_plane/internal/model"
	"github.com/lazyrag/scan_control_plane/internal/store"
)

const (
	scanFrontendPrefix = "/api/scan"
)

type Handler struct {
	store         *store.Store
	merger        EventMerger
	core          coreclient.Client
	coreDatasetID string
	agentToken    string
	client        *http.Client
	log           *zap.Logger
}

type EventMerger interface {
	Ingest(events []model.FileEvent)
}

func NewHandler(st *store.Store, merger EventMerger, core coreclient.Client, coreDatasetID string, agentToken string, log *zap.Logger) *Handler {
	if core == nil {
		core = coreclient.NewNoop()
	}
	return &Handler{
		store:         st,
		merger:        merger,
		core:          core,
		coreDatasetID: strings.TrimSpace(coreDatasetID),
		agentToken:    agentToken,
		client: &http.Client{
			Timeout: 10 * time.Second,
		},
		log: log,
	}
}

func NewHTTPServer(listenAddr string, h *Handler) *http.Server {
	mux := http.NewServeMux()
	h.registerRoutes(mux)
	handler := h.authMiddleware(mux)
	return &http.Server{
		Addr:         listenAddr,
		Handler:      accessLogMiddleware(h.log, handler),
		ReadTimeout:  10 * time.Second,
		WriteTimeout: 30 * time.Second,
	}
}

type statusRecorder struct {
	http.ResponseWriter
	status int
}

func (r *statusRecorder) WriteHeader(code int) {
	r.status = code
	r.ResponseWriter.WriteHeader(code)
}

func accessLogMiddleware(log *zap.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		startedAt := time.Now()
		rec := &statusRecorder{ResponseWriter: w, status: http.StatusOK}
		next.ServeHTTP(rec, r)

		reqSize := r.ContentLength
		if reqSize < 0 {
			reqSize = 0
		}
		log.Info("http access",
			zap.String("path", r.URL.Path),
			zap.String("method", r.Method),
			zap.Int("status", rec.status),
			zap.Duration("latency", time.Since(startedAt)),
			zap.Int64("request_size", reqSize),
		)
	})
}

func (h *Handler) authMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimSpace(r.URL.Path)
		switch {
		case strings.HasPrefix(path, scanFrontendPrefix+"/"):
			if strings.TrimSpace(r.Header.Get("X-User-Id")) == "" {
				writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "missing X-User-Id; frontend requests must pass through Kong auth")
				return
			}
		case strings.HasPrefix(path, "/api/v1/agents/"):
			if !h.validateAgentAuthorization(r.Header.Get("Authorization")) {
				writeError(w, http.StatusUnauthorized, "UNAUTHORIZED", "invalid agent authorization")
				return
			}
		}
		next.ServeHTTP(w, r)
	})
}

func (h *Handler) validateAgentAuthorization(rawAuth string) bool {
	expected := strings.TrimSpace(h.agentToken)
	if expected == "" {
		// Keep backward compatibility when agent_token is intentionally unset.
		return true
	}
	rawAuth = strings.TrimSpace(rawAuth)
	if rawAuth == "" {
		return false
	}
	const prefix = "Bearer "
	if !strings.HasPrefix(rawAuth, prefix) {
		return false
	}
	got := strings.TrimSpace(strings.TrimPrefix(rawAuth, prefix))
	if got == "" {
		return false
	}
	expectedBytes := []byte(expected)
	gotBytes := []byte(got)
	if len(expectedBytes) != len(gotBytes) {
		return false
	}
	return subtle.ConstantTimeCompare(expectedBytes, gotBytes) == 1
}

func (h *Handler) registerRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /healthz", h.healthz)
	mux.HandleFunc("GET /docs", h.docs)
	mux.HandleFunc("GET /openapi.json", h.openapiJSON)

	// Frontend APIs (canonical).
	h.registerFrontendRoutes(mux, scanFrontendPrefix)

	// Agent-facing internal APIs (kept on /api/v1 for file-watcher compatibility).
	mux.HandleFunc("POST /api/v1/agents/register", h.registerAgent)
	mux.HandleFunc("POST /api/v1/agents/heartbeat", h.reportHeartbeat)
	mux.HandleFunc("POST /api/v1/agents/pull", h.pullCommands)
	mux.HandleFunc("POST /api/v1/agents/commands/ack", h.ackCommand)
	mux.HandleFunc("POST /api/v1/agents/snapshots/report", h.reportSnapshot)
	mux.HandleFunc("POST /api/v1/agents/events", h.reportEvents)
	mux.HandleFunc("POST /api/v1/agents/scan-results", h.reportScanResults)
}

func (h *Handler) registerFrontendRoutes(mux *http.ServeMux, prefix string) {
	prefix = strings.TrimRight(strings.TrimSpace(prefix), "/")
	if prefix == "" {
		return
	}
	mux.HandleFunc("POST "+prefix+"/sources", h.createSource)
	mux.HandleFunc("POST "+prefix+"/knowledge-bases", h.createKnowledgeBase)
	mux.HandleFunc("GET "+prefix+"/sources", h.listSources)
	mux.HandleFunc("GET "+prefix+"/sources/{id}", h.getSource)
	mux.HandleFunc("PUT "+prefix+"/sources/{id}", h.updateSource)
	mux.HandleFunc("POST "+prefix+"/sources/{id}/enable", h.enableSource)
	mux.HandleFunc("POST "+prefix+"/sources/{id}/disable", h.disableSource)
	mux.HandleFunc("POST "+prefix+"/sources/{id}/tasks/generate", h.generateSourceTasks)
	mux.HandleFunc("POST "+prefix+"/sources/{id}/watch/enable", h.enableSourceWatch)
	mux.HandleFunc("POST "+prefix+"/sources/{id}/watch/disable", h.disableSourceWatch)
	mux.HandleFunc("POST "+prefix+"/sources/{id}/tasks/expedite", h.expediteSourceTasks)
	mux.HandleFunc("GET "+prefix+"/sources/{id}/documents", h.listSourceDocuments)
	mux.HandleFunc("GET "+prefix+"/sources/{id}/manual-pull-jobs", h.listManualPullJobs)
	mux.HandleFunc("GET "+prefix+"/parse-tasks", h.listParseTasks)
	mux.HandleFunc("GET "+prefix+"/parse-tasks/stats", h.parseTaskStats)
	mux.HandleFunc("GET "+prefix+"/parse-tasks/{id}", h.getParseTask)
	mux.HandleFunc("POST "+prefix+"/parse-tasks/{id}/retry", h.retryParseTask)
	mux.HandleFunc("GET "+prefix+"/agents", h.listAgents)
	mux.HandleFunc("GET "+prefix+"/agents/{id}", h.getAgent)
	// Frontend helper APIs: proxy path validation/tree via selected agent.
	mux.HandleFunc("POST "+prefix+"/agents/fs/validate", h.validatePathByAgent)
	mux.HandleFunc("POST "+prefix+"/agents/fs/tree", h.pathTreeByAgent)
}

func (h *Handler) healthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (h *Handler) createSource(w http.ResponseWriter, r *http.Request) {
	var req model.CreateSourceRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	req.DatasetID = strings.TrimSpace(req.DatasetID)
	if h.core != nil && h.core.Enabled() {
		// In core-task mode each source should have a concrete dataset binding.
		if req.DatasetID == "" {
			req.DatasetID = strings.TrimSpace(h.coreDatasetID)
		}
		if req.DatasetID == "" {
			writeError(w, http.StatusBadRequest, "DATASET_ID_REQUIRED", "dataset_id is required when core is enabled; set source dataset_id or configure core.dataset_id")
			return
		}
	}
	src, err := h.store.CreateSource(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusBadRequest, "CREATE_SOURCE_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, src)
}

func (h *Handler) createKnowledgeBase(w http.ResponseWriter, r *http.Request) {
	if h.core == nil || !h.core.Enabled() {
		writeError(w, http.StatusBadRequest, "CORE_DISABLED", "core client is disabled")
		return
	}
	var req model.CreateKnowledgeBaseRequest
	if !decodeJSONStrict(w, r, &req) {
		return
	}
	if strings.TrimSpace(req.Name) == "" {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", "name is required")
		return
	}
	if strings.TrimSpace(req.Algo.AlgoID) == "" {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", "algo.algo_id is required")
		return
	}
	currentUserID := strings.TrimSpace(r.Header.Get("X-User-Id"))
	currentUserName := strings.TrimSpace(r.Header.Get("X-User-Name"))
	if currentUserID == "" {
		writeError(w, http.StatusBadRequest, "MISSING_CURRENT_USER", "missing X-User-Id")
		return
	}

	result, err := h.core.CreateKnowledgeBase(r.Context(), coreclient.CreateKnowledgeBaseRequest{
		Name:            strings.TrimSpace(req.Name),
		AlgoID:          strings.TrimSpace(req.Algo.AlgoID),
		AlgoDescription: strings.TrimSpace(req.Algo.Description),
		AlgoDisplayName: strings.TrimSpace(req.Algo.DisplayName),
		CurrentUserID:   currentUserID,
		CurrentUserName: currentUserName,
	})
	if err != nil {
		writeError(w, http.StatusBadGateway, "CREATE_KNOWLEDGE_BASE_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, model.CreateKnowledgeBaseResponse{
		DatasetID: result.DatasetID,
		Name:      result.Name,
	})
}

func (h *Handler) listSources(w http.ResponseWriter, r *http.Request) {
	tenantID := strings.TrimSpace(r.URL.Query().Get("tenant_id"))
	sources, err := h.store.ListSources(r.Context(), tenantID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LIST_SOURCES_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": sources})
}

func (h *Handler) getSource(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	src, err := h.store.GetSource(r.Context(), id)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "SOURCE_NOT_FOUND", "source not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "GET_SOURCE_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, src)
}

func (h *Handler) updateSource(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	var req model.UpdateSourceRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	src, err := h.store.UpdateSource(r.Context(), id, req)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "SOURCE_NOT_FOUND", "source not found")
			return
		}
		writeError(w, http.StatusBadRequest, "UPDATE_SOURCE_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, src)
}

func (h *Handler) enableSource(w http.ResponseWriter, r *http.Request) {
	h.setSourceEnabled(w, r, true)
}

func (h *Handler) disableSource(w http.ResponseWriter, r *http.Request) {
	h.setSourceEnabled(w, r, false)
}

func (h *Handler) setSourceEnabled(w http.ResponseWriter, r *http.Request, enabled bool) {
	id := r.PathValue("id")
	src, err := h.store.SetSourceEnabled(r.Context(), id, enabled)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "SOURCE_NOT_FOUND", "source not found")
			return
		}
		writeError(w, http.StatusBadRequest, "SET_SOURCE_STATUS_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, src)
}

func (h *Handler) generateSourceTasks(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	var req model.GenerateTasksRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if h.core != nil && h.core.Enabled() {
		src, err := h.store.GetSource(r.Context(), id)
		if err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				writeError(w, http.StatusNotFound, "SOURCE_NOT_FOUND", "source not found")
				return
			}
			writeError(w, http.StatusInternalServerError, "GET_SOURCE_FAILED", err.Error())
			return
		}
		effectiveDatasetID := strings.TrimSpace(src.DatasetID)
		if effectiveDatasetID == "" {
			effectiveDatasetID = strings.TrimSpace(h.coreDatasetID)
		}
		if effectiveDatasetID == "" {
			writeError(w, http.StatusBadRequest, "MISSING_DATASET_BINDING", "source dataset_id is empty; bind dataset to source or configure core.dataset_id")
			return
		}
	}
	resp, err := h.store.GenerateTasksForSource(r.Context(), id, req)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "SOURCE_NOT_FOUND", "source not found")
			return
		}
		writeError(w, http.StatusBadRequest, "GENERATE_TASKS_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) enableSourceWatch(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	var req model.EnableWatchRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	_, err := h.store.EnableSourceWatch(r.Context(), id, req)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "SOURCE_NOT_FOUND", "source not found")
			return
		}
		writeError(w, http.StatusBadRequest, "ENABLE_WATCH_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, model.WatchToggleResponse{
		Accepted:        true,
		SkipInitialScan: true,
	})
}

func (h *Handler) disableSourceWatch(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	_, queued, err := h.store.DisableSourceWatch(r.Context(), id)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "SOURCE_NOT_FOUND", "source not found")
			return
		}
		writeError(w, http.StatusBadRequest, "DISABLE_WATCH_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, model.WatchToggleResponse{
		Accepted:               true,
		BaselineSnapshotQueued: queued,
	})
}

func (h *Handler) expediteSourceTasks(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	var req model.ExpediteTasksRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	resp, err := h.store.ExpediteTasksByPaths(r.Context(), id, req)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "SOURCE_NOT_FOUND", "source not found")
			return
		}
		writeError(w, http.StatusBadRequest, "EXPEDITE_TASKS_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) listSourceDocuments(w http.ResponseWriter, r *http.Request) {
	sourceID := strings.TrimSpace(r.PathValue("id"))
	req := model.ListSourceDocumentsRequest{
		TenantID:   strings.TrimSpace(r.URL.Query().Get("tenant_id")),
		Keyword:    strings.TrimSpace(r.URL.Query().Get("keyword")),
		UpdateType: strings.TrimSpace(r.URL.Query().Get("update_type")),
		ParseState: strings.TrimSpace(r.URL.Query().Get("parse_state")),
		Page:       parseIntDefault(r.URL.Query().Get("page"), 1),
		PageSize:   parseIntDefault(r.URL.Query().Get("page_size"), 20),
	}
	resp, err := h.store.ListSourceDocuments(r.Context(), sourceID, req)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "SOURCE_NOT_FOUND", "source not found")
			return
		}
		if isBadRequestError(err) {
			writeError(w, http.StatusBadRequest, "LIST_SOURCE_DOCUMENTS_FAILED", err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, "LIST_SOURCE_DOCUMENTS_FAILED", err.Error())
		return
	}
	if h.core != nil && h.core.Enabled() {
		coreRefs, err := h.store.ListSourceDocumentCoreRefs(r.Context(), sourceID, req.TenantID)
		if err != nil {
			h.log.Warn("list source core refs failed", zap.Error(err), zap.String("source_id", sourceID))
		} else {
			states, err := h.searchCoreTaskStates(r.Context(), coreRefs)
			if err != nil {
				h.log.Warn("search core tasks failed", zap.Error(err), zap.String("source_id", sourceID))
			} else {
				for i := range resp.Items {
					id := strings.TrimSpace(resp.Items[i].CoreTaskID)
					if id == "" {
						continue
					}
					state, ok := states[id]
					if !ok {
						continue
					}
					resp.Items[i].CoreTaskState = strings.TrimSpace(state.TaskState)
					if strings.TrimSpace(resp.Items[i].CoreTaskState) != "" {
						resp.Items[i].ParseState = resp.Items[i].CoreTaskState
					}
				}
				resp.Summary = buildSourceDocumentsSummaryWithCore(coreRefs, states, resp.Summary.StorageBytes)
			}
		}
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) listManualPullJobs(w http.ResponseWriter, r *http.Request) {
	sourceID := strings.TrimSpace(r.PathValue("id"))
	req := model.ListManualPullJobsRequest{
		SourceID: sourceID,
		Page:     parseIntDefault(r.URL.Query().Get("page"), 1),
		PageSize: parseIntDefault(r.URL.Query().Get("page_size"), 20),
		Status:   strings.TrimSpace(r.URL.Query().Get("status")),
	}
	resp, err := h.store.ListManualPullJobs(r.Context(), sourceID, req)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "SOURCE_NOT_FOUND", "source not found")
			return
		}
		if isBadRequestError(err) {
			writeError(w, http.StatusBadRequest, "LIST_MANUAL_PULL_JOBS_FAILED", err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, "LIST_MANUAL_PULL_JOBS_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) listParseTasks(w http.ResponseWriter, r *http.Request) {
	req := model.ListParseTasksRequest{
		TenantID: strings.TrimSpace(r.URL.Query().Get("tenant_id")),
		SourceID: strings.TrimSpace(r.URL.Query().Get("source_id")),
		Status:   strings.TrimSpace(r.URL.Query().Get("status")),
		Keyword:  strings.TrimSpace(r.URL.Query().Get("keyword")),
		Page:     parseIntDefault(r.URL.Query().Get("page"), 1),
		PageSize: parseIntDefault(r.URL.Query().Get("page_size"), 20),
	}
	resp, err := h.store.ListParseTasks(r.Context(), req)
	if err != nil {
		if isBadRequestError(err) {
			writeError(w, http.StatusBadRequest, "LIST_PARSE_TASKS_FAILED", err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, "LIST_PARSE_TASKS_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) getParseTask(w http.ResponseWriter, r *http.Request) {
	taskID, ok := parsePathInt64(w, r, "id")
	if !ok {
		return
	}
	resp, err := h.store.GetParseTask(r.Context(), taskID)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "PARSE_TASK_NOT_FOUND", "parse task not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "GET_PARSE_TASK_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) parseTaskStats(w http.ResponseWriter, r *http.Request) {
	tenantID := strings.TrimSpace(r.URL.Query().Get("tenant_id"))
	sourceID := strings.TrimSpace(r.URL.Query().Get("source_id"))
	counts, err := h.store.CountParseTasksByStatusWithFilter(r.Context(), tenantID, sourceID)
	if err != nil {
		if isBadRequestError(err) {
			writeError(w, http.StatusBadRequest, "GET_PARSE_TASK_STATS_FAILED", err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, "GET_PARSE_TASK_STATS_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, model.ParseTaskStatsResponse{Counts: counts})
}

func (h *Handler) retryParseTask(w http.ResponseWriter, r *http.Request) {
	taskID, ok := parsePathInt64(w, r, "id")
	if !ok {
		return
	}
	resp, err := h.store.RetryParseTask(r.Context(), taskID)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "PARSE_TASK_NOT_FOUND", "parse task not found")
			return
		}
		if isBadRequestError(err) {
			writeError(w, http.StatusBadRequest, "RETRY_PARSE_TASK_FAILED", err.Error())
			return
		}
		writeError(w, http.StatusInternalServerError, "RETRY_PARSE_TASK_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) listAgents(w http.ResponseWriter, r *http.Request) {
	tenantID := strings.TrimSpace(r.URL.Query().Get("tenant_id"))
	agents, err := h.store.ListAgents(r.Context(), tenantID)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "LIST_AGENTS_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": agents})
}

func (h *Handler) getAgent(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	agent, err := h.store.GetAgent(r.Context(), id)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "AGENT_NOT_FOUND", "agent not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "GET_AGENT_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, agent)
}

func (h *Handler) registerAgent(w http.ResponseWriter, r *http.Request) {
	var req model.RegisterAgentRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if err := h.store.RegisterAgent(r.Context(), req); err != nil {
		writeError(w, http.StatusBadRequest, "REGISTER_AGENT_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"accepted": true})
}

func (h *Handler) reportHeartbeat(w http.ResponseWriter, r *http.Request) {
	var req model.HeartbeatPayload
	if !decodeJSON(w, r, &req) {
		return
	}
	if err := h.store.UpdateHeartbeat(r.Context(), req); err != nil {
		writeError(w, http.StatusBadRequest, "HEARTBEAT_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"accepted": true})
}

func (h *Handler) pullCommands(w http.ResponseWriter, r *http.Request) {
	var req model.PullCommandsRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	resp, err := h.store.PullPendingCommands(r.Context(), req)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "PULL_COMMANDS_FAILED", err.Error())
		return
	}
	if len(resp.Commands) > 0 {
		h.log.Info("commands pulled by agent",
			zap.String("agent_id", req.AgentID),
			zap.Int("count", len(resp.Commands)),
		)
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) ackCommand(w http.ResponseWriter, r *http.Request) {
	var req model.AckCommandRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if err := h.store.AckCommand(r.Context(), req); err != nil {
		writeError(w, http.StatusBadRequest, "ACK_COMMAND_FAILED", err.Error())
		return
	}
	h.log.Info("command ack received",
		zap.String("agent_id", req.AgentID),
		zap.Int64("command_id", req.CommandID),
		zap.Bool("success", req.Success),
		zap.String("error", strings.TrimSpace(req.Error)),
	)
	writeJSON(w, http.StatusOK, map[string]any{"accepted": true})
}

func (h *Handler) reportSnapshot(w http.ResponseWriter, r *http.Request) {
	var req model.ReportSnapshotRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if err := h.store.ReportSnapshotMetadata(r.Context(), req); err != nil {
		writeError(w, http.StatusBadRequest, "REPORT_SNAPSHOT_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"accepted": true})
}

func (h *Handler) reportEvents(w http.ResponseWriter, r *http.Request) {
	var req model.ReportEventsRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	h.log.Info("agent events received",
		zap.String("agent_id", req.AgentID),
		zap.Int("count", len(req.Events)),
	)
	if h.merger != nil {
		h.merger.Ingest(req.Events)
	} else {
		if err := h.store.IngestEvents(r.Context(), req); err != nil {
			writeError(w, http.StatusInternalServerError, "INGEST_EVENTS_FAILED", err.Error())
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"accepted": true})
}

func (h *Handler) reportScanResults(w http.ResponseWriter, r *http.Request) {
	var req model.ReportScanResultsRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	h.log.Info("agent scan results received",
		zap.String("agent_id", req.AgentID),
		zap.String("source_id", req.SourceID),
		zap.String("mode", req.Mode),
		zap.Int("records", len(req.Records)),
	)
	events := make([]model.FileEvent, 0, len(req.Records))
	for _, rec := range req.Records {
		events = append(events, model.FileEvent{
			SourceID:       rec.SourceID,
			EventType:      "modified",
			Path:           rec.Path,
			IsDir:          rec.IsDir,
			OccurredAt:     rec.ModTime,
			OriginType:     rec.OriginType,
			OriginPlatform: rec.OriginPlatform,
			OriginRef:      rec.OriginRef,
			TriggerPolicy:  rec.TriggerPolicy,
		})
	}
	if h.merger != nil {
		h.merger.Ingest(events)
	} else {
		if err := h.store.IngestScanResults(r.Context(), req); err != nil {
			writeError(w, http.StatusInternalServerError, "INGEST_SCAN_RESULTS_FAILED", err.Error())
			return
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"accepted": true})
}

func (h *Handler) validatePathByAgent(w http.ResponseWriter, r *http.Request) {
	var req model.AgentPathRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	agent, err := h.store.GetAgent(r.Context(), req.AgentID)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "AGENT_NOT_FOUND", "agent not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "GET_AGENT_FAILED", err.Error())
		return
	}
	var resp model.AgentPathValidateResponse
	if err := h.callAgentJSON(r.Context(), agent.ListenAddr, "/api/v1/fs/validate", model.BrowseRequest{Path: req.Path}, &resp); err != nil {
		writeError(w, http.StatusBadGateway, "AGENT_VALIDATE_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, resp)
}

func (h *Handler) pathTreeByAgent(w http.ResponseWriter, r *http.Request) {
	var req model.AgentPathTreeRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if req.MaxDepth <= 0 {
		req.MaxDepth = 2
	}
	if req.MaxDepth > 8 {
		req.MaxDepth = 8
	}
	agent, err := h.store.GetAgent(r.Context(), req.AgentID)
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			writeError(w, http.StatusNotFound, "AGENT_NOT_FOUND", "agent not found")
			return
		}
		writeError(w, http.StatusInternalServerError, "GET_AGENT_FAILED", err.Error())
		return
	}

	var treeResp model.AgentPathTreeResponse
	payload := map[string]any{
		"path":          req.Path,
		"max_depth":     req.MaxDepth,
		"include_files": req.IncludeFiles,
	}
	if err := h.callAgentJSON(r.Context(), agent.ListenAddr, "/api/v1/fs/tree", payload, &treeResp); err != nil {
		writeError(w, http.StatusBadGateway, "AGENT_TREE_FAILED", err.Error())
		return
	}
	if strings.TrimSpace(req.SourceID) != "" {
		fileStats, err := h.fetchTreeFileStats(r.Context(), agent.ListenAddr, treeResp.Items)
		if err != nil {
			writeError(w, http.StatusBadGateway, "AGENT_TREE_STAT_FAILED", err.Error())
			return
		}
		items, token, err := h.store.BuildTreeUpdateState(r.Context(), req.SourceID, treeResp.Items, fileStats)
		if err != nil {
			if errors.Is(err, gorm.ErrRecordNotFound) {
				writeError(w, http.StatusNotFound, "SOURCE_NOT_FOUND", "source not found")
				return
			}
			writeError(w, http.StatusInternalServerError, "BUILD_TREE_STATE_FAILED", err.Error())
			return
		}
		if req.ChangesOnly {
			items = filterTreeToChanged(items)
		}
		treeResp.Items = items
		treeResp.SelectionToken = token
	}
	writeJSON(w, http.StatusOK, treeResp)
}

func (h *Handler) callAgentJSON(ctx context.Context, baseURL, apiPath string, reqBody, out any) error {
	if strings.TrimSpace(baseURL) == "" {
		return fmt.Errorf("empty agent listen_addr")
	}
	u, err := url.Parse(strings.TrimRight(baseURL, "/") + apiPath)
	if err != nil {
		return fmt.Errorf("invalid agent url: %w", err)
	}

	data, err := json.Marshal(reqBody)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u.String(), bytes.NewReader(data))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if h.agentToken != "" {
		req.Header.Set("Authorization", "Bearer "+h.agentToken)
	}

	resp, err := h.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("agent returned %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	if out == nil {
		return nil
	}
	return json.NewDecoder(resp.Body).Decode(out)
}

func decodeJSON(w http.ResponseWriter, r *http.Request, out any) bool {
	if err := json.NewDecoder(r.Body).Decode(out); err != nil {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", "invalid JSON: "+err.Error())
		return false
	}
	return true
}

func decodeJSONStrict(w http.ResponseWriter, r *http.Request, out any) bool {
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(out); err != nil {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", "invalid JSON: "+err.Error())
		return false
	}
	return true
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, status int, code, msg string) {
	writeJSON(w, status, model.ErrorResponse{Code: code, Message: msg})
}

func parseIntDefault(raw string, fallback int) int {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return fallback
	}
	v, err := strconv.Atoi(raw)
	if err != nil {
		return fallback
	}
	return v
}

func parsePathInt64(w http.ResponseWriter, r *http.Request, name string) (int64, bool) {
	raw := strings.TrimSpace(r.PathValue(name))
	if raw == "" {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", fmt.Sprintf("%s is required", name))
		return 0, false
	}
	id, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || id <= 0 {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", fmt.Sprintf("invalid %s", name))
		return 0, false
	}
	return id, true
}

func isBadRequestError(err error) bool {
	if err == nil {
		return false
	}
	msg := strings.ToLower(strings.TrimSpace(err.Error()))
	return strings.Contains(msg, "required") ||
		strings.Contains(msg, "must be >") ||
		strings.Contains(msg, "does not support retry")
}

func collectTreeFilePaths(items []model.TreeNode) []string {
	out := make([]string, 0, 64)
	seen := make(map[string]struct{}, 64)
	var walk func(nodes []model.TreeNode)
	walk = func(nodes []model.TreeNode) {
		for _, node := range nodes {
			if node.IsDir {
				if len(node.Children) > 0 {
					walk(node.Children)
				}
				continue
			}
			path := strings.TrimSpace(node.Key)
			if path == "" {
				continue
			}
			if _, ok := seen[path]; ok {
				continue
			}
			seen[path] = struct{}{}
			out = append(out, path)
		}
	}
	walk(items)
	return out
}

func (h *Handler) fetchTreeFileStats(ctx context.Context, agentAddr string, items []model.TreeNode) (map[string]model.TreeFileStat, error) {
	paths := collectTreeFilePaths(items)
	stats := make(map[string]model.TreeFileStat, len(paths))
	for _, path := range paths {
		var resp struct {
			Path     string    `json:"path"`
			Size     int64     `json:"size"`
			ModTime  time.Time `json:"mod_time"`
			IsDir    bool      `json:"is_dir"`
			Checksum string    `json:"checksum"`
		}
		if err := h.callAgentJSON(ctx, agentAddr, "/api/v1/fs/stat", map[string]any{"path": path}, &resp); err != nil {
			return nil, err
		}
		stat := model.TreeFileStat{
			Path:     path,
			Size:     resp.Size,
			IsDir:    resp.IsDir,
			Checksum: strings.TrimSpace(resp.Checksum),
		}
		if !resp.ModTime.IsZero() {
			mt := resp.ModTime.UTC()
			stat.ModTime = &mt
		}
		stats[path] = stat
	}
	return stats, nil
}

func filterTreeToChanged(items []model.TreeNode) []model.TreeNode {
	out := make([]model.TreeNode, 0, len(items))
	for _, node := range items {
		item := node
		if item.IsDir {
			item.Children = filterTreeToChanged(item.Children)
			if len(item.Children) > 0 || nodeHasChanged(item) {
				out = append(out, item)
			}
			continue
		}
		if nodeHasChanged(item) {
			out = append(out, item)
		}
	}
	return out
}

func nodeHasChanged(node model.TreeNode) bool {
	if node.HasUpdate != nil {
		return *node.HasUpdate
	}
	switch strings.ToUpper(strings.TrimSpace(node.UpdateType)) {
	case "NEW", "MODIFIED", "DELETED":
		return true
	default:
		return false
	}
}

func (h *Handler) searchCoreTaskStates(ctx context.Context, refs []store.SourceDocumentCoreRef) (map[string]coreclient.TaskState, error) {
	states := make(map[string]coreclient.TaskState, len(refs))
	if len(refs) == 0 {
		return states, nil
	}
	byDataset := make(map[string][]string, 4)
	seenByDataset := make(map[string]map[string]struct{}, 4)
	legacyIDs := make([]string, 0, len(refs))
	legacySeen := make(map[string]struct{}, len(refs))
	for _, ref := range refs {
		taskID := strings.TrimSpace(ref.CoreTaskID)
		if taskID == "" {
			continue
		}
		datasetID := strings.TrimSpace(ref.CoreDatasetID)
		if datasetID == "" {
			if _, ok := legacySeen[taskID]; ok {
				continue
			}
			legacySeen[taskID] = struct{}{}
			legacyIDs = append(legacyIDs, taskID)
			continue
		}
		if _, ok := seenByDataset[datasetID]; !ok {
			seenByDataset[datasetID] = make(map[string]struct{}, 16)
		}
		if _, ok := seenByDataset[datasetID][taskID]; ok {
			continue
		}
		seenByDataset[datasetID][taskID] = struct{}{}
		byDataset[datasetID] = append(byDataset[datasetID], taskID)
	}
	for datasetID, taskIDs := range byDataset {
		datasetStates, err := h.core.SearchTasksByDataset(ctx, datasetID, taskIDs)
		if err != nil {
			return nil, fmt.Errorf("dataset %s search failed: %w", datasetID, err)
		}
		for taskID, st := range datasetStates {
			states[taskID] = st
		}
	}
	if len(legacyIDs) > 0 {
		legacyStates, err := h.core.SearchTasks(ctx, legacyIDs)
		if err != nil {
			return nil, err
		}
		for taskID, st := range legacyStates {
			states[taskID] = st
		}
	}
	return states, nil
}

func buildSourceDocumentsSummaryWithCore(refs []store.SourceDocumentCoreRef, states map[string]coreclient.TaskState, storageBytes int64) model.SourceDocumentsSummary {
	var (
		parsedCount int64
		newCount    int64
		modCount    int64
		delCount    int64
	)
	for _, ref := range refs {
		update := inferDocumentUpdateType(ref.DesiredVersionID, ref.CurrentVersionID, ref.ParseStatus)
		switch update {
		case "NEW":
			newCount++
		case "MODIFIED":
			modCount++
		case "DELETED":
			delCount++
		}
		parseState := strings.ToUpper(strings.TrimSpace(ref.ParseStatus))
		taskID := strings.TrimSpace(ref.CoreTaskID)
		if taskID != "" {
			if taskState, ok := states[taskID]; ok {
				if s := strings.ToUpper(strings.TrimSpace(taskState.TaskState)); s != "" {
					parseState = s
				}
			}
		}
		if isCoreParsedState(parseState) ||
			(taskID == "" && strings.TrimSpace(ref.CurrentVersionID) != "" && strings.ToUpper(strings.TrimSpace(ref.ParseStatus)) != "DELETED") {
			parsedCount++
		}
	}
	return model.SourceDocumentsSummary{
		ParsedDocumentCount: parsedCount,
		StorageBytes:        storageBytes,
		TotalDocumentCount:  int64(len(refs)),
		NewCount:            newCount,
		ModifiedCount:       modCount,
		DeletedCount:        delCount,
		PendingPullCount:    newCount + modCount + delCount,
	}
}

func inferDocumentUpdateType(desiredVersionID, currentVersionID, parseStatus string) string {
	parseStatus = strings.ToUpper(strings.TrimSpace(parseStatus))
	desiredVersionID = strings.TrimSpace(desiredVersionID)
	currentVersionID = strings.TrimSpace(currentVersionID)
	if parseStatus == "DELETED" {
		return "DELETED"
	}
	if desiredVersionID != "" && currentVersionID == "" {
		return "NEW"
	}
	if desiredVersionID != "" && currentVersionID != "" && desiredVersionID != currentVersionID {
		return "MODIFIED"
	}
	if desiredVersionID != "" && desiredVersionID == currentVersionID {
		return "UNCHANGED"
	}
	return "UNKNOWN"
}

func isCoreParsedState(state string) bool {
	switch strings.ToUpper(strings.TrimSpace(state)) {
	case "SUCCEEDED", "SUCCESS", "COMPLETED", "DONE", "FINISHED", "TASK_STATE_SUCCEEDED", "TASK_STATE_SUCCESS":
		return true
	default:
		return false
	}
}
