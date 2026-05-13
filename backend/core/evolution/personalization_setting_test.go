package evolution

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"lazyrag/core/common/orm"
	"lazyrag/core/store"
)

type personalizationSettingAPITestResponse struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
	Data    struct {
		Enabled bool `json:"enabled"`
	} `json:"data"`
}

func TestGetPersonalizationSettingDefaultsTrue(t *testing.T) {
	db := newTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	req := httptest.NewRequest(http.MethodGet, "/api/core/personalization-setting", nil)
	req.Header.Set("X-User-Id", "u1")
	rec := httptest.NewRecorder()

	GetPersonalizationSetting(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", rec.Code, rec.Body.String())
	}

	var resp personalizationSettingAPITestResponse
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if !resp.Data.Enabled {
		t.Fatalf("expected personalization enabled by default")
	}
}

func TestSetPersonalizationSettingCreatesThenUpdatesRow(t *testing.T) {
	db := newTestDB(t)
	store.Init(db.DB, nil, nil)
	t.Cleanup(func() { store.Init(nil, nil, nil) })

	firstReq := httptest.NewRequest(http.MethodPut, "/api/core/personalization-setting", strings.NewReader(`{"enabled":false}`))
	firstReq.Header.Set("Content-Type", "application/json")
	firstReq.Header.Set("X-User-Id", "u1")
	firstReq.Header.Set("X-User-Name", "User 1")
	firstRec := httptest.NewRecorder()

	SetPersonalizationSetting(firstRec, firstReq)

	if firstRec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", firstRec.Code, firstRec.Body.String())
	}

	var row orm.UserPersonalizationSetting
	if err := db.Where("user_id = ?", "u1").Take(&row).Error; err != nil {
		t.Fatalf("query setting: %v", err)
	}
	if row.Enabled {
		t.Fatalf("expected stored setting to be false")
	}

	secondReq := httptest.NewRequest(http.MethodPut, "/api/core/personalization-setting", strings.NewReader(`{"enabled":true}`))
	secondReq.Header.Set("Content-Type", "application/json")
	secondReq.Header.Set("X-User-Id", "u1")
	secondReq.Header.Set("X-User-Name", "User 1")
	secondRec := httptest.NewRecorder()

	SetPersonalizationSetting(secondRec, secondReq)

	if secondRec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d body=%s", secondRec.Code, secondRec.Body.String())
	}

	var updated orm.UserPersonalizationSetting
	if err := db.Where("user_id = ?", "u1").Take(&updated).Error; err != nil {
		t.Fatalf("query updated setting: %v", err)
	}
	if !updated.Enabled {
		t.Fatalf("expected updated setting to be true")
	}
	if updated.ID != row.ID {
		t.Fatalf("expected update in place, got new id %d from old %d", updated.ID, row.ID)
	}
}
