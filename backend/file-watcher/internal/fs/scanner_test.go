package fs

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"go.uber.org/zap"

	internal "github.com/lazyrag/file_watcher/internal"
	"github.com/lazyrag/file_watcher/internal/config"
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
