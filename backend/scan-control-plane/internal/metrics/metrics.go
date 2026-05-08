package metrics

import (
	"context"
	"time"

	"go.uber.org/zap"

	"github.com/lazyrag/scan_control_plane/internal/config"
)

type Store interface {
	CountParseTasksByStatus(ctx context.Context) (map[string]int64, error)
	CountCommandsByStatus(ctx context.Context) (map[string]int64, error)
	CountAgentsByStatus(ctx context.Context) (map[string]int64, error)
	CountSourcesByStatus(ctx context.Context) (map[string]int64, error)
}

type Reporter struct {
	cfg   config.MetricsConfig
	store Store
	log   *zap.Logger
}

func New(cfg config.MetricsConfig, st Store, log *zap.Logger) *Reporter {
	return &Reporter{cfg: cfg, store: st, log: log}
}

func (r *Reporter) Run(ctx context.Context) {
	if !r.cfg.Enabled {
		return
	}
	ticker := time.NewTicker(r.cfg.Tick)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			r.emit(ctx)
		}
	}
}

func (r *Reporter) emit(ctx context.Context) {
	taskStats, err := r.store.CountParseTasksByStatus(ctx)
	if err != nil {
		r.log.Warn("count parse task metrics failed", zap.Error(err))
		return
	}
	cmdStats, err := r.store.CountCommandsByStatus(ctx)
	if err != nil {
		r.log.Warn("count command metrics failed", zap.Error(err))
		return
	}
	agentStats, err := r.store.CountAgentsByStatus(ctx)
	if err != nil {
		r.log.Warn("count agent metrics failed", zap.Error(err))
		return
	}
	sourceStats, err := r.store.CountSourcesByStatus(ctx)
	if err != nil {
		r.log.Warn("count source metrics failed", zap.Error(err))
		return
	}

	r.log.Info("scan control plane metrics snapshot",
		zap.Any("parse_tasks", taskStats),
		zap.Any("agent_commands", cmdStats),
		zap.Any("agents", agentStats),
		zap.Any("sources", sourceStats),
	)
}
