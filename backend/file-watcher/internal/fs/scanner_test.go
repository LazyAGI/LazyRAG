package fs

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/fsnotify/fsnotify"
	"go.uber.org/zap"

	internal "github.com/lazymind/file_watcher/internal"
	"github.com/lazymind/file_watcher/internal/config"
)

type scanReporterStub struct {
	records []internal.ScanRecord
}

func (r *scanReporterStub) ReportScanResults(_ context.Context, req internal.ReportScanResultsRequest) error {
	r.records = append(r.records, req.Records...)
	return nil
}

func TestScannerReportsPublicPathsWhenMapped(t *testing.T) {
	t.Parallel()

	runtimeRoot := t.TempDir()
	filePath := filepath.Join(runtimeRoot, "nested", "a.txt")
	if err := os.MkdirAll(filepath.Dir(filePath), 0o755); err != nil {
		t.Fatalf("mkdir nested: %v", err)
	}
	if err := os.WriteFile(filePath, []byte("hello"), 0o644); err != nil {
		t.Fatalf("write file: %v", err)
	}

	mapper := NewPathMapper("posix", []config.PathMapping{
		{PublicRoot: "/host/docs", RuntimeRoot: runtimeRoot},
	})
	reporter := &scanReporterStub{}
	scanner := NewScanner(
		"agent-1",
		config.ScanConfig{BatchSize: 100, LargeFileThresholdMB: 1},
		reporter,
		NewPathValidator([]string{runtimeRoot}),
		mapper,
		zap.NewNop(),
	)

	if err := scanner.FullScan(context.Background(), "src-1", runtimeRoot); err != nil {
		t.Fatalf("FullScan() error = %v", err)
	}

	found := false
	for _, record := range reporter.records {
		if record.Path == "/host/docs/nested/a.txt" {
			found = true
		}
		if record.Path == filePath {
			t.Fatalf("scanner leaked runtime path %q", record.Path)
		}
	}
	if !found {
		t.Fatalf("expected public file path in records, got %#v", reporter.records)
	}
}

func TestScannerSkipsTransientEditorFiles(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	regularPath := filepath.Join(root, "test2.txt")
	transientPaths := []string{
		filepath.Join(root, ".test2.txt.swp"),
		filepath.Join(root, ".test2.txt.swx"),
		filepath.Join(root, "~$draft.docx"),
		filepath.Join(root, "#draft.txt#"),
		filepath.Join(root, ".#draft.txt"),
	}
	if err := os.WriteFile(regularPath, []byte("hello"), 0o644); err != nil {
		t.Fatalf("write regular file: %v", err)
	}
	for _, path := range transientPaths {
		if err := os.WriteFile(path, []byte("tmp"), 0o644); err != nil {
			t.Fatalf("write transient file %s: %v", path, err)
		}
	}

	reporter := &scanReporterStub{}
	scanner := NewScanner(
		"agent-1",
		config.ScanConfig{BatchSize: 100, LargeFileThresholdMB: 1},
		reporter,
		NewPathValidator([]string{root}),
		NewPathMapper("", nil),
		zap.NewNop(),
	)

	if err := scanner.FullScan(context.Background(), "src-1", root); err != nil {
		t.Fatalf("FullScan() error = %v", err)
	}

	seen := make(map[string]struct{}, len(reporter.records))
	for _, record := range reporter.records {
		seen[record.Path] = struct{}{}
	}
	if _, ok := seen[regularPath]; !ok {
		t.Fatalf("expected regular file to be scanned, got %#v", reporter.records)
	}
	for _, path := range transientPaths {
		if _, ok := seen[path]; ok {
			t.Fatalf("transient file %s should not be scanned; records=%#v", path, reporter.records)
		}
	}
}

func TestScannerStatRejectsTransientEditorFile(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	transientPath := filepath.Join(root, ".draft.txt.swp")
	if err := os.WriteFile(transientPath, []byte("tmp"), 0o644); err != nil {
		t.Fatalf("write transient file: %v", err)
	}

	scanner := NewScanner(
		"agent-1",
		config.ScanConfig{BatchSize: 100, LargeFileThresholdMB: 1},
		&scanReporterStub{},
		NewPathValidator([]string{root}),
		NewPathMapper("", nil),
		zap.NewNop(),
	)

	if _, err := scanner.Stat(context.Background(), transientPath); err == nil {
		t.Fatal("expected Stat to reject transient editor file")
	}
}

func TestWatcherIgnoresTransientEditorFileEvents(t *testing.T) {
	t.Parallel()

	rw := &recursiveWatcher{log: zap.NewNop()}
	scheduled := 0
	rw.handleFsEvent(fsnotify.Event{
		Name: filepath.Join(t.TempDir(), ".test2.txt.swp"),
		Op:   fsnotify.Create,
	}, nil, func(string, internal.FileEventType, bool) {
		scheduled++
	})

	if scheduled != 0 {
		t.Fatalf("expected transient file event to be ignored, scheduled=%d", scheduled)
	}
}
