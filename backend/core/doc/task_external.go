package doc

import (
	"net/http"
	"time"

	"lazyrag/core/common"
	"lazyrag/core/log"
)

type addResultItem struct {
	TaskID         string
	DocID          string
	FilePath       string
	DisplayName    string
	CoreTaskID     string
	CoreDocumentID string
	Metadata       map[string]any
}

type addFileItem struct {
	FilePath string         `json:"file_path"`
	DocID    string         `json:"doc_id,omitempty"`
	Metadata map[string]any `json:"metadata,omitempty"`
}

type addRequest struct {
	Items          []addFileItem `json:"items"`
	KbID           string        `json:"kb_id,omitempty"`
	AlgoID         string        `json:"algo_id,omitempty"`
	SourceType     string        `json:"source_type,omitempty"`
	IdempotencyKey string        `json:"idempotency_key,omitempty"`
}

type reparseRequest struct {
	DocIDs         []string `json:"doc_ids"`
	KbID           string   `json:"kb_id,omitempty"`
	AlgoID         string   `json:"algo_id,omitempty"`
	IdempotencyKey string   `json:"idempotency_key,omitempty"`
}

type transferItem struct {
	DocID        string `json:"doc_id"`
	TargetDocID  string `json:"target_doc_id,omitempty"`
	SourceKbID   string `json:"source_kb_id,omitempty"`
	SourceAlgoID string `json:"source_algo_id,omitempty"`
	TargetKbID   string `json:"target_kb_id,omitempty"`
	TargetAlgoID string `json:"target_algo_id,omitempty"`
	Mode         string `json:"mode,omitempty"`
}

type transferRequest struct {
	Items          []transferItem `json:"items"`
	IdempotencyKey string         `json:"idempotency_key,omitempty"`
}

func callExternalAddDocs(r *http.Request, req addRequest) ([]addResultItem, error) {
	url := common.JoinURL(parsingServiceEndpoint(), "/v1/docs/add")
	log.Logger.Info().
		Str("handler", "StartTask").
		Str("external_url", url).
		Int("items_count", len(req.Items)).
		Any("request_body", req).
		Msg("calling external add-docs request")
	for i, item := range req.Items {
		log.Logger.Info().
			Str("handler", "StartTask").
			Str("external_url", url).
			Int("item_index", i).
			Str("doc_id", item.DocID).
			Str("file_path", item.FilePath).
			Any("metadata", item.Metadata).
			Msg("calling external add-docs item")
	}
	var resp any
	if err := common.ApiPost(r.Context(), url, req, nil, &resp, 15*time.Second); err != nil {
		log.Logger.Error().
			Err(err).
			Str("handler", "StartTask").
			Str("external_url", url).
			Int("items_count", len(req.Items)).
			Any("request_body", req).
			Msg("external add-docs request failed")
		return nil, err
	}
	log.Logger.Info().
		Str("handler", "StartTask").
		Str("external_url", url).
		Int("items_count", len(req.Items)).
		Any("request_body", req).
		Any("response_body", resp).
		Msg("external add-docs request succeeded")
	return parseAddResponse(resp, req), nil
}

func callExternalReparseDocs(r *http.Request, req reparseRequest) error {
	var resp map[string]any
	return common.ApiPost(r.Context(), common.JoinURL(parsingServiceEndpoint(), "/v1/docs/reparse"), req, nil, &resp, 15*time.Second)
}

func callExternalTransferDocs(r *http.Request, req transferRequest) error {
	var resp map[string]any
	return common.ApiPost(r.Context(), common.JoinURL(parsingServiceEndpoint(), "/v1/docs/transfer"), req, nil, &resp, 15*time.Second)
}

func callExternalSuspendJob(r *http.Request, req ExternalCancelTaskRequest) error {
	url := common.JoinURL(parsingServiceEndpoint(), "/v1/tasks/cancel")
	var resp map[string]any
	return common.ApiPost(r.Context(), url, req, nil, &resp, 15*time.Second)
}

func parseAddResponse(resp any, req addRequest) []addResultItem {
	items := make([]addResultItem, 0)
	for _, in := range req.Items {
		items = append(items, addResultItem{
			TaskID:         firstString(in.Metadata, "task_id", "external_task_id"),
			DocID:          firstNonEmpty(in.DocID, firstString(in.Metadata, "doc_id", "document_id")),
			FilePath:       in.FilePath,
			DisplayName:    firstString(in.Metadata, "display_name", "filename", "name"),
			CoreTaskID:     firstString(in.Metadata, "core_task_id"),
			CoreDocumentID: firstString(in.Metadata, "core_document_id"),
			Metadata:       in.Metadata,
		})
	}

	root, ok := resp.(map[string]any)
	if !ok {
		return items
	}
	parseArray := func(arr []any) []addResultItem {
		parsed := make([]addResultItem, 0, len(arr))
		for i, one := range arr {
			m, ok := one.(map[string]any)
			if !ok {
				continue
			}
			fallback := addResultItem{}
			if i < len(items) {
				fallback = items[i]
			}
			meta := nestedMap(m, "metadata")
			if len(meta) == 0 {
				meta = fallback.Metadata
			}
			parsed = append(parsed, addResultItem{
				TaskID:         firstAnyStringWithMeta(m, meta, fallback.TaskID, "task_id", "id", "service_task_id"),
				DocID:          firstAnyStringWithMeta(m, meta, fallback.DocID, "doc_id", "document_id"),
				FilePath:       firstAnyStringWithMeta(m, meta, fallback.FilePath, "file_path", "path"),
				DisplayName:    firstAnyStringWithMeta(m, meta, fallback.DisplayName, "display_name", "filename", "name"),
				CoreTaskID:     firstAnyStringWithMeta(m, meta, fallback.CoreTaskID, "core_task_id"),
				CoreDocumentID: firstAnyStringWithMeta(m, meta, fallback.CoreDocumentID, "core_document_id"),
				Metadata:       meta,
			})
		}
		return parsed
	}
	for _, key := range []string{"items", "results", "data", "documents", "tasks"} {
		raw, exists := root[key]
		if !exists {
			continue
		}
		if arr, ok := raw.([]any); ok {
			if parsed := parseArray(arr); len(parsed) > 0 {
				return parsed
			}
			continue
		}
		if obj, ok := raw.(map[string]any); ok {
			for _, nestedKey := range []string{"items", "results", "documents", "tasks"} {
				nestedRaw, exists := obj[nestedKey]
				if !exists {
					continue
				}
				arr, ok := nestedRaw.([]any)
				if !ok {
					continue
				}
				if parsed := parseArray(arr); len(parsed) > 0 {
					return parsed
				}
			}
		}
	}
	return items
}

func firstString(m map[string]any, keys ...string) string {
	for _, key := range keys {
		if v, ok := m[key]; ok {
			switch vv := v.(type) {
			case string:
				if vv != "" {
					return vv
				}
			}
		}
	}
	return ""
}

func firstAnyString(m map[string]any, fallback string, keys ...string) string {
	for _, key := range keys {
		if v, ok := m[key]; ok {
			switch vv := v.(type) {
			case string:
				if vv != "" {
					return vv
				}
			}
		}
	}
	return fallback
}

func firstAnyStringWithMeta(m map[string]any, meta map[string]any, fallback string, keys ...string) string {
	if v := firstAnyString(m, "", keys...); v != "" {
		return v
	}
	if len(meta) > 0 {
		if v := firstAnyString(meta, "", keys...); v != "" {
			return v
		}
	}
	return fallback
}

func nestedMap(m map[string]any, key string) map[string]any {
	if v, ok := m[key]; ok {
		if mm, ok := v.(map[string]any); ok {
			return mm
		}
	}
	return nil
}
