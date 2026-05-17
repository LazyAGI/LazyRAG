package feishu

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/lazyrag/scan_control_plane/internal/cloudsync/provider"
)

func TestListObjectsWikiSpaceIDListsNodesDirectly(t *testing.T) {
	var getNodeCalled bool
	p := newTestProvider(t, func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/wiki/v2/spaces/get_node":
			getNodeCalled = true
			writeFeishuData(w, `{"node":{"space_id":"7354","node_token":"unexpected"}}`)
		case "/wiki/v2/spaces/7354/nodes":
			if got := r.URL.Query().Get("parent_node_token"); got != "" {
				t.Fatalf("expected root listing, got parent_node_token=%q", got)
			}
			writeFeishuData(w, `{"items":[{"node_token":"node-1","title":"Doc","obj_type":"docx","obj_token":"docx-1","update_time":"1710000000"}]}`)
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	})

	objects, err := p.ListObjects(context.Background(), provider.ListRequest{
		AccessToken: "token",
		TargetType:  "wiki_space",
		TargetRef:   "7354",
	})
	if err != nil {
		t.Fatalf("ListObjects failed: %v", err)
	}
	if getNodeCalled {
		t.Fatalf("numeric space_id should not call get_node")
	}
	if len(objects) != 1 {
		t.Fatalf("expected 1 object, got %d", len(objects))
	}
	if objects[0].ExternalObjectID != "node-1" || objects[0].ExternalPath != "Doc" || objects[0].DownloadRef != "docx-1" {
		t.Fatalf("unexpected object: %#v", objects[0])
	}
}

func TestListObjectsWikiUsesObjEditTimeForVersion(t *testing.T) {
	p := newTestProvider(t, func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/wiki/v2/spaces/7354/nodes":
			writeFeishuData(w, `{"items":[{"node_token":"node-1","title":"Doc","obj_type":"docx","obj_token":"docx-1","obj_edit_time":"1710001234"}]}`)
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	})

	objects, err := p.ListObjects(context.Background(), provider.ListRequest{
		AccessToken: "token",
		TargetType:  "wiki_space",
		TargetRef:   "7354",
	})
	if err != nil {
		t.Fatalf("ListObjects failed: %v", err)
	}
	if len(objects) != 1 {
		t.Fatalf("expected 1 object, got %d", len(objects))
	}
	if objects[0].ExternalVersion != "1710001234" {
		t.Fatalf("expected obj_edit_time version, got %q", objects[0].ExternalVersion)
	}
	want := time.Unix(1710001234, 0).UTC()
	if objects[0].ExternalModifiedAt == nil || !objects[0].ExternalModifiedAt.UTC().Equal(want) {
		t.Fatalf("expected modified_at=%s, got %v", want, objects[0].ExternalModifiedAt)
	}
}

func TestListObjectsDriveUsesUpdateTimeForVersion(t *testing.T) {
	p := newTestProvider(t, func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/drive/v1/files":
			writeFeishuData(w, `{"files":[{"token":"file-1","name":"Doc.md","type":"file","update_time":"1710002222"}]}`)
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	})

	objects, err := p.ListObjects(context.Background(), provider.ListRequest{
		AccessToken: "token",
		TargetType:  "drive_folder",
	})
	if err != nil {
		t.Fatalf("ListObjects failed: %v", err)
	}
	if len(objects) != 1 {
		t.Fatalf("expected 1 object, got %d", len(objects))
	}
	if objects[0].ExternalVersion != "1710002222" {
		t.Fatalf("expected update_time version, got %q", objects[0].ExternalVersion)
	}
	want := time.Unix(1710002222, 0).UTC()
	if objects[0].ExternalModifiedAt == nil || !objects[0].ExternalModifiedAt.UTC().Equal(want) {
		t.Fatalf("expected modified_at=%s, got %v", want, objects[0].ExternalModifiedAt)
	}
}

func TestListObjectsWikiTokenResolvesSpaceIDAndWalksSubtree(t *testing.T) {
	const wikiToken = "UoPkwiVuPiCFtoklfBrcuKfpnHf"
	var getNodeCalled bool
	var listedResolvedSpace bool

	p := newTestProvider(t, func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/wiki/v2/spaces/get_node":
			getNodeCalled = true
			if got := r.URL.Query().Get("token"); got != wikiToken {
				t.Fatalf("expected token %q, got %q", wikiToken, got)
			}
			writeFeishuData(w, `{"node":{"space_id":"7354","node_token":"UoPkwiVuPiCFtoklfBrcuKfpnHf","title":"Root","obj_type":"docx","obj_token":"docx-root","has_child":true,"update_time":"1710000000"}}`)
		case "/wiki/v2/spaces/7354/nodes":
			listedResolvedSpace = true
			if got := r.URL.Query().Get("parent_node_token"); got != wikiToken {
				t.Fatalf("expected parent_node_token %q, got %q", wikiToken, got)
			}
			writeFeishuData(w, `{"items":[{"node_token":"child-1","title":"Child","obj_type":"docx","obj_token":"docx-child","update_time":"1710000001"}]}`)
		case "/wiki/v2/spaces/" + wikiToken + "/nodes":
			t.Fatalf("wiki token must not be used as space_id")
		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	})

	objects, err := p.ListObjects(context.Background(), provider.ListRequest{
		AccessToken: "token",
		TargetType:  "wiki_space",
		TargetRef:   "https://example.feishu.cn/wiki/" + wikiToken,
	})
	if err != nil {
		t.Fatalf("ListObjects failed: %v", err)
	}
	if !getNodeCalled || !listedResolvedSpace {
		t.Fatalf("expected get_node=%v and resolved space listing=%v", getNodeCalled, listedResolvedSpace)
	}
	if len(objects) != 2 {
		t.Fatalf("expected root and child objects, got %d", len(objects))
	}
	if objects[0].ExternalObjectID != wikiToken || objects[0].ExternalPath != "Root" || objects[0].DownloadRef != "docx-root" {
		t.Fatalf("unexpected root object: %#v", objects[0])
	}
	if objects[1].ExternalObjectID != "child-1" || objects[1].ExternalParentID != wikiToken || objects[1].ExternalPath != "Root/Child" {
		t.Fatalf("unexpected child object: %#v", objects[1])
	}
}

func TestNormalizeFeishuTargetRef(t *testing.T) {
	tests := map[string]string{
		"7354": "7354",
		"https://example.feishu.cn/wiki/UoPkwiVuPiCFtok":      "UoPkwiVuPiCFtok",
		"https://example.feishu.cn/wiki/space/73541234567890": "73541234567890",
		"https://example.feishu.cn/wiki/settings/space/7354":  "7354",
		"https://example.feishu.cn/wiki/foo?space_id=7354":    "7354",
		"<https://example.feishu.cn/wiki/UoPkwiVuPiCFtok>":    "UoPkwiVuPiCFtok",
	}

	for input, want := range tests {
		if got := normalizeFeishuTargetRef(input); got != want {
			t.Fatalf("normalizeFeishuTargetRef(%q)=%q, want %q", input, got, want)
		}
	}
}

func newTestProvider(t *testing.T, handler http.HandlerFunc) *Provider {
	t.Helper()
	p := New(0)
	p.baseURL = "https://feishu.test"
	p.client = &http.Client{
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			rec := httptest.NewRecorder()
			handler.ServeHTTP(rec, req)
			return rec.Result(), nil
		}),
	}
	return p
}

func writeFeishuData(w http.ResponseWriter, data string) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = fmt.Fprintf(w, `{"code":0,"msg":"ok","data":%s}`, data)
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return fn(req)
}
