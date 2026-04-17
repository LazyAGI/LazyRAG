package api

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"

	"go.uber.org/zap"

	internal "github.com/lazyrag/file_watcher/internal"
	"github.com/lazyrag/file_watcher/internal/fs"
	"github.com/lazyrag/file_watcher/internal/source"
)

// Handler 持有所有 HTTP handler 依赖。
type Handler struct {
	manager   source.Manager
	validator fs.PathValidator
	scanner   fs.Scanner
	staging   fs.StagingService
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
	if err := h.validator.EnsureAllowed(req.Path); err != nil {
		writeError(w, http.StatusForbidden, string(internal.ErrPathNotAllowed), err.Error())
		return
	}
	root, err := h.buildTreeNode(req.Path, req.MaxDepth, req.IncludeFiles, 0)
	if err != nil {
		writeError(w, http.StatusBadRequest, string(internal.ErrInvalidPath), err.Error())
		return
	}
	writeJSON(w, http.StatusOK, internal.TreeResponse{Items: []internal.TreeNode{root}})
}

func NewHandler(manager source.Manager, validator fs.PathValidator, scanner fs.Scanner, staging fs.StagingService, log *zap.Logger) *Handler {
	return &Handler{manager: manager, validator: validator, scanner: scanner, staging: staging, log: log}
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

	if err := h.validator.EnsureAllowed(req.Path); err != nil {
		writeError(w, http.StatusForbidden, string(internal.ErrPathNotAllowed), err.Error())
		return
	}

	entries, err := os.ReadDir(req.Path)
	if err != nil {
		writeError(w, http.StatusInternalServerError, string(internal.ErrInvalidPath), err.Error())
		return
	}

	resp := internal.BrowseResponse{Path: req.Path, Entries: make([]internal.BrowseEntry, 0, len(entries))}
	for _, e := range entries {
		info, err := e.Info()
		if err != nil {
			continue
		}
		resp.Entries = append(resp.Entries, internal.BrowseEntry{
			Name:    e.Name(),
			Path:    req.Path + "/" + e.Name(),
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
	resp := h.validator.Validate(req.Path)
	writeJSON(w, http.StatusOK, resp)
}

// StatFile POST /api/v1/fs/stat
func (h *Handler) StatFile(w http.ResponseWriter, r *http.Request) {
	var req internal.StatFileRequest
	if !decodeJSON(w, r, &req) {
		return
	}

	if err := h.validator.EnsureAllowed(req.Path); err != nil {
		writeError(w, http.StatusForbidden, string(internal.ErrPathNotAllowed), err.Error())
		return
	}

	meta, err := h.scanner.Stat(r.Context(), req.Path)
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

	if err := h.validator.EnsureAllowed(req.SrcPath); err != nil {
		writeError(w, http.StatusForbidden, string(internal.ErrPathNotAllowed), err.Error())
		return
	}

	result, err := h.staging.StageFile(r.Context(), req.SourceID, req.DocumentID, req.VersionID, req.SrcPath)
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

func (h *Handler) buildTreeNode(path string, maxDepth int, includeFiles bool, depth int) (internal.TreeNode, error) {
	name := filepath.Base(path)
	if name == "." || name == "/" {
		name = path
	}
	node := internal.TreeNode{
		Title: name,
		Key:   filepath.Clean(path),
		IsDir: true,
	}
	if depth >= maxDepth {
		return node, nil
	}
	entries, err := os.ReadDir(path)
	if err != nil {
		return node, err
	}
	children := make([]internal.TreeNode, 0, len(entries))
	for _, entry := range entries {
		childPath := filepath.Join(path, entry.Name())
		if err := h.validator.EnsureAllowed(childPath); err != nil {
			continue
		}
		if entry.IsDir() {
			next, err := h.buildTreeNode(childPath, maxDepth, includeFiles, depth+1)
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
			Key:   filepath.Clean(childPath),
			IsDir: false,
		})
	}
	node.Children = children
	return node, nil
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
