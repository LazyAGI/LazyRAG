package doc

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"lazyrag/core/common/orm"
)

func TestListDatasetsKeywordMatchesTags(t *testing.T) {
	db := newDocumentTestDB(t)
	if err := db.AutoMigrate(&orm.DefaultDataset{}); err != nil {
		t.Fatalf("auto migrate default datasets: %v", err)
	}

	now := time.Date(2026, 5, 11, 10, 0, 0, 0, time.UTC)
	rows := []orm.Dataset{
		{
			ID:           "ds-tag",
			KbID:         "kb-tag",
			DisplayName:  "Product docs",
			Desc:         "API references",
			CoverImage:   "",
			DatasetState: 0,
			ShareType:    0,
			Type:         1,
			Ext:          json.RawMessage(`{"tags":["333333","release"]}`),
			BaseModel: orm.BaseModel{
				CreateUserID:   "u1",
				CreateUserName: "Alice",
				CreatedAt:      now,
				UpdatedAt:      now,
			},
		},
		{
			ID:           "ds-other",
			KbID:         "kb-other",
			DisplayName:  "Engineering notes",
			Desc:         "Runbooks",
			CoverImage:   "",
			DatasetState: 0,
			ShareType:    0,
			Type:         1,
			Ext:          json.RawMessage(`{"tags":["release"]}`),
			BaseModel: orm.BaseModel{
				CreateUserID:   "u1",
				CreateUserName: "Alice",
				CreatedAt:      now.Add(-time.Hour),
				UpdatedAt:      now.Add(-time.Hour),
			},
		},
	}
	if err := db.Create(&rows).Error; err != nil {
		t.Fatalf("create datasets: %v", err)
	}

	req := httptest.NewRequest(http.MethodGet, "/api/core/datasets?page_token=&page_size=10&keyword=333333", nil)
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	ListDatasets(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp ListDatasetsResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if resp.TotalSize != 1 || len(resp.Datasets) != 1 {
		t.Fatalf("expected one dataset matched by tag, total=%d len=%d body=%s", resp.TotalSize, len(resp.Datasets), rec.Body.String())
	}
	if got := resp.Datasets[0].DatasetID; got != "ds-tag" {
		t.Fatalf("expected ds-tag, got %q", got)
	}
}
