package source

import (
	"context"
	"sync"
	"testing"
	"time"

	"go.uber.org/zap"

	internal "github.com/lazyrag/file_watcher/internal"
)

type reconcileScannerStub struct {
	mu        sync.Mutex
	snapshots []*internal.Snapshot
	fullScans int
}

func (s *reconcileScannerStub) FullScan(context.Context, string, string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.fullScans++
	return nil
}

func (s *reconcileScannerStub) ReconcileScan(context.Context, string, string) (*internal.Snapshot, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.snapshots) == 0 {
		return &internal.Snapshot{Files: map[string]internal.SnapshotEntry{}}, nil
	}
	head := s.snapshots[0]
	s.snapshots = s.snapshots[1:]
	return head, nil
}

func (s *reconcileScannerStub) Stat(context.Context, string) (internal.FileMeta, error) {
	return internal.FileMeta{}, nil
}

type reconcileReporterStub struct {
	mu     sync.Mutex
	events []internal.FileEvent
}

func (r *reconcileReporterStub) ReportEvents(_ context.Context, req internal.ReportEventsRequest) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.events = append(r.events, req.Events...)
	return nil
}

func (r *reconcileReporterStub) ReportSnapshot(context.Context, internal.ReportSnapshotRequest) error {
	return nil
}

func TestReconcilerPersistsAndLoadsSnapshot(t *testing.T) {
	t.Parallel()
	now := time.Now().UTC()
	oldSnap := &internal.Snapshot{
		SourceID: "src-1",
		TakenAt:  now,
		Files: map[string]internal.SnapshotEntry{
			"/tmp/a.txt": {Size: 10, ModTime: now, IsDir: false},
		},
	}
	newSnap := &internal.Snapshot{
		SourceID: "src-1",
		TakenAt:  now.Add(time.Minute),
		Files: map[string]internal.SnapshotEntry{
			"/tmp/a.txt": {Size: 20, ModTime: now.Add(time.Minute), IsDir: false},
		},
	}

	snapshotRoot := t.TempDir()
	scannerA := &reconcileScannerStub{snapshots: []*internal.Snapshot{oldSnap}}
	reporterA := &reconcileReporterStub{}
	r1 := NewReconciler("src-1", "tenant-1", "agent-1", "/tmp", snapshotRoot, time.Hour, scannerA, reporterA, zap.NewNop())
	r1.RunOnce(context.Background())

	if scannerA.fullScans == 0 {
		t.Fatalf("expected fallback full scan when no snapshot exists")
	}

	scannerB := &reconcileScannerStub{snapshots: []*internal.Snapshot{newSnap}}
	reporterB := &reconcileReporterStub{}
	r2 := NewReconciler("src-1", "tenant-1", "agent-1", "/tmp", snapshotRoot, time.Hour, scannerB, reporterB, zap.NewNop())
	r2.RunOnce(context.Background())

	reporterB.mu.Lock()
	defer reporterB.mu.Unlock()
	if len(reporterB.events) == 0 {
		t.Fatalf("expected reconcile events after loading persisted snapshot")
	}
}
