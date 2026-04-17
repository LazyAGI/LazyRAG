package source

import (
	"context"
	"sync"
	"testing"
	"time"

	"go.uber.org/zap"

	internal "github.com/lazyrag/file_watcher/internal"
	"github.com/lazyrag/file_watcher/internal/config"
	"github.com/lazyrag/file_watcher/internal/fs"
)

type scannerStub struct{}

func (scannerStub) FullScan(context.Context, string, string) error {
	return nil
}

func (scannerStub) ReconcileScan(context.Context, string, string) (*internal.Snapshot, error) {
	return &internal.Snapshot{Files: map[string]internal.SnapshotEntry{}}, nil
}

func (scannerStub) Stat(context.Context, string) (internal.FileMeta, error) {
	return internal.FileMeta{}, nil
}

type startCall struct {
	sourceID string
	tenantID string
	root     string
}

type watcherStub struct {
	mu      sync.Mutex
	started map[string]startCall
	startCh chan startCall
}

func newWatcherStub() *watcherStub {
	return &watcherStub{
		started: make(map[string]startCall),
		startCh: make(chan startCall, 4),
	}
}

func (w *watcherStub) Start(_ context.Context, sourceID, tenantID, root string) error {
	call := startCall{sourceID: sourceID, tenantID: tenantID, root: root}
	w.mu.Lock()
	w.started[sourceID] = call
	w.mu.Unlock()
	w.startCh <- call
	return nil
}

func (w *watcherStub) Stop(sourceID string) error {
	w.mu.Lock()
	delete(w.started, sourceID)
	w.mu.Unlock()
	return nil
}

func (w *watcherStub) Health(sourceID string) fs.WatcherHealth {
	w.mu.Lock()
	defer w.mu.Unlock()
	_, ok := w.started[sourceID]
	return fs.WatcherHealth{Enabled: ok, Healthy: ok}
}

type validatorStub struct{}

func (validatorStub) Validate(path string) internal.ValidatePathResponse {
	return internal.ValidatePathResponse{Path: path, Allowed: true}
}

func (validatorStub) EnsureAllowed(string) error {
	return nil
}

type reporterStub struct{}

func (reporterStub) ReportEvents(context.Context, internal.ReportEventsRequest) error {
	return nil
}

func (reporterStub) ReportSnapshot(context.Context, internal.ReportSnapshotRequest) error {
	return nil
}

type stagingStub struct{}

func (stagingStub) StageFile(context.Context, string, string, string, string) (internal.StageResult, error) {
	return internal.StageResult{}, nil
}

func TestHandleCommandUsesCommandTenantID(t *testing.T) {
	t.Parallel()

	watcher := newWatcherStub()
	mgr := NewManager(
		&config.Config{AgentID: "agent-1", TenantID: "tenant-default", ReconcileInterval: time.Hour},
		scannerStub{},
		watcher,
		validatorStub{},
		reporterStub{},
		stagingStub{},
		zap.NewNop(),
	)

	rootPath := t.TempDir()
	_, err := mgr.HandleCommand(context.Background(), internal.Command{
		Type:     internal.CommandStartSource,
		SourceID: "src-1",
		TenantID: "tenant-cmd",
		RootPath: rootPath,
	})
	if err != nil {
		t.Fatalf("handle start command: %v", err)
	}

	select {
	case call := <-watcher.startCh:
		if call.tenantID != "tenant-cmd" {
			t.Fatalf("expected tenant tenant-cmd, got %q", call.tenantID)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for watcher start")
	}

	runtimes := mgr.ListRuntimes()
	if len(runtimes) != 1 {
		t.Fatalf("expected 1 runtime, got %d", len(runtimes))
	}
	if runtimes[0].TenantID != "tenant-cmd" {
		t.Fatalf("expected runtime tenant tenant-cmd, got %q", runtimes[0].TenantID)
	}

	if err := mgr.StopSource(context.Background(), "src-1"); err != nil {
		t.Fatalf("stop source: %v", err)
	}
}

func TestHandleCommandFallsBackToAgentTenantID(t *testing.T) {
	t.Parallel()

	watcher := newWatcherStub()
	mgr := NewManager(
		&config.Config{AgentID: "agent-1", TenantID: "tenant-default", ReconcileInterval: time.Hour},
		scannerStub{},
		watcher,
		validatorStub{},
		reporterStub{},
		stagingStub{},
		zap.NewNop(),
	)

	rootPath := t.TempDir()
	_, err := mgr.HandleCommand(context.Background(), internal.Command{
		Type:     internal.CommandStartSource,
		SourceID: "src-2",
		RootPath: rootPath,
	})
	if err != nil {
		t.Fatalf("handle start command: %v", err)
	}

	select {
	case call := <-watcher.startCh:
		if call.tenantID != "tenant-default" {
			t.Fatalf("expected tenant tenant-default, got %q", call.tenantID)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for watcher start")
	}

	if err := mgr.StopSource(context.Background(), "src-2"); err != nil {
		t.Fatalf("stop source: %v", err)
	}
}
