package store

import (
	"path/filepath"
	"strings"
	"time"

	"github.com/lazyrag/scan_control_plane/internal/model"
)

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

func InferDocumentUpdateType(desiredVersionID, currentVersionID, parseStatus string) string {
	return inferDocumentUpdateType(desiredVersionID, currentVersionID, parseStatus)
}

func NormalizeTaskAction(raw string) string {
	return normalizeTaskAction(raw)
}

func updateTypeDescription(updateType string) string {
	switch updateType {
	case "NEW":
		return "新文件待解析"
	case "MODIFIED":
		return "内容变化待重解析"
	case "DELETED":
		return "文件已删除待同步"
	case "UNCHANGED":
		return "无更新"
	default:
		return "状态未知"
	}
}

func fileTypeFromPath(path string) string {
	ext := strings.TrimPrefix(strings.ToLower(filepath.Ext(strings.TrimSpace(path))), ".")
	return ext
}

func toModelParseTaskListItem(row parseTaskListRow) model.ParseTaskListItem {
	return model.ParseTaskListItem{
		TaskID:                  row.TaskID,
		TenantID:                row.TenantID,
		SourceID:                row.SourceID,
		SourceName:              row.SourceName,
		DocumentID:              row.DocumentID,
		SourceObjectID:          row.SourceObjectID,
		TaskAction:              normalizeTaskAction(row.TaskAction),
		TargetVersionID:         row.TargetVersionID,
		Status:                  row.Status,
		RetryCount:              row.RetryCount,
		MaxRetryCount:           row.MaxRetryCount,
		OriginType:              row.OriginType,
		OriginPlatform:          row.OriginPlatform,
		TriggerPolicy:           row.TriggerPolicy,
		NextRunAt:               row.NextRunAt,
		StartedAt:               row.StartedAt,
		FinishedAt:              row.FinishedAt,
		LastError:               row.LastError,
		CreatedAt:               row.CreatedAt,
		UpdatedAt:               row.UpdatedAt,
		AgentID:                 row.AgentID,
		AgentListenAddr:         row.AgentListenAddr,
		CoreDatasetID:           row.CoreDatasetID,
		CoreDocumentID:          row.CoreDocumentID,
		CoreTaskID:              row.CoreTaskID,
		ScanOrchestrationStatus: row.ScanOrchestrationStatus,
		SubmitErrorMessage:      row.SubmitErrorMessage,
		SubmitAt:                row.SubmitAt,
	}
}

func toModelParseTaskDetail(row parseTaskDetailRow) model.ParseTaskDetailResponse {
	item := model.ParseTaskListItem{
		TaskID:                  row.TaskID,
		TenantID:                row.TenantID,
		SourceID:                row.SourceID,
		SourceName:              row.SourceName,
		DocumentID:              row.DocumentID,
		SourceObjectID:          row.SourceObjectID,
		TaskAction:              normalizeTaskAction(row.TaskAction),
		TargetVersionID:         row.TargetVersionID,
		Status:                  row.Status,
		RetryCount:              row.RetryCount,
		MaxRetryCount:           row.MaxRetryCount,
		OriginType:              row.OriginType,
		OriginPlatform:          row.OriginPlatform,
		TriggerPolicy:           row.TriggerPolicy,
		NextRunAt:               row.NextRunAt,
		StartedAt:               row.StartedAt,
		FinishedAt:              row.FinishedAt,
		LastError:               row.LastError,
		CreatedAt:               row.CreatedAt,
		UpdatedAt:               row.UpdatedAt,
		AgentID:                 row.AgentID,
		AgentListenAddr:         row.AgentListenAddr,
		CoreDatasetID:           row.CoreDatasetID,
		CoreDocumentID:          row.CoreDocumentID,
		CoreTaskID:              row.CoreTaskID,
		ScanOrchestrationStatus: row.ScanOrchestrationStatus,
		SubmitErrorMessage:      row.SubmitErrorMessage,
		SubmitAt:                row.SubmitAt,
	}
	return model.ParseTaskDetailResponse{
		ParseTaskListItem:   item,
		DesiredVersionID:    row.DesiredVersionID,
		CurrentVersionID:    row.CurrentVersionID,
		DocumentParseStatus: row.DocumentParseStatus,
	}
}

func toModelManualPullJob(e manualPullJobEntity) model.ManualPullJob {
	return model.ManualPullJob{
		JobID:                 e.JobID,
		TenantID:              e.TenantID,
		SourceID:              e.SourceID,
		Status:                e.Status,
		Mode:                  e.Mode,
		TriggerPolicy:         e.TriggerPolicy,
		SelectionToken:        e.SelectionToken,
		UpdatedOnly:           e.UpdatedOnly,
		RequestedCount:        e.RequestedCount,
		AcceptedCount:         e.AcceptedCount,
		SkippedCount:          e.SkippedCount,
		IgnoredUnchangedCount: e.IgnoredUnchangedCount,
		ErrorMessage:          e.ErrorMessage,
		CreatedAt:             e.CreatedAt,
		UpdatedAt:             e.UpdatedAt,
		FinishedAt:            e.FinishedAt,
	}
}

func toCloudSyncClaim(row cloudSyncClaimRow) CloudSyncClaim {
	return CloudSyncClaim{
		SourceID:              strings.TrimSpace(row.SourceID),
		TenantID:              strings.TrimSpace(row.TenantID),
		RootPath:              filepath.Clean(strings.TrimSpace(row.RootPath)),
		Provider:              strings.ToLower(strings.TrimSpace(row.Provider)),
		AuthConnectionID:      strings.TrimSpace(row.AuthConnectionID),
		TargetType:            strings.TrimSpace(row.TargetType),
		TargetRef:             strings.TrimSpace(row.TargetRef),
		ScheduleExpr:          strings.TrimSpace(row.ScheduleExpr),
		ScheduleTZ:            strings.TrimSpace(row.ScheduleTZ),
		ReconcileAfterSync:    row.ReconcileAfterSync,
		ReconcileDelayMinutes: row.ReconcileDelayMinutes,
		IncludePatterns:       decodeStringSliceJSON(row.IncludePatternsJSON),
		ExcludePatterns:       decodeStringSliceJSON(row.ExcludePatternsJSON),
		MaxObjectSizeBytes:    row.MaxObjectSizeBytes,
		ProviderOptions:       decodeMapJSON(row.ProviderOptionsJSON),
		ExistingRunID:         strings.TrimSpace(row.LastRunID),
	}
}

func toModelCloudSourceBinding(e cloudSourceBindingEntity, nextSyncAt *time.Time) model.CloudSourceBinding {
	return model.CloudSourceBinding{
		SourceID:              e.SourceID,
		TenantID:              e.TenantID,
		Provider:              e.Provider,
		Enabled:               e.Enabled,
		Status:                e.Status,
		AuthConnectionID:      e.AuthConnectionID,
		TargetType:            e.TargetType,
		TargetRef:             e.TargetRef,
		ScheduleExpr:          e.ScheduleExpr,
		ScheduleTZ:            e.ScheduleTZ,
		ReconcileAfterSync:    e.ReconcileAfterSync,
		ReconcileDelayMinutes: e.ReconcileDelayMinutes,
		IncludePatterns:       decodeStringSliceJSON(e.IncludePatternsJSON),
		ExcludePatterns:       decodeStringSliceJSON(e.ExcludePatternsJSON),
		MaxObjectSizeBytes:    e.MaxObjectSizeBytes,
		ProviderOptions:       decodeMapJSON(e.ProviderOptionsJSON),
		LastError:             e.LastError,
		NextSyncAt:            nextSyncAt,
		CreatedAt:             e.CreatedAt,
		UpdatedAt:             e.UpdatedAt,
	}
}

func toModelCloudSyncRun(e cloudSyncRunEntity) model.CloudSyncRun {
	return model.CloudSyncRun{
		RunID:        e.RunID,
		SourceID:     e.SourceID,
		TenantID:     e.TenantID,
		Provider:     e.Provider,
		TriggerType:  e.TriggerType,
		Status:       e.Status,
		StartedAt:    e.StartedAt,
		FinishedAt:   e.FinishedAt,
		RemoteTotal:  e.RemoteTotal,
		CreatedCount: e.CreatedCount,
		UpdatedCount: e.UpdatedCount,
		DeletedCount: e.DeletedCount,
		SkippedCount: e.SkippedCount,
		FailedCount:  e.FailedCount,
		ErrorCode:    e.ErrorCode,
		ErrorMessage: e.ErrorMessage,
	}
}

func toModelSource(e sourceEntity) model.Source {
	return model.Source{
		ID:                    e.ID,
		TenantID:              e.TenantID,
		Name:                  e.Name,
		SourceType:            e.SourceType,
		RootPath:              e.RootPath,
		Status:                model.SourceStatus(e.Status),
		WatchEnabled:          e.WatchEnabled,
		IdleWindowSeconds:     e.IdleWindowSeconds,
		ReconcileSeconds:      e.ReconcileSeconds,
		ReconcileSchedule:     e.ReconcileSchedule,
		AgentID:               e.AgentID,
		DatasetID:             strings.TrimSpace(e.DatasetID),
		DefaultOriginType:     e.DefaultOriginType,
		DefaultOriginPlatform: e.DefaultOriginPlatform,
		DefaultTriggerPolicy:  e.DefaultTriggerPolicy,
		CreatedAt:             e.CreatedAt,
		UpdatedAt:             e.UpdatedAt,
	}
}

func toModelAgent(e agentEntity) model.Agent {
	return model.Agent{
		AgentID:           e.AgentID,
		TenantID:          e.TenantID,
		Hostname:          e.Hostname,
		Version:           e.Version,
		Status:            e.Status,
		ListenAddr:        e.ListenAddr,
		LastHeartbeatAt:   e.LastHeartbeatAt,
		ActiveSourceCount: e.ActiveSourceCount,
		ActiveWatchCount:  e.ActiveWatchCount,
		ActiveTaskCount:   e.ActiveTaskCount,
		UpdatedAt:         e.UpdatedAt,
	}
}
