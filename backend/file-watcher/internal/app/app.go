package app

import (
	"context"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"go.uber.org/zap"

	internal "github.com/lazyrag/file_watcher/internal"
	"github.com/lazyrag/file_watcher/internal/api"
	"github.com/lazyrag/file_watcher/internal/config"
	"github.com/lazyrag/file_watcher/internal/control"
	"github.com/lazyrag/file_watcher/internal/fs"
	"github.com/lazyrag/file_watcher/internal/source"
)

// App 是进程级生命周期中枢。
type App struct {
	cfg         *config.Config
	log         *zap.Logger
	server      *http.Server
	heartbeat   *control.HeartbeatReporter
	manager     source.Manager
	cpClient    control.ControlPlaneClient
	stagingSvc  fs.StagingService
	agentStatus internal.AgentStatus
	statusMu    sync.Mutex
}

// New 装配所有依赖，返回可运行的 App。
func New(cfg *config.Config, log *zap.Logger) *App {
	// 控制面客户端
	cpClient := control.NewHTTPClient(cfg.ControlPlaneBaseURL, cfg.AgentToken, log)

	// fs 层
	validator := fs.NewPathValidator(cfg.Security.AllowedRoots)
	scanner := fs.NewScanner(cfg.AgentID, cfg.Scan, cpClient, validator, log)
	watcher := fs.NewRecursiveWatcher(cfg.AgentID, cfg.Watch, cpClient, log)
	stagingSvc := fs.NewStagingService(cfg.Staging, log)

	// source manager（同时实现 Manager 和 CommandDispatcher）
	mgr := source.NewManager(cfg, scanner, watcher, validator, cpClient, stagingSvc, log)

	a := &App{
		cfg:         cfg,
		log:         log,
		manager:     mgr,
		cpClient:    cpClient,
		stagingSvc:  stagingSvc,
		agentStatus: internal.AgentStatusRegistering,
	}

	// 心跳 + 拉配置（statusFn 通过闭包读取 app 动态状态）
	heartbeat := control.NewHeartbeatReporter(
		cfg,
		cpClient,
		mgr,
		a.getStatus,
		mgr.Stats,
		log,
	)
	a.heartbeat = heartbeat

	// HTTP server
	handler := api.NewHandler(mgr, validator, scanner, stagingSvc, log)
	a.server = api.NewServer(cfg, handler, log)

	return a
}

// Run 按固定顺序启动各子系统，阻塞直到收到退出信号。
func (a *App) Run(ctx context.Context) error {
	hostname, _ := os.Hostname()
	advertiseAddr := a.cfg.AgentListenURL()
	if err := a.ensureBaseDirs(); err != nil {
		return err
	}
	a.log.Info("file_watcher starting",
		zap.String("agent_id", a.cfg.AgentID),
		zap.String("hostname", hostname),
		zap.String("listen", a.cfg.ListenAddr),
		zap.String("advertise", advertiseAddr),
		zap.String("base_root", a.cfg.BaseRoot),
		zap.String("staging_root", a.cfg.Staging.HostRoot),
		zap.String("snapshot_root", a.cfg.Snapshot.HostRoot),
		zap.String("log_dir", a.cfg.LogDir),
	)

	// 注册 Agent 到控制面
	if err := a.cpClient.RegisterAgent(ctx, internal.RegisterAgentRequest{
		AgentID:    a.cfg.AgentID,
		TenantID:   a.cfg.TenantID,
		Hostname:   hostname,
		Version:    "0.1.0",
		ListenAddr: advertiseAddr,
	}); err != nil {
		a.log.Warn("register agent failed, will retry via heartbeat", zap.Error(err))
	} else {
		a.setStatus(internal.AgentStatusOnline)
	}

	// 启动心跳协程
	heartbeatCtx, cancelHeartbeat := context.WithCancel(ctx)
	defer cancelHeartbeat()
	go a.heartbeat.Run(heartbeatCtx)

	// 启动 HTTP server
	serverErr := make(chan error, 1)
	go func() {
		a.log.Info("http server listening", zap.String("addr", a.cfg.ListenAddr))
		if err := a.server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			serverErr <- err
		}
	}()

	// 启动健康自检
	go a.healthLoop(ctx)

	// 等待退出信号
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-quit:
		a.log.Info("received signal, shutting down", zap.String("signal", sig.String()))
	case err := <-serverErr:
		a.log.Error("http server error", zap.Error(err))
	case <-ctx.Done():
	}

	return a.shutdown()
}

func (a *App) shutdown() error {
	a.log.Info("shutting down http server")
	if err := api.GracefulShutdown(a.server, 10*time.Second); err != nil {
		a.log.Warn("http server shutdown error", zap.Error(err))
	}
	a.log.Info("file_watcher stopped")
	return nil
}

// healthLoop 每 30s 执行一次健康自检，检查 6 项并更新 AgentStatus。
func (a *App) healthLoop(ctx context.Context) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			a.runHealthCheck(ctx)
		}
	}
}

func (a *App) runHealthCheck(ctx context.Context) {
	var failures []string

	// 1. 检查 staging 根目录是否可写
	if a.cfg.Staging.Enabled {
		if err := checkDirWritable(a.cfg.Staging.HostRoot); err != nil {
			failures = append(failures, "staging_not_writable: "+err.Error())
		}
	}
	if strings.TrimSpace(a.cfg.Snapshot.HostRoot) != "" {
		if err := checkDirWritable(a.cfg.Snapshot.HostRoot); err != nil {
			failures = append(failures, "snapshot_not_writable: "+err.Error())
		}
	}
	if strings.TrimSpace(a.cfg.LogDir) != "" {
		if err := checkDirWritable(a.cfg.LogDir); err != nil {
			failures = append(failures, "log_dir_not_writable: "+err.Error())
		}
	}

	// 2. 检查控制面是否可达（复用心跳接口做探活）
	probeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := a.cpClient.ReportHeartbeat(probeCtx, internal.HeartbeatPayload{
		AgentID:         a.cfg.AgentID,
		TenantID:        a.cfg.TenantID,
		Status:          a.getStatus(),
		LastHeartbeatAt: time.Now(),
	}); err != nil {
		failures = append(failures, "control_plane_unreachable: "+err.Error())
	}

	// 3. 检查各 Source 的 watcher 是否存活
	runtimes := a.manager.ListRuntimes()
	for _, rt := range runtimes {
		if rt.Status == internal.SourceRuntimeStatusRunning && !rt.WatcherHealthy {
			failure := "watcher_dead: source_id=" + rt.SourceID
			if rt.WatcherLastError != "" {
				failure += ", error=" + rt.WatcherLastError
			}
			failures = append(failures, failure)
		}
	}

	// 4. 检查是否有 Source 长时间处于 ERROR 状态
	for _, rt := range runtimes {
		if rt.Status == internal.SourceRuntimeStatusError {
			failures = append(failures, "source_error: source_id="+rt.SourceID)
		}
	}

	if len(failures) > 0 {
		a.setStatus(internal.AgentStatusDegraded)
		a.log.Warn("health check failed",
			zap.Int("active_sources", len(runtimes)),
			zap.Strings("failures", failures),
		)
	} else {
		a.setStatus(internal.AgentStatusOnline)
		a.log.Info("health check ok", zap.Int("active_sources", len(runtimes)))
	}
}

func (a *App) getStatus() internal.AgentStatus {
	a.statusMu.Lock()
	defer a.statusMu.Unlock()
	return a.agentStatus
}

func (a *App) setStatus(s internal.AgentStatus) {
	a.statusMu.Lock()
	defer a.statusMu.Unlock()
	a.agentStatus = s
}

// checkDirWritable 检查目录是否存在且可写。
func checkDirWritable(dir string) error {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	probe := dir + "/.health_probe"
	f, err := os.Create(probe)
	if err != nil {
		return err
	}
	_ = f.Close()
	return os.Remove(probe)
}

func (a *App) ensureBaseDirs() error {
	if a.cfg.Staging.Enabled && strings.TrimSpace(a.cfg.Staging.HostRoot) != "" {
		if err := os.MkdirAll(a.cfg.Staging.HostRoot, 0o755); err != nil {
			return err
		}
	}
	if strings.TrimSpace(a.cfg.Snapshot.HostRoot) != "" {
		if err := os.MkdirAll(a.cfg.Snapshot.HostRoot, 0o755); err != nil {
			return err
		}
	}
	if strings.TrimSpace(a.cfg.LogDir) != "" {
		if err := os.MkdirAll(a.cfg.LogDir, 0o755); err != nil {
			return err
		}
	}
	return nil
}
