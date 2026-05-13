package api

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"go.uber.org/zap"

	internal "github.com/lazyrag/file_watcher/internal"
	"github.com/lazyrag/file_watcher/internal/fs"
	"github.com/lazyrag/file_watcher/internal/source"
)

// Handler holds all HTTP handler dependencies.
type Handler struct {
	manager   source.Manager
	validator fs.PathValidator
	scanner   fs.Scanner
	staging   fs.StagingService
	mapper    fs.PathMapper
	log       *zap.Logger
}

// Tree POST /api/v1/fs/tree
func (h *Handler) Tree(w http.ResponseWriter, r *http.Request) {
	var req internal.TreeRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	if req.MaxDepth <= 0 {
		req.MaxDepth = 2
	}
	if req.MaxDepth > 8 {
		req.MaxDepth = 8
	}
	runtimePath := h.mapper.ToRuntime(req.Path)
	if err := h.validator.EnsureAllowed(runtimePath); err != nil {
		writeError(w, http.StatusForbidden, string(internal.ErrPathNotAllowed), err.Error())
		return
	}
	root, err := h.buildTreeNode(runtimePath, h.mapper.ToPublic(runtimePath), req.MaxDepth, req.IncludeFiles, 0)
	if err != nil {
		writeError(w, http.StatusBadRequest, string(internal.ErrInvalidPath), err.Error())
		return
	}
	writeJSON(w, http.StatusOK, internal.TreeResponse{Items: []internal.TreeNode{root}})
}

func NewHandler(manager source.Manager, validator fs.PathValidator, scanner fs.Scanner, staging fs.StagingService, mapper fs.PathMapper, log *zap.Logger) *Handler {
	if mapper == nil {
		mapper = fs.NewPathMapper("", nil)
	}
	return &Handler{manager: manager, validator: validator, scanner: scanner, staging: staging, mapper: mapper, log: log}
}

// Healthz GET /healthz
func (h *Handler) Healthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// Browse POST /api/v1/fs/browse
func (h *Handler) Browse(w http.ResponseWriter, r *http.Request) {
	var req internal.BrowseRequest
	if !decodeJSON(w, r, &req) {
		return
	}

	runtimePath := h.mapper.ToRuntime(req.Path)
	if err := h.validator.EnsureAllowed(runtimePath); err != nil {
		writeError(w, http.StatusForbidden, string(internal.ErrPathNotAllowed), err.Error())
		return
	}

	entries, err := os.ReadDir(runtimePath)
	if err != nil {
		writeError(w, http.StatusInternalServerError, string(internal.ErrInvalidPath), err.Error())
		return
	}

	resp := internal.BrowseResponse{Path: h.mapper.ToPublic(runtimePath), Entries: make([]internal.BrowseEntry, 0, len(entries))}
	for _, e := range entries {
		info, err := e.Info()
		if err != nil {
			continue
		}
		childRuntimePath := filepath.Join(runtimePath, e.Name())
		resp.Entries = append(resp.Entries, internal.BrowseEntry{
			Name:    e.Name(),
			Path:    h.mapper.ToPublic(childRuntimePath),
			IsDir:   e.IsDir(),
			Size:    info.Size(),
			ModTime: info.ModTime(),
		})
	}
	writeJSON(w, http.StatusOK, resp)
}

// ValidatePath POST /api/v1/fs/validate
func (h *Handler) ValidatePath(w http.ResponseWriter, r *http.Request) {
	var req internal.ValidatePathRequest
	if !decodeJSON(w, r, &req) {
		return
	}
	resp := h.validator.Validate(h.mapper.ToRuntime(req.Path))
	resp.Path = h.mapper.ToPublic(resp.Path)
	writeJSON(w, http.StatusOK, resp)
}

// StatFile POST /api/v1/fs/stat
func (h *Handler) StatFile(w http.ResponseWriter, r *http.Request) {
	var req internal.StatFileRequest
	if !decodeJSON(w, r, &req) {
		return
	}

	runtimePath := h.mapper.ToRuntime(req.Path)
	if err := h.validator.EnsureAllowed(runtimePath); err != nil {
		writeError(w, http.StatusForbidden, string(internal.ErrPathNotAllowed), err.Error())
		return
	}

	meta, err := h.scanner.Stat(r.Context(), runtimePath)
	if err != nil {
		writeError(w, http.StatusInternalServerError, string(internal.ErrInvalidPath), err.Error())
		return
	}

	writeJSON(w, http.StatusOK, internal.StatFileResponse{
		Path:     meta.Path,
		Size:     meta.Size,
		ModTime:  meta.ModTime,
		IsDir:    meta.IsDir,
		MimeType: meta.MimeType,
		Checksum: meta.Checksum,
	})
}

// StartSource POST /api/v1/sources/start
func (h *Handler) StartSource(w http.ResponseWriter, r *http.Request) {
	var req internal.StartSourceRequest
	if !decodeJSON(w, r, &req) {
		return
	}

	if err := h.manager.StartSource(r.Context(), req); err != nil {
		writeError(w, http.StatusBadRequest, "START_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, internal.StartSourceResponse{Started: true})
}

// StopSource POST /api/v1/sources/stop
func (h *Handler) StopSource(w http.ResponseWriter, r *http.Request) {
	var req internal.StopSourceRequest
	if !decodeJSON(w, r, &req) {
		return
	}

	if err := h.manager.StopSource(r.Context(), req.SourceID); err != nil {
		writeError(w, http.StatusBadRequest, "STOP_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, internal.AcceptedResponse{Accepted: true})
}

// ScanSource POST /api/v1/sources/scan
func (h *Handler) ScanSource(w http.ResponseWriter, r *http.Request) {
	var req internal.ScanSourceRequest
	if !decodeJSON(w, r, &req) {
		return
	}

	if err := h.manager.TriggerScan(r.Context(), req.SourceID, req.Mode); err != nil {
		writeError(w, http.StatusBadRequest, "SCAN_FAILED", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, internal.AcceptedResponse{Accepted: true})
}

// StageFile POST /api/v1/fs/stage
func (h *Handler) StageFile(w http.ResponseWriter, r *http.Request) {
	var req internal.StageFileRequest
	if !decodeJSON(w, r, &req) {
		return
	}

	runtimePath := h.mapper.ToRuntime(req.SrcPath)
	if err := h.validator.EnsureAllowed(runtimePath); err != nil {
		writeError(w, http.StatusForbidden, string(internal.ErrPathNotAllowed), err.Error())
		return
	}

	result, err := h.staging.StageFile(r.Context(), req.SourceID, req.DocumentID, req.VersionID, runtimePath)
	if err != nil {
		writeError(w, http.StatusInternalServerError, string(internal.ErrStageFailed), err.Error())
		return
	}

	writeJSON(w, http.StatusOK, internal.StageFileResponse{
		HostPath:      result.HostPath,
		ContainerPath: result.ContainerPath,
		URI:           result.URI,
		Size:          result.Size,
	})
}

func (h *Handler) buildTreeNode(runtimePath, publicPath string, maxDepth int, includeFiles bool, depth int) (internal.TreeNode, error) {
	name := publicBase(publicPath)
	if name == "." || name == "/" || name == "\\" {
		name = publicPath
	}
	node := internal.TreeNode{
		Title: name,
		Key:   h.mapper.CleanPublic(publicPath),
		IsDir: true,
	}
	if depth >= maxDepth {
		return node, nil
	}
	entries, err := os.ReadDir(runtimePath)
	if err != nil {
		return node, err
	}
	children := make([]internal.TreeNode, 0, len(entries))
	for _, entry := range entries {
		childRuntimePath := filepath.Join(runtimePath, entry.Name())
		childPublicPath := h.mapper.ToPublic(childRuntimePath)
		if err := h.validator.EnsureAllowed(childRuntimePath); err != nil {
			continue
		}
		if entry.IsDir() {
			next, err := h.buildTreeNode(childRuntimePath, childPublicPath, maxDepth, includeFiles, depth+1)
			if err != nil {
				continue
			}
			children = append(children, next)
			continue
		}
		if !includeFiles {
			continue
		}
		children = append(children, internal.TreeNode{
			Title: entry.Name(),
			Key:   h.mapper.CleanPublic(childPublicPath),
			IsDir: false,
		})
	}
	node.Children = children
	return node, nil
}

func publicBase(path string) string {
	clean := strings.TrimRight(strings.ReplaceAll(path, "\\", "/"), "/")
	if clean == "" {
		return path
	}
	idx := strings.LastIndex(clean, "/")
	if idx < 0 {
		return clean
	}
	return clean[idx+1:]
}

// ─── helpers ─────────────────────────────────────────────────────────────────

func decodeJSON(w http.ResponseWriter, r *http.Request, v any) bool {
	if err := json.NewDecoder(r.Body).Decode(v); err != nil {
		writeError(w, http.StatusBadRequest, "BAD_REQUEST", "invalid JSON: "+err.Error())
		return false
	}
	return true
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, code, msg string) {
	writeJSON(w, status, internal.ErrorResponse{Code: code, Message: msg})
}
