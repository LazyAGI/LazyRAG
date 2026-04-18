package server

import (
	"encoding/json"
	"net/http"
	"strings"

	"gopkg.in/yaml.v3"
)

func (h *Handler) docs(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	specURL := openAPIJSONPath
	if strings.HasPrefix(strings.TrimSpace(r.URL.Path), scanFrontendPrefix) {
		specURL = scanOpenAPIJSONPath
	}
	_, _ = w.Write([]byte(docsHTML(specURL)))
}

func (h *Handler) openapiJSON(w http.ResponseWriter, _ *http.Request) {
	spec := buildOpenAPISpec()
	writeJSON(w, http.StatusOK, spec)
}

func (h *Handler) openapiYAML(w http.ResponseWriter, _ *http.Request) {
	spec := buildOpenAPISpec()
	body, err := yaml.Marshal(spec)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "OPENAPI_YAML_FAILED", "marshal OpenAPI yaml failed")
		return
	}
	w.Header().Set("Content-Type", "application/x-yaml")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(body)
}

func buildOpenAPISpec() map[string]any {
	return map[string]any{
		"openapi": "3.0.3",
		"info": map[string]any{
			"title":       "Scan Control Plane API",
			"version":     "0.1.0",
			"description": "Control plane for local source management, agent coordination, and idle-window scheduling.",
		},
		"servers": []map[string]any{
			{
				"url":         "/",
				"description": "same origin",
			},
		},
		"paths": map[string]any{
			"/healthz": map[string]any{
				"get": op("Health check", nil, map[string]any{
					"200": resp("OK", inlineObj(map[string]any{
						"status": strSchema(),
					}, []string{"status"})),
				}),
			},
			"/api/scan/sources": map[string]any{
				"get": op("List sources", nil, map[string]any{
					"200": resp("Source list", inlineObj(map[string]any{
						"items": arrSchema(refSchema("Source")),
					}, []string{"items"})),
				}),
				"post": op("Create source", reqBody(refSchema("CreateSourceRequest")), map[string]any{
					"200": resp("Created source", refSchema("Source")),
					"400": errResp(),
				}),
			},
			"/api/scan/knowledge-bases": map[string]any{
				"post": op("Create knowledge base in core and grant current user read permission", reqBody(refSchema("CreateKnowledgeBaseRequest")), map[string]any{
					"200": resp("Created knowledge base", refSchema("CreateKnowledgeBaseResponse")),
					"400": errResp(),
					"502": errResp(),
				}),
			},
			"/api/scan/sources/{id}": map[string]any{
				"get": op("Get source", nil, map[string]any{
					"200": resp("Source", refSchema("Source")),
					"404": errResp(),
				}, pathParam("id")),
				"put": op("Update source", reqBody(refSchema("UpdateSourceRequest")), map[string]any{
					"200": resp("Updated source", refSchema("Source")),
					"400": errResp(),
					"404": errResp(),
				}, pathParam("id")),
			},
			"/api/scan/sources/{id}/enable": map[string]any{
				"post": op("Enable source", nil, map[string]any{
					"200": resp("Source", refSchema("Source")),
					"404": errResp(),
				}, pathParam("id")),
			},
			"/api/scan/sources/{id}/disable": map[string]any{
				"post": op("Disable source", nil, map[string]any{
					"200": resp("Source", refSchema("Source")),
					"404": errResp(),
				}, pathParam("id")),
			},
			"/api/scan/sources/{id}/tasks/generate": map[string]any{
				"post": op("Generate parse tasks for source", reqBody(refSchema("GenerateTasksRequest")), map[string]any{
					"200": resp("Generated task stats", refSchema("GenerateTasksResponse")),
					"400": errResp(),
					"404": errResp(),
				}, pathParam("id")),
			},
			"/api/scan/sources/{id}/watch/enable": map[string]any{
				"post": op("Enable source watch", reqBody(refSchema("EnableWatchRequest")), map[string]any{
					"200": resp("Watch toggle result", refSchema("WatchToggleResponse")),
					"400": errResp(),
					"404": errResp(),
				}, pathParam("id")),
			},
			"/api/scan/sources/{id}/watch/disable": map[string]any{
				"post": op("Disable source watch", nil, map[string]any{
					"200": resp("Watch toggle result", refSchema("WatchToggleResponse")),
					"400": errResp(),
					"404": errResp(),
				}, pathParam("id")),
			},
			"/api/scan/sources/{id}/tasks/expedite": map[string]any{
				"post": op("Expedite source tasks by paths", reqBody(refSchema("ExpediteTasksRequest")), map[string]any{
					"200": resp("Expedite stats", refSchema("ExpediteTasksResponse")),
					"400": errResp(),
					"404": errResp(),
				}, pathParam("id")),
			},
			"/api/scan/sources/{id}/documents": map[string]any{
				"get": op("List source documents", nil, map[string]any{
					"200": resp("Source documents", refSchema("SourceDocumentsResponse")),
					"400": errResp(),
					"404": errResp(),
					"500": errResp(),
				},
					pathParam("id"),
					queryParam("tenant_id", true),
					queryParam("keyword", false),
					queryParam("update_type", false),
					queryParam("parse_state", false),
					queryIntParam("page", false),
					queryIntParam("page_size", false),
				),
			},
			"/api/scan/sources/{id}/manual-pull-jobs": map[string]any{
				"get": op("List source manual pull jobs", nil, map[string]any{
					"200": resp("Manual pull jobs", refSchema("ListManualPullJobsResponse")),
					"400": errResp(),
					"404": errResp(),
					"500": errResp(),
				},
					pathParam("id"),
					queryParam("status", false),
					queryIntParam("page", false),
					queryIntParam("page_size", false),
				),
			},
			"/api/scan/parse-tasks": map[string]any{
				"get": op("List parse tasks", nil, map[string]any{
					"200": resp("Parse task list", refSchema("ListParseTasksResponse")),
					"400": errResp(),
					"500": errResp(),
				},
					queryParam("tenant_id", true),
					queryParam("source_id", false),
					queryParam("status", false),
					queryParam("keyword", false),
					queryIntParam("page", false),
					queryIntParam("page_size", false),
				),
			},
			"/api/scan/parse-tasks/stats": map[string]any{
				"get": op("Parse task status stats", nil, map[string]any{
					"200": resp("Status counts", refSchema("ParseTaskStatsResponse")),
					"400": errResp(),
					"500": errResp(),
				},
					queryParam("tenant_id", true),
					queryParam("source_id", false),
				),
			},
			"/api/scan/parse-tasks/{id}": map[string]any{
				"get": op("Get parse task detail", nil, map[string]any{
					"200": resp("Parse task detail", refSchema("ParseTaskDetailResponse")),
					"404": errResp(),
					"500": errResp(),
				}, pathParam("id")),
			},
			"/api/scan/parse-tasks/{id}/retry": map[string]any{
				"post": op("Retry parse task", nil, map[string]any{
					"200": resp("Retried parse task detail", refSchema("ParseTaskDetailResponse")),
					"400": errResp(),
					"404": errResp(),
					"500": errResp(),
				}, pathParam("id")),
			},
			"/api/scan/agents": map[string]any{
				"get": op("List agents", nil, map[string]any{
					"200": resp("Agent list", inlineObj(map[string]any{
						"items": arrSchema(refSchema("Agent")),
					}, []string{"items"})),
				}),
			},
			"/api/scan/agents/{id}": map[string]any{
				"get": op("Get agent", nil, map[string]any{
					"200": resp("Agent", refSchema("Agent")),
					"404": errResp(),
				}, pathParam("id")),
			},
			"/api/v1/agents/register": map[string]any{
				"post": op("Register agent", reqBody(refSchema("RegisterAgentRequest")), map[string]any{
					"200": acceptedResp(),
					"400": errResp(),
				}),
			},
			"/api/v1/agents/heartbeat": map[string]any{
				"post": op("Report heartbeat", reqBody(refSchema("HeartbeatPayload")), map[string]any{
					"200": acceptedResp(),
					"400": errResp(),
				}),
			},
			"/api/v1/agents/pull": map[string]any{
				"post": op("Pull commands", reqBody(refSchema("PullCommandsRequest")), map[string]any{
					"200": resp("Commands", refSchema("PullCommandsResponse")),
					"500": errResp(),
				}),
			},
			"/api/v1/agents/commands/ack": map[string]any{
				"post": op("Acknowledge command", reqBody(refSchema("AckCommandRequest")), map[string]any{
					"200": acceptedResp(),
					"400": errResp(),
				}),
			},
			"/api/v1/agents/snapshots/report": map[string]any{
				"post": op("Report reconcile snapshot metadata", reqBody(refSchema("ReportSnapshotRequest")), map[string]any{
					"200": acceptedResp(),
					"400": errResp(),
				}),
			},
			"/api/v1/agents/events": map[string]any{
				"post": op("Report file events", reqBody(refSchema("ReportEventsRequest")), map[string]any{
					"200": acceptedResp(),
					"500": errResp(),
				}),
			},
			"/api/v1/agents/scan-results": map[string]any{
				"post": op("Report scan results", reqBody(refSchema("ReportScanResultsRequest")), map[string]any{
					"200": acceptedResp(),
					"500": errResp(),
				}),
			},
			"/api/scan/agents/fs/validate": map[string]any{
				"post": op("Validate path via agent", reqBody(refSchema("AgentPathRequest")), map[string]any{
					"200": resp("Path validation result", refSchema("AgentPathValidateResponse")),
					"404": errResp(),
					"502": errResp(),
				}),
			},
			"/api/scan/agents/fs/tree": map[string]any{
				"post": op("Get directory tree via agent", reqBody(refSchema("AgentPathTreeRequest")), map[string]any{
					"200": resp("Directory tree", refSchema("AgentPathTreeResponse")),
					"404": errResp(),
					"502": errResp(),
				}),
			},
		},
		"components": map[string]any{
			"schemas": schemas(),
		},
	}
}

func schemas() map[string]any {
	// Keep schemas aligned with model DTOs used by handlers.
	return map[string]any{
		"ErrorResponse": inlineObj(map[string]any{
			"code":    strSchema(),
			"message": strSchema(),
		}, []string{"code", "message"}),
		"Source": inlineObj(map[string]any{
			"id":                      strSchema(),
			"tenant_id":               strSchema(),
			"name":                    strSchema(),
			"source_type":             strSchema(),
			"root_path":               strSchema(),
			"status":                  strSchema(),
			"watch_enabled":           boolSchema(),
			"idle_window_seconds":     intSchema(),
			"reconcile_seconds":       intSchema(),
			"reconcile_schedule":      strSchema(),
			"agent_id":                strSchema(),
			"dataset_id":              strSchema(),
			"default_origin_type":     strSchema(),
			"default_origin_platform": strSchema(),
			"default_trigger_policy":  strSchema(),
			"created_at":              dateTimeSchema(),
			"updated_at":              dateTimeSchema(),
		}, []string{"id", "tenant_id", "name", "source_type", "root_path", "status", "watch_enabled", "idle_window_seconds", "reconcile_seconds", "agent_id", "created_at", "updated_at"}),
		"CreateSourceRequest": inlineObj(map[string]any{
			"tenant_id":               strSchema(),
			"name":                    strSchema(),
			"root_path":               strSchema(),
			"agent_id":                strSchema(),
			"dataset_id":              strSchema(),
			"watch_enabled":           boolSchema(),
			"idle_window_seconds":     intSchema(),
			"reconcile_seconds":       intSchema(),
			"reconcile_schedule":      strSchema(),
			"default_origin_type":     strSchema(),
			"default_origin_platform": strSchema(),
			"default_trigger_policy":  strSchema(),
		}, []string{"tenant_id", "name", "root_path", "agent_id"}),
		"CreateKnowledgeBaseRequest": inlineObj(map[string]any{
			"name": strSchema(),
			"algo": inlineObj(map[string]any{
				"algo_id":      strSchema(),
				"description":  strSchema(),
				"display_name": strSchema(),
			}, []string{"algo_id"}),
		}, []string{"name", "algo"}),
		"CreateKnowledgeBaseResponse": inlineObj(map[string]any{
			"dataset_id": strSchema(),
			"name":       strSchema(),
		}, []string{"dataset_id", "name"}),
		"UpdateSourceRequest": inlineObj(map[string]any{
			"name":                    strSchema(),
			"root_path":               strSchema(),
			"dataset_id":              strSchema(),
			"idle_window_seconds":     intSchema(),
			"reconcile_seconds":       intSchema(),
			"reconcile_schedule":      strSchema(),
			"default_origin_type":     strSchema(),
			"default_origin_platform": strSchema(),
			"default_trigger_policy":  strSchema(),
		}, nil),
		"Agent": inlineObj(map[string]any{
			"agent_id":            strSchema(),
			"tenant_id":           strSchema(),
			"hostname":            strSchema(),
			"version":             strSchema(),
			"status":              strSchema(),
			"listen_addr":         strSchema(),
			"last_heartbeat_at":   dateTimeSchema(),
			"active_source_count": intSchema(),
			"active_watch_count":  intSchema(),
			"active_task_count":   intSchema(),
			"updated_at":          dateTimeSchema(),
		}, []string{"agent_id", "tenant_id", "status", "listen_addr"}),
		"RegisterAgentRequest": inlineObj(map[string]any{
			"agent_id":    strSchema(),
			"tenant_id":   strSchema(),
			"hostname":    strSchema(),
			"version":     strSchema(),
			"listen_addr": strSchema(),
		}, []string{"agent_id", "tenant_id", "hostname", "version"}),
		"HeartbeatPayload": inlineObj(map[string]any{
			"agent_id":           strSchema(),
			"tenant_id":          strSchema(),
			"hostname":           strSchema(),
			"version":            strSchema(),
			"status":             strSchema(),
			"last_heartbeat_at":  dateTimeSchema(),
			"source_count":       intSchema(),
			"active_watch_count": intSchema(),
			"active_task_count":  intSchema(),
			"listen_addr":        strSchema(),
		}, []string{"agent_id", "tenant_id", "status"}),
		"PullCommandsRequest": inlineObj(map[string]any{
			"agent_id":  strSchema(),
			"tenant_id": strSchema(),
		}, []string{"agent_id", "tenant_id"}),
		"PulledCommand": inlineObj(map[string]any{
			"id":                 intSchema(),
			"type":               strSchema(),
			"tenant_id":          strSchema(),
			"source_id":          strSchema(),
			"root_path":          strSchema(),
			"mode":               strSchema(),
			"reason":             strSchema(),
			"skip_initial_scan":  boolSchema(),
			"reconcile_seconds":  intSchema(),
			"reconcile_schedule": strSchema(),
			"document_id":        strSchema(),
			"version_id":         strSchema(),
			"src_path":           strSchema(),
		}, []string{"id", "type"}),
		"GenerateTasksRequest": inlineObj(map[string]any{
			"mode":            strSchema(),
			"paths":           arrSchema(strSchema()),
			"trigger_policy":  strSchema(),
			"updated_only":    boolSchema(),
			"selection_token": strSchema(),
		}, []string{"mode", "paths"}),
		"GenerateTasksResponse": inlineObj(map[string]any{
			"requested_count":          intSchema(),
			"accepted_count":           intSchema(),
			"merged_pending_count":     intSchema(),
			"skipped_count":            intSchema(),
			"ignored_unchanged_count":  intSchema(),
			"baseline_snapshot_queued": boolSchema(),
			"manual_pull_job_id":       strSchema(),
		}, []string{"requested_count", "accepted_count", "merged_pending_count", "skipped_count"}),
		"EnableWatchRequest": inlineObj(map[string]any{
			"reconcile_seconds":  intSchema(),
			"reconcile_schedule": strSchema(),
		}, nil),
		"WatchToggleResponse": inlineObj(map[string]any{
			"accepted":                 boolSchema(),
			"skip_initial_scan":        boolSchema(),
			"baseline_snapshot_queued": boolSchema(),
		}, []string{"accepted"}),
		"ExpediteTasksRequest": inlineObj(map[string]any{
			"paths": arrSchema(strSchema()),
		}, []string{"paths"}),
		"ExpediteTasksResponse": inlineObj(map[string]any{
			"updated_existing_task_count": intSchema(),
			"created_task_count":          intSchema(),
			"skipped_count":               intSchema(),
		}, []string{"updated_existing_task_count", "created_task_count", "skipped_count"}),
		"SourceDocumentsSource": inlineObj(map[string]any{
			"id":                        strSchema(),
			"name":                      strSchema(),
			"root_path":                 strSchema(),
			"watch_enabled":             boolSchema(),
			"agent_id":                  strSchema(),
			"agent_online":              boolSchema(),
			"update_tracking_supported": boolSchema(),
			"last_synced_at":            dateTimeSchema(),
		}, []string{"id", "name", "root_path", "watch_enabled", "agent_id", "agent_online", "update_tracking_supported"}),
		"SourceDocumentsSummary": inlineObj(map[string]any{
			"parsed_document_count": intSchema(),
			"storage_bytes":         intSchema(),
			"total_document_count":  intSchema(),
			"new_count":             intSchema(),
			"modified_count":        intSchema(),
			"deleted_count":         intSchema(),
			"pending_pull_count":    intSchema(),
		}, []string{"parsed_document_count", "storage_bytes", "total_document_count", "new_count", "modified_count", "deleted_count", "pending_pull_count"}),
		"SourceDocumentItem": inlineObj(map[string]any{
			"document_id":               intSchema(),
			"name":                      strSchema(),
			"path":                      strSchema(),
			"directory":                 strSchema(),
			"tags":                      arrSchema(strSchema()),
			"has_update":                boolSchema(),
			"update_type":               strSchema(),
			"update_desc":               strSchema(),
			"parse_state":               strSchema(),
			"file_type":                 strSchema(),
			"size_bytes":                intSchema(),
			"last_synced_at":            dateTimeSchema(),
			"core_dataset_id":           strSchema(),
			"core_task_id":              strSchema(),
			"core_task_state":           strSchema(),
			"scan_orchestration_status": strSchema(),
		}, []string{"document_id", "name", "path", "directory", "parse_state", "size_bytes"}),
		"SourceDocumentsResponse": inlineObj(map[string]any{
			"source":    refSchema("SourceDocumentsSource"),
			"summary":   refSchema("SourceDocumentsSummary"),
			"items":     arrSchema(refSchema("SourceDocumentItem")),
			"total":     intSchema(),
			"page":      intSchema(),
			"page_size": intSchema(),
		}, []string{"source", "summary", "items", "total", "page", "page_size"}),
		"ManualPullJob": inlineObj(map[string]any{
			"job_id":                  strSchema(),
			"tenant_id":               strSchema(),
			"source_id":               strSchema(),
			"status":                  strSchema(),
			"mode":                    strSchema(),
			"trigger_policy":          strSchema(),
			"selection_token":         strSchema(),
			"updated_only":            boolSchema(),
			"requested_count":         intSchema(),
			"accepted_count":          intSchema(),
			"skipped_count":           intSchema(),
			"ignored_unchanged_count": intSchema(),
			"error_message":           strSchema(),
			"created_at":              dateTimeSchema(),
			"updated_at":              dateTimeSchema(),
			"finished_at":             dateTimeSchema(),
		}, []string{"job_id", "tenant_id", "source_id", "status", "mode", "updated_only", "requested_count", "accepted_count", "skipped_count", "created_at", "updated_at"}),
		"ListManualPullJobsResponse": inlineObj(map[string]any{
			"items":     arrSchema(refSchema("ManualPullJob")),
			"total":     intSchema(),
			"page":      intSchema(),
			"page_size": intSchema(),
		}, []string{"items", "total", "page", "page_size"}),
		"ParseTaskListItem": inlineObj(map[string]any{
			"task_id":                   intSchema(),
			"tenant_id":                 strSchema(),
			"source_id":                 strSchema(),
			"source_name":               strSchema(),
			"document_id":               intSchema(),
			"source_object_id":          strSchema(),
			"task_action":               strSchema(),
			"target_version_id":         strSchema(),
			"status":                    strSchema(),
			"retry_count":               intSchema(),
			"max_retry_count":           intSchema(),
			"origin_type":               strSchema(),
			"origin_platform":           strSchema(),
			"trigger_policy":            strSchema(),
			"next_run_at":               dateTimeSchema(),
			"started_at":                dateTimeSchema(),
			"finished_at":               dateTimeSchema(),
			"last_error":                strSchema(),
			"created_at":                dateTimeSchema(),
			"updated_at":                dateTimeSchema(),
			"agent_id":                  strSchema(),
			"agent_listen_addr":         strSchema(),
			"core_dataset_id":           strSchema(),
			"core_document_id":          strSchema(),
			"core_task_id":              strSchema(),
			"scan_orchestration_status": strSchema(),
			"submit_error_message":      strSchema(),
			"submit_at":                 dateTimeSchema(),
		}, []string{"task_id", "tenant_id", "source_id", "document_id", "source_object_id", "target_version_id", "status", "retry_count", "max_retry_count", "next_run_at", "created_at", "updated_at"}),
		"ListParseTasksResponse": inlineObj(map[string]any{
			"items":     arrSchema(refSchema("ParseTaskListItem")),
			"total":     intSchema(),
			"page":      intSchema(),
			"page_size": intSchema(),
		}, []string{"items", "total", "page", "page_size"}),
		"ParseTaskDetailResponse": inlineObj(map[string]any{
			"task_id":                   intSchema(),
			"tenant_id":                 strSchema(),
			"source_id":                 strSchema(),
			"source_name":               strSchema(),
			"document_id":               intSchema(),
			"source_object_id":          strSchema(),
			"task_action":               strSchema(),
			"target_version_id":         strSchema(),
			"status":                    strSchema(),
			"retry_count":               intSchema(),
			"max_retry_count":           intSchema(),
			"origin_type":               strSchema(),
			"origin_platform":           strSchema(),
			"trigger_policy":            strSchema(),
			"next_run_at":               dateTimeSchema(),
			"started_at":                dateTimeSchema(),
			"finished_at":               dateTimeSchema(),
			"last_error":                strSchema(),
			"created_at":                dateTimeSchema(),
			"updated_at":                dateTimeSchema(),
			"agent_id":                  strSchema(),
			"agent_listen_addr":         strSchema(),
			"core_dataset_id":           strSchema(),
			"core_document_id":          strSchema(),
			"core_task_id":              strSchema(),
			"scan_orchestration_status": strSchema(),
			"submit_error_message":      strSchema(),
			"submit_at":                 dateTimeSchema(),
			"desired_version_id":        strSchema(),
			"current_version_id":        strSchema(),
			"document_parse_status":     strSchema(),
		}, []string{"task_id", "tenant_id", "source_id", "document_id", "source_object_id", "target_version_id", "status", "retry_count", "max_retry_count", "next_run_at", "created_at", "updated_at"}),
		"ParseTaskStatsResponse": inlineObj(map[string]any{
			"counts": map[string]any{
				"type":                 "object",
				"additionalProperties": intSchema(),
			},
		}, []string{"counts"}),
		"PullCommandsResponse": inlineObj(map[string]any{
			"commands": arrSchema(refSchema("PulledCommand")),
		}, []string{"commands"}),
		"AckCommandRequest": inlineObj(map[string]any{
			"agent_id":    strSchema(),
			"command_id":  intSchema(),
			"success":     boolSchema(),
			"error":       strSchema(),
			"result_json": strSchema(),
		}, []string{"agent_id", "command_id", "success"}),
		"ReportSnapshotRequest": inlineObj(map[string]any{
			"agent_id":     strSchema(),
			"source_id":    strSchema(),
			"snapshot_ref": strSchema(),
			"file_count":   intSchema(),
			"taken_at":     dateTimeSchema(),
		}, []string{"agent_id", "source_id", "snapshot_ref", "taken_at"}),
		"FileEvent": inlineObj(map[string]any{
			"source_id":       strSchema(),
			"tenant_id":       strSchema(),
			"event_type":      strSchema(),
			"path":            strSchema(),
			"is_dir":          boolSchema(),
			"occurred_at":     dateTimeSchema(),
			"origin_type":     strSchema(),
			"origin_platform": strSchema(),
			"origin_ref":      strSchema(),
			"trigger_policy":  strSchema(),
		}, []string{"source_id", "event_type", "path"}),
		"ReportEventsRequest": inlineObj(map[string]any{
			"agent_id": strSchema(),
			"events":   arrSchema(refSchema("FileEvent")),
		}, []string{"agent_id", "events"}),
		"ScanRecord": inlineObj(map[string]any{
			"source_id":       strSchema(),
			"path":            strSchema(),
			"is_dir":          boolSchema(),
			"size":            intSchema(),
			"mod_time":        dateTimeSchema(),
			"checksum":        strSchema(),
			"origin_type":     strSchema(),
			"origin_platform": strSchema(),
			"origin_ref":      strSchema(),
			"trigger_policy":  strSchema(),
		}, []string{"source_id", "path"}),
		"ReportScanResultsRequest": inlineObj(map[string]any{
			"agent_id":  strSchema(),
			"source_id": strSchema(),
			"mode":      strSchema(),
			"records":   arrSchema(refSchema("ScanRecord")),
		}, []string{"agent_id", "source_id", "mode", "records"}),
		"AgentPathRequest": inlineObj(map[string]any{
			"agent_id": strSchema(),
			"path":     strSchema(),
		}, []string{"agent_id", "path"}),
		"AgentPathValidateResponse": inlineObj(map[string]any{
			"path":     strSchema(),
			"exists":   boolSchema(),
			"readable": boolSchema(),
			"is_dir":   boolSchema(),
			"allowed":  boolSchema(),
			"reason":   strSchema(),
		}, []string{"path", "exists", "readable", "is_dir", "allowed"}),
		"AgentPathTreeRequest": inlineObj(map[string]any{
			"agent_id":      strSchema(),
			"source_id":     strSchema(),
			"path":          strSchema(),
			"max_depth":     intSchema(),
			"include_files": boolSchema(),
			"changes_only":  boolSchema(),
		}, []string{"agent_id", "path"}),
		"TreeNode": inlineObj(map[string]any{
			"title":             strSchema(),
			"key":               strSchema(),
			"is_dir":            boolSchema(),
			"has_update":        boolSchema(),
			"update_type":       strSchema(),
			"update_desc":       strSchema(),
			"selectable":        boolSchema(),
			"external_file_id":  strSchema(),
			"parse_queue_state": strSchema(),
			"status_source":     strSchema(),
			"children":          arrSchema(refSchema("TreeNode")),
		}, []string{"title", "key", "is_dir"}),
		"AgentPathTreeResponse": inlineObj(map[string]any{
			"items":           arrSchema(refSchema("TreeNode")),
			"selection_token": strSchema(),
		}, []string{"items"}),
	}
}

func op(summary string, req map[string]any, responses map[string]any, params ...map[string]any) map[string]any {
	opMap := map[string]any{
		"summary":   summary,
		"responses": responses,
	}
	if req != nil {
		opMap["requestBody"] = req
	}
	if len(params) > 0 {
		items := make([]any, 0, len(params))
		for _, p := range params {
			items = append(items, p)
		}
		opMap["parameters"] = items
	}
	return opMap
}

func reqBody(schema map[string]any) map[string]any {
	return map[string]any{
		"required": true,
		"content": map[string]any{
			"application/json": map[string]any{
				"schema": schema,
			},
		},
	}
}

func resp(desc string, schema map[string]any) map[string]any {
	m := map[string]any{"description": desc}
	if schema != nil {
		m["content"] = map[string]any{
			"application/json": map[string]any{"schema": schema},
		}
	}
	return m
}

func acceptedResp() map[string]any {
	return resp("Accepted", inlineObj(map[string]any{
		"accepted": boolSchema(),
	}, []string{"accepted"}))
}

func errResp() map[string]any {
	return resp("Error", refSchema("ErrorResponse"))
}

func pathParam(name string) map[string]any {
	return map[string]any{
		"name":     name,
		"in":       "path",
		"required": true,
		"schema":   strSchema(),
	}
}

func queryParam(name string, required bool) map[string]any {
	return map[string]any{
		"name":     name,
		"in":       "query",
		"required": required,
		"schema":   strSchema(),
	}
}

func queryIntParam(name string, required bool) map[string]any {
	return map[string]any{
		"name":     name,
		"in":       "query",
		"required": required,
		"schema":   intSchema(),
	}
}

func refSchema(name string) map[string]any {
	return map[string]any{"$ref": "#/components/schemas/" + name}
}

func inlineObj(props map[string]any, required []string) map[string]any {
	m := map[string]any{
		"type":       "object",
		"properties": props,
	}
	if len(required) > 0 {
		items := make([]any, 0, len(required))
		for _, r := range required {
			items = append(items, r)
		}
		m["required"] = items
	}
	return m
}

func arrSchema(item map[string]any) map[string]any {
	return map[string]any{"type": "array", "items": item}
}

func strSchema() map[string]any {
	return map[string]any{"type": "string"}
}

func intSchema() map[string]any {
	return map[string]any{"type": "integer", "format": "int64"}
}

func boolSchema() map[string]any {
	return map[string]any{"type": "boolean"}
}

func dateTimeSchema() map[string]any {
	return map[string]any{"type": "string", "format": "date-time"}
}

func docsHTML(specURL string) string {
	specURLJSON, _ := json.Marshal(specURL)
	payload, _ := json.Marshal(map[string]any{
		"title": "Scan Control Plane API - Swagger UI",
	})
	return "<!DOCTYPE html>\n" +
		"<html lang=\"zh-CN\"><head><meta charset=\"UTF-8\">" +
		"<title>Scan Control Plane API - Swagger UI</title>" +
		"<link rel=\"stylesheet\" href=\"https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui.css\">" +
		"</head><body><div id=\"swagger-ui\"></div>" +
		"<script src=\"https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-bundle.js\"></script>" +
		"<script src=\"https://unpkg.com/swagger-ui-dist@5.11.0/swagger-ui-standalone-preset.js\"></script>" +
		"<script>window.__META__=" + string(payload) + ";" +
		"window.onload=function(){window.ui=SwaggerUIBundle({url:" + string(specURLJSON) + ",dom_id:'#swagger-ui',presets:[SwaggerUIBundle.presets.apis,SwaggerUIStandalonePreset],layout:'StandaloneLayout'});};</script>" +
		"</body></html>"
}
