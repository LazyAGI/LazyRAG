package store

import (
	"context"
	"strings"
	"time"

	"gorm.io/gorm"

	"lazymind/core/common/orm"
	"lazymind/core/common/readonlyorm"
)

// LazyLLMDocumentView is a joined view of core diff data and lazyllm base data.
type LazyLLMDocumentView struct {
	DocID         string
	Filename      string
	Path          string
	Meta          *string
	UploadStatus  string
	SourceType    string
	FileType      *string
	ContentHash   *string
	SizeBytes     *int
	BaseCreatedAt time.Time
	BaseUpdatedAt time.Time

	DiffExt            []byte
	DiffCreatedAt      time.Time
	DiffUpdatedAt      time.Time
	DiffDeletedAt      *time.Time
	DiffCreateUserID   string
	DiffCreateUserName string
}

// LazyLLMTaskView is a joined view of core diff data and lazyllm base data.
// AlgoID was removed from the lazyllm_doc_service_tasks table in the
// node-group refactor; the field no longer exists in schema-B.
type LazyLLMTaskView struct {
	TaskID        string
	TaskType      string
	DocID         string
	KbID          string
	Status        string
	Message       *string
	ErrorCode     *string
	ErrorMsg      *string
	BaseCreatedAt time.Time
	BaseUpdatedAt time.Time
	StartedAt     *time.Time
	FinishedAt    *time.Time

	DiffExt            []byte
	DiffCreatedAt      time.Time
	DiffUpdatedAt      time.Time
	DiffDeletedAt      *time.Time
	DiffCreateUserID   string
	DiffCreateUserName string
}

func dbOrTx(tx *gorm.DB) *gorm.DB {
	if tx != nil {
		return tx
	}
	return DB()
}

// GetLazyLLMDocumentView returns a merged view by Core document id or external lazyllm doc id.
func GetLazyLLMDocumentView(ctx context.Context, docID string, tx *gorm.DB) (*LazyLLMDocumentView, error) {
	var diff orm.Document
	if err := dbOrTx(tx).WithContext(ctx).Where("(id = ? OR lazyllm_doc_id = ?) AND deleted_at IS NULL", docID, docID).Take(&diff).Error; err != nil {
		return nil, err
	}
	extKey := strings.TrimSpace(diff.LazyllmDocID)
	if extKey == "" {
		extKey = docID
	}
	var base readonlyorm.LazyLLMDocRow
	if err := LazyLLMDB().WithContext(ctx).Table(base.TableName()).Where("doc_id = ?", extKey).Take(&base).Error; err != nil {
		return nil, err
	}
	return &LazyLLMDocumentView{
		DocID:              base.DocID,
		Filename:           base.Filename,
		Path:               base.Path,
		Meta:               base.Meta,
		UploadStatus:       base.UploadStatus,
		SourceType:         base.SourceType,
		FileType:           base.FileType,
		ContentHash:        base.ContentHash,
		SizeBytes:          base.SizeBytes,
		BaseCreatedAt:      base.CreatedAt,
		BaseUpdatedAt:      base.UpdatedAt,
		DiffExt:            diff.Ext,
		DiffCreateUserID:   diff.CreateUserID,
		DiffCreateUserName: diff.CreateUserName,
		DiffCreatedAt:      diff.CreatedAt,
		DiffUpdatedAt:      diff.UpdatedAt,
		DiffDeletedAt:      diff.DeletedAt,
	}, nil
}

// ListLazyLLMTaskViewsByKb returns merged task views filtered by kb_id.
// The algoID parameter has been removed after the node-group refactor;
// algo_id is no longer a column in lazyllm_doc_service_tasks.
func ListLazyLLMTaskViewsByKb(ctx context.Context, kbID string, limit int, tx *gorm.DB) ([]LazyLLMTaskView, error) {
	if limit <= 0 {
		limit = 20
	}
	var diffs []orm.Task
	if err := dbOrTx(tx).WithContext(ctx).
		Where("deleted_at IS NULL AND kb_id = ?", kbID).
		Find(&diffs).Error; err != nil {
		return nil, err
	}
	if len(diffs) == 0 {
		return []LazyLLMTaskView{}, nil
	}

	taskIDs := make([]string, 0, len(diffs))
	diffByTaskID := make(map[string]orm.Task, len(diffs))
	for _, diff := range diffs {
		tid := strings.TrimSpace(diff.LazyllmTaskID)
		if tid == "" {
			continue
		}
		taskIDs = append(taskIDs, tid)
		diffByTaskID[tid] = diff
	}
	if len(taskIDs) == 0 {
		return []LazyLLMTaskView{}, nil
	}

	var bases []readonlyorm.LazyLLMDocServiceTaskRow
	if err := LazyLLMDB().WithContext(ctx).
		Table((readonlyorm.LazyLLMDocServiceTaskRow{}).TableName()).
		Where("kb_id = ? AND task_id IN ?", kbID, taskIDs).
		Order("updated_at DESC").
		Limit(limit).
		Find(&bases).Error; err != nil {
		return nil, err
	}

	out := make([]LazyLLMTaskView, 0, len(bases))
	for _, base := range bases {
		diff, ok := diffByTaskID[base.TaskID]
		if !ok {
			continue
		}
		out = append(out, LazyLLMTaskView{
			TaskID:             base.TaskID,
			TaskType:           base.TaskType,
			DocID:              base.DocID,
			KbID:               base.KbID,
			Status:             base.Status,
			Message:            base.Message,
			ErrorCode:          base.ErrorCode,
			ErrorMsg:           base.ErrorMsg,
			BaseCreatedAt:      base.CreatedAt,
			BaseUpdatedAt:      base.UpdatedAt,
			StartedAt:          base.StartedAt,
			FinishedAt:         base.FinishedAt,
			DiffExt:            diff.Ext,
			DiffCreateUserID:   diff.CreateUserID,
			DiffCreateUserName: diff.CreateUserName,
			DiffCreatedAt:      diff.CreatedAt,
			DiffUpdatedAt:      diff.UpdatedAt,
			DiffDeletedAt:      diff.DeletedAt,
		})
	}
	return out, nil
}
