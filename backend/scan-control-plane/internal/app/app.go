package app

import (
	"context"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"

	"github.com/lazyrag/scan_control_plane/internal/config"
	"github.com/lazyrag/scan_control_plane/internal/coreclient"
	"github.com/lazyrag/scan_control_plane/internal/merger"
	"github.com/lazyrag/scan_control_plane/internal/metrics"
	"github.com/lazyrag/scan_control_plane/internal/scheduler"
	"github.com/lazyrag/scan_control_plane/internal/server"
	"github.com/lazyrag/scan_control_plane/internal/store"
	"github.com/lazyrag/scan_control_plane/internal/worker"
)

type App struct {
	cfg       *config.Config
	log       *zap.Logger
	store     *store.Store
	server    *http.Server
	scheduler *scheduler.Scheduler
	merger    *merger.EventMerger
	worker    *worker.Worker
	metrics   *metrics.Reporter
}

func New(cfg *config.Config) (*App, error) {
	log, err := buildLogger(cfg.LogLevel)
	if err != nil {
		return nil, err
	}

	st, err := store.New(cfg.DatabaseDriver, cfg.DatabaseDSN, cfg.DefaultIdleWindow, log)
	if err != nil {
		return nil, err
	}

	evMerger := merger.New(cfg.EventMerge, st, log)
	coreClient := coreclient.New(cfg.Core, log)
	h := server.NewHandler(st, evMerger, coreClient, cfg.Core.DatasetID, cfg.AgentToken, log)
	srv := server.NewHTTPServer(cfg.ListenAddr, h)
	sch := scheduler.New(st, cfg.SchedulerTick, log)
	wk := worker.New(cfg.Worker, st, coreClient, log)
	metricReporter := metrics.New(cfg.Metrics, st, log)

	return &App{
		cfg:       cfg,
		log:       log,
		store:     st,
		server:    srv,
		scheduler: sch,
		merger:    evMerger,
		worker:    wk,
		metrics:   metricReporter,
	}, nil
}

func (a *App) Run(ctx context.Context) error {
	a.log.Info("scan-control-plane starting",
		zap.String("listen", a.cfg.ListenAddr),
		zap.String("database_driver", a.cfg.DatabaseDriver),
	)
	if count, err := a.store.RequeueEnabledSourcesOnStartup(ctx); err != nil {
		a.log.Warn("requeue enabled sources on startup failed", zap.Error(err))
	} else if count > 0 {
		a.log.Info("requeued enabled sources on startup", zap.Int("count", count))
	}

	schCtx, cancelScheduler := context.WithCancel(ctx)
	defer cancelScheduler()
	go a.scheduler.Run(schCtx)
	go a.merger.Run(schCtx)
	go a.worker.Run(schCtx)
	go a.metrics.Run(schCtx)

	serverErr := make(chan error, 1)
	go func() {
		if err := a.server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			serverErr <- err
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	select {
	case <-ctx.Done():
	case sig := <-sigCh:
		a.log.Info("received signal, shutting down", zap.String("signal", sig.String()))
	case err := <-serverErr:
		a.log.Error("http server exited with error", zap.Error(err))
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = a.server.Shutdown(shutdownCtx)
	_ = a.store.Close()
	a.log.Info("scan-control-plane stopped")
	return nil
}

func buildLogger(level string) (*zap.Logger, error) {
	var zapLevel zapcore.Level
	if err := zapLevel.UnmarshalText([]byte(level)); err != nil {
		zapLevel = zapcore.InfoLevel
	}

	cfg := zap.Config{
		Level:            zap.NewAtomicLevelAt(zapLevel),
		Encoding:         "json",
		OutputPaths:      []string{"stdout"},
		ErrorOutputPaths: []string{"stderr"},
		EncoderConfig: zapcore.EncoderConfig{
			TimeKey:      "ts",
			LevelKey:     "level",
			CallerKey:    "caller",
			MessageKey:   "msg",
			EncodeTime:   zapcore.ISO8601TimeEncoder,
			EncodeLevel:  zapcore.LowercaseLevelEncoder,
			EncodeCaller: zapcore.ShortCallerEncoder,
		},
	}
	return cfg.Build()
}
