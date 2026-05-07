package merger

import (
	"context"
	"errors"
	"testing"
	"time"

	"go.uber.org/zap"

	"github.com/lazyrag/scan_control_plane/internal/config"
	"github.com/lazyrag/scan_control_plane/internal/model"
	"github.com/lazyrag/scan_control_plane/internal/store"
)

type fakeStore struct {
	buildErr error
	applyErr error
}

func (f *fakeStore) BuildMutationsFromEvents(_ context.Context, events []model.FileEvent) ([]store.DocumentMutation, error) {
	if f.buildErr != nil {
		return nil, f.buildErr
	}
	out := make([]store.DocumentMutation, 0, len(events))
	for _, ev := range events {
		out = append(out, store.DocumentMutation{
			SourceID:       ev.SourceID,
			SourceObjectID: ev.Path,
			EventType:      ev.EventType,
			OccurredAt:     ev.OccurredAt,
		})
	}
	return out, nil
}

func (f *fakeStore) BatchApplyDocumentMutations(_ context.Context, _ []store.DocumentMutation) error {
	return f.applyErr
}

func TestFlushRetainsEventsWhenPersistFails(t *testing.T) {
	t.Parallel()

	st := &fakeStore{applyErr: errors.New("db unavailable")}
	m := New(config.MergeConfig{
		FlushTick:      100 * time.Millisecond,
		FlushIdle:      100 * time.Millisecond,
		FlushMaxWait:   500 * time.Millisecond,
		FlushBatchSize: 16,
		MaxMemoryKeys:  1024,
	}, st, zap.NewNop())

	m.Ingest([]model.FileEvent{
		{
			SourceID:   "src_1",
			Path:       "/tmp/watch/a.txt",
			EventType:  "modified",
			OccurredAt: time.Now().UTC(),
		},
	})

	if err := m.FlushAll(context.Background()); err == nil {
		t.Fatalf("expected flush to fail when apply mutation returns error")
	}
	if len(m.events) != 1 {
		t.Fatalf("expected event to stay in memory after failed flush, got %d", len(m.events))
	}

	st.applyErr = nil
	if err := m.FlushAll(context.Background()); err != nil {
		t.Fatalf("flush after recovery failed: %v", err)
	}
	if len(m.events) != 0 {
		t.Fatalf("expected event map to be empty after successful flush, got %d", len(m.events))
	}
}

func TestNormalizeEventTypeIsCaseInsensitive(t *testing.T) {
	t.Parallel()

	if got := normalizeEventType("  Deleted "); got != "deleted" {
		t.Fatalf("expected deleted, got %q", got)
	}
	if got := normalizeEventType("CREATED"); got != "created" {
		t.Fatalf("expected created, got %q", got)
	}
	if got := normalizeEventType("unexpected"); got != "modified" {
		t.Fatalf("expected modified fallback, got %q", got)
	}
}
