package doc

import (
	"net/url"
	"testing"
)

func TestBuildParserChunksURLUsesOffsetPagination(t *testing.T) {
	t.Setenv("LAZYRAG_PARSING_SERVICE_URL", "http://parser:8000/")

	got := buildParserChunksURL("kb-1", "algo-1", "doc-1", "block", 3, 12)
	parsed, err := url.Parse(got)
	if err != nil {
		t.Fatalf("parse URL: %v", err)
	}
	if want := "http://parser:8000/doc/chunks"; parsed.Scheme+"://"+parsed.Host+parsed.Path != want {
		t.Fatalf("expected parser chunks URL %q, got %q", want, got)
	}
	q := parsed.Query()
	for key, want := range map[string]string{
		"kb_id":     "kb-1",
		"doc_id":    "doc-1",
		"group":     "block",
		"algo_id":   "algo-1",
		"offset":    "24",
		"page_size": "12",
	} {
		if got := q.Get(key); got != want {
			t.Fatalf("expected query %s=%q, got %q in %s", key, want, got, parsed.RawQuery)
		}
	}
}

func TestParseChunkSearchResponseAcceptsParserChunksShape(t *testing.T) {
	raw := map[string]any{
		"code": 200.0,
		"msg":  "success",
		"data": map[string]any{
			"items": []any{
				map[string]any{
					"uid":     "chunk-1",
					"doc_id":  "lazy-doc-1",
					"kb_id":   "dataset-1",
					"group":   "block",
					"number":  1.0,
					"content": "hello",
				},
			},
			"total":     25.0,
			"offset":    0.0,
			"page_size": 12.0,
		},
	}

	segments, total, next := parseChunkSearchResponse("dataset-1", "doc-1", raw, 1, 12)

	if total != 25 {
		t.Fatalf("expected total 25, got %d", total)
	}
	if next == "" {
		t.Fatalf("expected next page token")
	}
	if len(segments) != 1 {
		t.Fatalf("expected one segment, got %d", len(segments))
	}
	seg := segments[0]
	if seg.SegmentID != "chunk-1" || seg.DatasetID != "dataset-1" || seg.DocumentID != "lazy-doc-1" || seg.Content != "hello" {
		t.Fatalf("unexpected segment mapping: %+v", seg)
	}
}
