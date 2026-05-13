package doc

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"lazyrag/core/acl"
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

func TestParseDatasetScanManaged(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		ext  json.RawMessage
		want bool
	}{
		{name: "explicit flag", ext: json.RawMessage(`{"scan_managed":true}`), want: true},
		{name: "legacy scan tag", ext: json.RawMessage(`{"tags":["scan"]}`), want: true},
		{name: "not scan managed", ext: json.RawMessage(`{"tags":["manual"]}`), want: false},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := parseDatasetScanManaged(tc.ext); got != tc.want {
				t.Fatalf("expected %v, got %v", tc.want, got)
			}
		})
	}
}

func TestAllDatasetTagsIncludesACLVisibleDatasets(t *testing.T) {
	db := newDocumentTestDB(t)
	if err := db.AutoMigrate(&orm.DefaultDataset{}, &orm.ACLModel{}, &orm.UserGroupModel{}); err != nil {
		t.Fatalf("auto migrate acl tables: %v", err)
	}
	acl.InitStore(db)

	now := time.Date(2026, 5, 12, 10, 0, 0, 0, time.UTC)
	rows := []orm.Dataset{
		{
			ID:           "ds-owned",
			KbID:         "kb-owned",
			DisplayName:  "owned",
			Desc:         "owned",
			DatasetState: 0,
			ShareType:    0,
			Type:         1,
			Ext:          json.RawMessage(`{"tags":["owned-tag"]}`),
			BaseModel: orm.BaseModel{
				CreateUserID:   "u1",
				CreateUserName: "Alice",
				CreatedAt:      now,
				UpdatedAt:      now,
			},
		},
		{
			ID:           "ds-shared",
			KbID:         "kb-shared",
			DisplayName:  "shared",
			Desc:         "shared",
			DatasetState: 0,
			ShareType:    0,
			Type:         1,
			Ext:          json.RawMessage(`{"tags":["shared-tag"]}`),
			BaseModel: orm.BaseModel{
				CreateUserID:   "owner-2",
				CreateUserName: "Bob",
				CreatedAt:      now,
				UpdatedAt:      now,
			},
		},
		{
			ID:           "ds-hidden",
			KbID:         "kb-hidden",
			DisplayName:  "hidden",
			Desc:         "hidden",
			DatasetState: 0,
			ShareType:    0,
			Type:         1,
			Ext:          json.RawMessage(`{"tags":["hidden-tag"]}`),
			BaseModel: orm.BaseModel{
				CreateUserID:   "owner-3",
				CreateUserName: "Carol",
				CreatedAt:      now,
				UpdatedAt:      now,
			},
		},
	}
	if err := db.Create(&rows).Error; err != nil {
		t.Fatalf("create datasets: %v", err)
	}
	if id := acl.GetStore().AddACL(acl.ResourceTypeDB, "ds-shared", acl.GranteeUser, "u1", acl.PermissionDatasetRead, "owner-2", nil); id == 0 {
		t.Fatalf("expected acl row to be created")
	}

	req := httptest.NewRequest(http.MethodGet, "/api/core/dataset/tags", nil)
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	AllDatasetTags(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d: %s", rec.Code, rec.Body.String())
	}
	var resp AllDatasetTagsResponse
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	want := []string{"owned-tag", "shared-tag"}
	if got := resp.Tags; len(got) != len(want) || got[0] != want[0] || got[1] != want[1] {
		t.Fatalf("expected tags %v, got %v", want, got)
	}
}
