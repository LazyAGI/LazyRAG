package app

import (
	"context"
	"errors"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"

	"github.com/lazyrag/scan_control_plane/internal/cloudsync"
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
	cloudSync *cloudsync.Runner
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
	st.SetDefaultCloudScheduleTZ(cfg.CloudSync.DefaultScheduleTZ)
	if cfg.Parser.Enabled {
		log.Warn("parser config is enabled but parser runtime is deprecated and ignored")
	}

	evMerger := merger.New(cfg.EventMerge, st, log)
	coreClient := coreclient.New(cfg.Core, log)
	cloudSyncRunner := cloudsync.New(cfg.CloudSync, st, log)
	var triggerFn func(sourceID, runID string) bool
	if cloudSyncRunner != nil && cfg.CloudSync.Enabled {
		triggerFn = cloudSyncRunner.Trigger
	}
	h := server.NewHandler(
		st,
		evMerger,
		coreClient,
		cfg.Core.DatasetID,
		cfg.AgentToken,
		triggerFn,
		cfg.CloudSync.AuthServiceBaseURL,
		cfg.CloudSync.AuthServiceInternalToken,
		cfg.CloudSync.HTTPTimeout,
		log,
	)
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
		cloudSync: cloudSyncRunner,
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

	runCtx, cancelWorkers := context.WithCancel(ctx)
	defer cancelWorkers()

	var workerWG sync.WaitGroup
	runComponent := func(fn func(context.Context)) {
		workerWG.Add(1)
		go func() {
			defer workerWG.Done()
			fn(runCtx)
		}()
	}
	runComponent(a.scheduler.Run)
	runComponent(a.merger.Run)
	runComponent(a.worker.Run)
	runComponent(a.metrics.Run)
	if a.cloudSync != nil {
		runComponent(a.cloudSync.Run)
	}

	serverErr := make(chan error, 1)
	go func() {
		if err := a.server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			serverErr <- err
		}
	}()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	defer signal.Stop(sigCh)

	var runErr error
	select {
	case <-ctx.Done():
		if !errors.Is(ctx.Err(), context.Canceled) {
			runErr = ctx.Err()
		}
	case sig := <-sigCh:
		a.log.Info("received signal, shutting down", zap.String("signal", sig.String()))
	case err := <-serverErr:
		a.log.Error("http server exited with error", zap.Error(err))
		runErr = err
	}

	cancelWorkers()

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := a.server.Shutdown(shutdownCtx); err != nil && !errors.Is(err, http.ErrServerClosed) {
		a.log.Warn("http server shutdown failed", zap.Error(err))
		if runErr == nil {
			runErr = err
		}
	}

	workerStopped := make(chan struct{})
	go func() {
		workerWG.Wait()
		close(workerStopped)
	}()
	select {
	case <-workerStopped:
	case <-shutdownCtx.Done():
		a.log.Warn("background workers did not stop before shutdown timeout")
	}

	if err := a.store.Close(); err != nil {
		a.log.Warn("close store failed", zap.Error(err))
		if runErr == nil {
			runErr = err
		}
	}
	a.log.Info("scan-control-plane stopped")
	return runErr
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
