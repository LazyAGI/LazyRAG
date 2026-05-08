package scheduler

import (
	"context"
	"time"

	"go.uber.org/zap"

	"github.com/lazyrag/scan_control_plane/internal/store"
)

type Scheduler struct {
	store *store.Store
	tick  time.Duration
	log   *zap.Logger
}

func New(st *store.Store, tick time.Duration, log *zap.Logger) *Scheduler {
	return &Scheduler{store: st, tick: tick, log: log}
}

func (s *Scheduler) Run(ctx context.Context) {
	ticker := time.NewTicker(s.tick)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case now := <-ticker.C:
			count, err := s.store.ScheduleDueParses(ctx, now)
			if err != nil {
				s.log.Error("schedule due parses failed", zap.Error(err))
				continue
			}
			if count > 0 {
				s.log.Info("parse tasks scheduled", zap.Int("count", count))
			}
		}
	}
}
