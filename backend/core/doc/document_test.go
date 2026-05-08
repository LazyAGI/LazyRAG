package doc

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestDetectDocumentContentTypeCSV(t *testing.T) {
	if got := detectDocumentContentType("cases.csv", "", ""); got != "text/csv; charset=utf-8" {
		t.Fatalf("expected csv content type, got %q", got)
	}
}

func TestStreamLocalFileInlineUsesActualFilenameForCSV(t *testing.T) {
	root := t.TempDir()
	t.Setenv("LAZYRAG_UPLOAD_ROOT", root)

	fullPath := filepath.Join(root, "agent-results", "thr-1", "datasets", "cases.csv")
	if err := os.MkdirAll(filepath.Dir(fullPath), 0o755); err != nil {
		t.Fatalf("create dir: %v", err)
	}
	if err := os.WriteFile(fullPath, []byte{0xEF, 0xBB, 0xBF, 'a', ',', 'b', '\n'}, 0o644); err != nil {
		t.Fatalf("write csv: %v", err)
	}

	recorder := httptest.NewRecorder()
	streamLocalFile(recorder, fullPath, "cases.csv", "", true)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d: %s", recorder.Code, recorder.Body.String())
	}
	if got := recorder.Header().Get("Content-Type"); got != "text/csv; charset=utf-8" {
		t.Fatalf("expected csv content type, got %q", got)
	}
	disposition := recorder.Header().Get("Content-Disposition")
	if !strings.Contains(disposition, "inline") || !strings.Contains(disposition, "cases.csv") {
		t.Fatalf("expected inline disposition with csv filename, got %q", disposition)
	}
	if strings.Contains(disposition, "preview.pdf") {
		t.Fatalf("disposition must not force preview.pdf: %q", disposition)
	}
}
