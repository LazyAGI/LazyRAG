package merger

import (
	"context"
	"strings"
	"sync"
	"time"

	"go.uber.org/zap"

	"github.com/lazyrag/scan_control_plane/internal/config"
	"github.com/lazyrag/scan_control_plane/internal/model"
	"github.com/lazyrag/scan_control_plane/internal/store"
)

type Store interface {
	BuildMutationsFromEvents(ctx context.Context, events []model.FileEvent) ([]store.DocumentMutation, error)
	BatchApplyDocumentMutations(ctx context.Context, mutations []store.DocumentMutation) error
}

type mergeKey struct {
	sourceID string
	path     string
}

type mergedEvent struct {
	event      model.FileEvent
	firstSeen  time.Time
	lastSeen   time.Time
	occurredAt time.Time
}

type EventMerger struct {
	cfg   config.MergeConfig
	store Store
	log   *zap.Logger

	mu     sync.Mutex
	events map[mergeKey]*mergedEvent
}

func New(cfg config.MergeConfig, st Store, log *zap.Logger) *EventMerger {
	return &EventMerger{
		cfg:    cfg,
		store:  st,
		log:    log,
		events: make(map[mergeKey]*mergedEvent),
	}
}

func (m *EventMerger) Run(ctx context.Context) {
	ticker := time.NewTicker(m.cfg.FlushTick)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			_ = m.FlushAll(context.Background())
			return
		case now := <-ticker.C:
			if err := m.flushDue(ctx, now); err != nil {
				m.log.Error("flush merged events failed", zap.Error(err))
			}
		}
	}
}

func (m *EventMerger) Ingest(events []model.FileEvent) {
	now := time.Now().UTC()
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, ev := range events {
		if ev.IsDir || ev.SourceID == "" || ev.Path == "" {
			continue
		}
		key := mergeKey{sourceID: ev.SourceID, path: ev.Path}
		occurred := ev.OccurredAt.UTC()
		if occurred.IsZero() {
			occurred = now
		}
		if exist, ok := m.events[key]; ok {
			exist.event = mergeEvent(exist.event, ev)
			exist.lastSeen = now
			exist.occurredAt = occurred
			exist.event.OccurredAt = occurred
			continue
		}
		cp := ev
		cp.OccurredAt = occurred
		m.events[key] = &mergedEvent{
			event:      cp,
			firstSeen:  now,
			lastSeen:   now,
			occurredAt: occurred,
		}
	}
}

func (m *EventMerger) FlushAll(ctx context.Context) error {
	return m.flush(func(_ *mergedEvent, _ time.Time) bool { return true }, ctx)
}

func (m *EventMerger) flushDue(ctx context.Context, now time.Time) error {
	return m.flush(func(ev *mergedEvent, t time.Time) bool {
		if len(m.events) >= m.cfg.FlushBatchSize {
			return true
		}
		if len(m.events) >= m.cfg.MaxMemoryKeys {
			return true
		}
		if t.Sub(ev.lastSeen) >= m.cfg.FlushIdle {
			return true
		}
		return t.Sub(ev.firstSeen) >= m.cfg.FlushMaxWait
	}, ctx)
}

func (m *EventMerger) flush(shouldFlush func(*mergedEvent, time.Time) bool, ctx context.Context) error {
	now := time.Now().UTC()
	events := make([]model.FileEvent, 0, m.cfg.FlushBatchSize)
	candidates := make([]flushCandidate, 0, m.cfg.FlushBatchSize)

	m.mu.Lock()
	for key, item := range m.events {
		if !shouldFlush(item, now) {
			continue
		}
		events = append(events, item.event)
		candidates = append(candidates, flushCandidate{
			key: key,
			snapshot: mergedEvent{
				event:      item.event,
				firstSeen:  item.firstSeen,
				lastSeen:   item.lastSeen,
				occurredAt: item.occurredAt,
			},
		})
		if len(events) >= m.cfg.FlushBatchSize {
			break
		}
	}
	m.mu.Unlock()

	if len(events) == 0 {
		return nil
	}
	mutations, err := m.store.BuildMutationsFromEvents(ctx, events)
	if err != nil {
		return err
	}
	if err := m.store.BatchApplyDocumentMutations(ctx, mutations); err != nil {
		return err
	}

	// Drop only events that are unchanged since snapshot selection.
	// New in-flight ingests on the same key must be kept for next flush.
	m.mu.Lock()
	for _, item := range candidates {
		current, ok := m.events[item.key]
		if !ok {
			continue
		}
		if mergedEventEqual(current, item.snapshot) {
			delete(m.events, item.key)
		}
	}
	m.mu.Unlock()

	m.log.Debug("flushed merged events", zap.Int("events", len(events)), zap.Int("mutations", len(mutations)))
	return nil
}

type flushCandidate struct {
	key      mergeKey
	snapshot mergedEvent
}

func mergeEvent(oldEv, newEv model.FileEvent) model.FileEvent {
	oldType := normalizeEventType(oldEv.EventType)
	newType := normalizeEventType(newEv.EventType)
	mergedType := newType
	if oldType == "created" && newType == "modified" {
		mergedType = "modified"
	}
	if oldType == "deleted" && newType != "deleted" {
		mergedType = newType
	}
	result := newEv
	result.EventType = mergedType
	return result
}

func normalizeEventType(v string) string {
	switch strings.ToLower(strings.TrimSpace(v)) {
	case "created":
		return "created"
	case "deleted":
		return "deleted"
	default:
		return "modified"
	}
}

func mergedEventEqual(current *mergedEvent, snapshot mergedEvent) bool {
	if current == nil {
		return false
	}
	return current.firstSeen.Equal(snapshot.firstSeen) &&
		current.lastSeen.Equal(snapshot.lastSeen) &&
		current.occurredAt.Equal(snapshot.occurredAt) &&
		fileEventEqual(current.event, snapshot.event)
}

func fileEventEqual(a, b model.FileEvent) bool {
	return strings.TrimSpace(a.SourceID) == strings.TrimSpace(b.SourceID) &&
		strings.TrimSpace(a.TenantID) == strings.TrimSpace(b.TenantID) &&
		strings.TrimSpace(a.EventType) == strings.TrimSpace(b.EventType) &&
		strings.TrimSpace(a.Path) == strings.TrimSpace(b.Path) &&
		a.IsDir == b.IsDir &&
		a.OccurredAt.Equal(b.OccurredAt) &&
		strings.TrimSpace(a.OriginType) == strings.TrimSpace(b.OriginType) &&
		strings.TrimSpace(a.OriginPlatform) == strings.TrimSpace(b.OriginPlatform) &&
		strings.TrimSpace(a.OriginRef) == strings.TrimSpace(b.OriginRef) &&
		strings.TrimSpace(a.TriggerPolicy) == strings.TrimSpace(b.TriggerPolicy)
}
