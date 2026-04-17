package source

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"go.uber.org/zap"

	internal "github.com/lazyrag/file_watcher/internal"
	"github.com/lazyrag/file_watcher/internal/config"
	"github.com/lazyrag/file_watcher/internal/fs"
)

// Manager Source 生命周期管理接口。
type Manager interface {
	StartSource(ctx context.Context, req internal.StartSourceRequest) error
	StopSource(ctx context.Context, sourceID string) error
	TriggerScan(ctx context.Context, sourceID string, mode internal.ScanMode) error
	ListRuntimes() []internal.SourceRuntime
	HandleCommand(ctx context.Context, cmd internal.Command) (any, error)
	Stats() (sourceCount, watchCount, taskCount int)
}

type manager struct {
	cfg       *config.Config
	scanner   fs.Scanner
	watcher   fs.RecursiveWatcher
	validator fs.PathValidator
	reporter  EventReporter
	staging   StagingService
	log       *zap.Logger

	mu       sync.RWMutex
	runtimes map[string]*runtimeEntry
}

// StagingService 文件落地接口（由 fs.StagingService 实现）。
type StagingService interface {
	StageFile(ctx context.Context, sourceID, documentID, versionID, srcPath string) (internal.StageResult, error)
}

// EventReporter 事件上报接口，由 control.Client 实现。
type EventReporter interface {
	ReportEvents(ctx context.Context, req internal.ReportEventsRequest) error
	ReportSnapshot(ctx context.Context, req internal.ReportSnapshotRequest) error
}

type runtimeEntry struct {
	runtime    internal.SourceRuntime
	cancel     context.CancelFunc
	reconciler *Reconciler
	scanMu     sync.Mutex // 同一 Source 同时只允许一个 full scan
}

func NewManager(
	cfg *config.Config,
	scanner fs.Scanner,
	watcher fs.RecursiveWatcher,
	validator fs.PathValidator,
	reporter EventReporter,
	staging StagingService,
	log *zap.Logger,
) Manager {
	return &manager{
		cfg:       cfg,
		scanner:   scanner,
		watcher:   watcher,
		validator: validator,
		reporter:  reporter,
		staging:   staging,
		log:       log,
		runtimes:  make(map[string]*runtimeEntry),
	}
}

func (m *manager) StartSource(ctx context.Context, req internal.StartSourceRequest) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, exists := m.runtimes[req.SourceID]; exists {
		m.log.Info("source already running, skip start", zap.String("source_id", req.SourceID))
		return nil
	}

	// 校验路径
	if err := m.validator.EnsureAllowed(req.RootPath); err != nil {
		return err
	}
	if err := m.ensureSourceDirs(req.SourceID); err != nil {
		return err
	}

	// Source 是长生命周期任务，不应绑定到单次 HTTP/命令请求上下文。
	sourceCtx, cancel := context.WithCancel(context.Background())
	tenantID := req.TenantID
	if tenantID == "" {
		tenantID = m.cfg.TenantID
	}
	reconcileInterval := m.cfg.ReconcileInterval
	if req.ReconcileSeconds > 0 {
		reconcileInterval = time.Duration(req.ReconcileSeconds) * time.Second
	}

	rt := internal.SourceRuntime{
		SourceID: req.SourceID,
		TenantID: tenantID,
		RootPath: req.RootPath,
		Status:   internal.SourceRuntimeStatusStarting,
	}

	reconciler := NewReconciler(
		req.SourceID,
		tenantID,
		m.cfg.AgentID,
		req.RootPath,
		m.cfg.Snapshot.HostRoot,
		reconcileInterval,
		m.scanner,
		m.reporter,
		m.log,
		req.ReconcileSchedule,
	)
	entry := &runtimeEntry{runtime: rt, cancel: cancel, reconciler: reconciler}
	m.runtimes[req.SourceID] = entry

	go func() {
		if !req.SkipInitialScan {
			// 首次全量扫描（持 scanMu，防止启动期间被 TriggerScan 并发）
			entry.scanMu.Lock()
			m.setStatus(req.SourceID, internal.SourceRuntimeStatusInitialScanning)
			fullScanStart := time.Now()
			if err := m.scanner.FullScan(sourceCtx, req.SourceID, req.RootPath); err != nil {
				entry.scanMu.Unlock()
				m.log.Error("full scan failed",
					zap.String("source_id", req.SourceID),
					zap.Duration("full_scan_cost", time.Since(fullScanStart)),
					zap.Error(err),
				)
				m.setStatus(req.SourceID, internal.SourceRuntimeStatusDegraded)
				return
			}
			entry.scanMu.Unlock()
			m.setLastScanAt(req.SourceID)
			m.log.Info("source lifecycle full scan done",
				zap.String("source_id", req.SourceID),
				zap.Duration("full_scan_cost", time.Since(fullScanStart)),
			)
		} else {
			m.log.Info("skip initial full scan",
				zap.String("source_id", req.SourceID),
				zap.String("root_path", req.RootPath),
			)
		}

		// 启动 watcher
		watcherStart := time.Now()
		if err := m.watcher.Start(sourceCtx, req.SourceID, tenantID, req.RootPath); err != nil {
			m.log.Error("watcher start failed",
				zap.String("source_id", req.SourceID),
				zap.Duration("watcher_start_cost", time.Since(watcherStart)),
				zap.Error(err),
			)
			m.setStatus(req.SourceID, internal.SourceRuntimeStatusError)
			return
		}
		m.log.Info("source lifecycle watcher start done",
			zap.String("source_id", req.SourceID),
			zap.Duration("watcher_start_cost", time.Since(watcherStart)),
		)
		m.setWatcherEnabled(req.SourceID, true)
		m.setStatus(req.SourceID, internal.SourceRuntimeStatusWatching)
		m.setStatus(req.SourceID, internal.SourceRuntimeStatusRunning)
		m.log.Info("source started", zap.String("source_id", req.SourceID))

		// 启动后先补偿一次，再进入周期 reconcile。
		reconciler.RunOnce(sourceCtx)
		// 启动 reconcile 循环
		reconciler.Run(sourceCtx)
	}()

	return nil
}

func (m *manager) StopSource(_ context.Context, sourceID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	entry, ok := m.runtimes[sourceID]
	if !ok {
		return fmt.Errorf("source %s not found", sourceID)
	}

	entry.cancel()
	_ = m.watcher.Stop(sourceID)
	entry.runtime.WatcherEnabled = false
	entry.runtime.Status = internal.SourceRuntimeStatusStopped
	delete(m.runtimes, sourceID)

	m.log.Info("source stopped", zap.String("source_id", sourceID))
	return nil
}

func (m *manager) TriggerScan(ctx context.Context, sourceID string, mode internal.ScanMode) error {
	m.mu.RLock()
	entry, ok := m.runtimes[sourceID]
	m.mu.RUnlock()

	if !ok {
		return fmt.Errorf("source %s not found", sourceID)
	}

	// TriggerScan 是异步任务，避免被调用方（尤其 HTTP 请求）提前取消。
	runCtx := context.WithoutCancel(ctx)
	m.log.Info("trigger scan accepted",
		zap.String("source_id", sourceID),
		zap.String("mode", string(mode)),
	)

	go func() {
		switch mode {
		case internal.ScanModeFull:
			// 同一 Source 同时只允许一个 full scan
			if !entry.scanMu.TryLock() {
				m.log.Warn("full scan already in progress, skipping", zap.String("source_id", sourceID))
				return
			}
			defer entry.scanMu.Unlock()
			fullScanStart := time.Now()
			if err := m.scanner.FullScan(runCtx, sourceID, entry.runtime.RootPath); err != nil {
				m.log.Error("triggered full scan failed",
					zap.String("source_id", sourceID),
					zap.Duration("full_scan_cost", time.Since(fullScanStart)),
					zap.Error(err),
				)
			} else {
				m.setLastScanAt(sourceID)
				m.log.Info("triggered full scan done",
					zap.String("source_id", sourceID),
					zap.Duration("full_scan_cost", time.Since(fullScanStart)),
				)
			}
		case internal.ScanModeReconcile:
			reconcileStart := time.Now()
			entry.reconciler.RunOnce(runCtx)
			m.log.Info("triggered reconcile done",
				zap.String("source_id", sourceID),
				zap.Duration("reconcile_cost", time.Since(reconcileStart)),
			)
		}
	}()
	return nil
}

func (m *manager) ListRuntimes() []internal.SourceRuntime {
	m.mu.RLock()
	defer m.mu.RUnlock()

	result := make([]internal.SourceRuntime, 0, len(m.runtimes))
	for _, e := range m.runtimes {
		rt := e.runtime
		health := m.watcher.Health(rt.SourceID)
		rt.WatcherEnabled = health.Enabled
		rt.WatcherHealthy = health.Healthy
		rt.WatcherLastError = health.LastError
		if !health.LastEventAt.IsZero() {
			rt.LastEventAt = health.LastEventAt
		}
		result = append(result, rt)
	}
	return result
}

// HandleCommand 处理控制面下发的指令（实现 control.CommandDispatcher 接口）。
func (m *manager) HandleCommand(ctx context.Context, cmd internal.Command) (any, error) {
	m.log.Info("received control-plane command",
		zap.Int64("command_id", cmd.ID),
		zap.String("type", string(cmd.Type)),
		zap.String("source_id", cmd.SourceID),
		zap.String("tenant_id", cmd.TenantID),
		zap.String("mode", string(cmd.Mode)),
		zap.String("document_id", cmd.DocumentID),
		zap.String("version_id", cmd.VersionID),
	)
	switch cmd.Type {
	case internal.CommandStartSource:
		if err := m.ensureSourceDirs(cmd.SourceID); err != nil {
			return nil, err
		}
		return nil, m.StartSource(ctx, internal.StartSourceRequest{
			SourceID:          cmd.SourceID,
			TenantID:          m.resolveTenantID(cmd.SourceID, cmd.TenantID),
			RootPath:          cmd.RootPath,
			SkipInitialScan:   cmd.SkipInitialScan,
			ReconcileSeconds:  cmd.ReconcileSeconds,
			ReconcileSchedule: cmd.ReconcileSchedule,
		})
	case internal.CommandStopSource:
		return nil, m.StopSource(ctx, cmd.SourceID)
	case internal.CommandScanSource:
		return nil, m.TriggerScan(ctx, cmd.SourceID, cmd.Mode)
	case internal.CommandReloadSource:
		_ = m.StopSource(ctx, cmd.SourceID)
		if err := m.ensureSourceDirs(cmd.SourceID); err != nil {
			return nil, err
		}
		return nil, m.StartSource(ctx, internal.StartSourceRequest{
			SourceID:          cmd.SourceID,
			TenantID:          m.resolveTenantID(cmd.SourceID, cmd.TenantID),
			RootPath:          cmd.RootPath,
			SkipInitialScan:   cmd.SkipInitialScan,
			ReconcileSeconds:  cmd.ReconcileSeconds,
			ReconcileSchedule: cmd.ReconcileSchedule,
		})
	case internal.CommandSnapshotSource:
		if err := m.ensureSourceDirs(cmd.SourceID); err != nil {
			return nil, err
		}
		r, err := m.captureSnapshot(ctx, cmd.SourceID, m.resolveTenantID(cmd.SourceID, cmd.TenantID), cmd.RootPath, cmd.ReconcileSeconds)
		if err != nil {
			return nil, err
		}
		return r, nil
	case internal.CommandStageFile:
		if err := m.ensureSourceDirs(cmd.SourceID); err != nil {
			return nil, err
		}
		result, err := m.staging.StageFile(ctx, cmd.SourceID, cmd.DocumentID, cmd.VersionID, cmd.SrcPath)
		if err != nil {
			m.log.Error("stage file failed",
				zap.String("source_id", cmd.SourceID),
				zap.String("src", cmd.SrcPath),
				zap.Error(err),
			)
			return nil, err
		}
		m.log.Info("stage file done",
			zap.String("host_path", result.HostPath),
			zap.String("container_path", result.ContainerPath),
			zap.Int64("size", result.Size),
		)
		return internal.StageFileResponse{
			HostPath:      result.HostPath,
			ContainerPath: result.ContainerPath,
			URI:           result.URI,
			Size:          result.Size,
		}, nil
	default:
		return nil, fmt.Errorf("unknown command type: %s", cmd.Type)
	}
}

func (m *manager) captureSnapshot(ctx context.Context, sourceID, tenantID, rootPath string, reconcileSeconds int64) (internal.ReportSnapshotRequest, error) {
	m.mu.RLock()
	entry, ok := m.runtimes[sourceID]
	m.mu.RUnlock()

	var reconciler *Reconciler
	if ok && entry.reconciler != nil {
		reconciler = entry.reconciler
	} else {
		interval := m.cfg.ReconcileInterval
		if reconcileSeconds > 0 {
			interval = time.Duration(reconcileSeconds) * time.Second
		}
		reconciler = NewReconciler(
			sourceID,
			tenantID,
			m.cfg.AgentID,
			rootPath,
			m.cfg.Snapshot.HostRoot,
			interval,
			m.scanner,
			m.reporter,
			m.log,
		)
	}
	snap, err := reconciler.CaptureSnapshot(ctx)
	if err != nil {
		return internal.ReportSnapshotRequest{}, err
	}
	snapshotRef := "local://snapshot/" + sourceID + "/snapshot.json"
	return internal.ReportSnapshotRequest{
		AgentID:     m.cfg.AgentID,
		SourceID:    sourceID,
		SnapshotRef: snapshotRef,
		FileCount:   int64(len(snap.Files)),
		TakenAt:     snap.TakenAt,
	}, nil
}

func (m *manager) resolveTenantID(sourceID, fallback string) string {
	if fallback != "" {
		return fallback
	}
	m.mu.RLock()
	defer m.mu.RUnlock()
	if entry, ok := m.runtimes[sourceID]; ok && entry.runtime.TenantID != "" {
		return entry.runtime.TenantID
	}
	return m.cfg.TenantID
}

func (m *manager) setStatus(sourceID string, status internal.SourceRuntimeStatus) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if e, ok := m.runtimes[sourceID]; ok {
		e.runtime.Status = status
	}
}

func (m *manager) setLastScanAt(sourceID string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if e, ok := m.runtimes[sourceID]; ok {
		e.runtime.LastScanAt = time.Now()
	}
}

func (m *manager) setWatcherEnabled(sourceID string, enabled bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if e, ok := m.runtimes[sourceID]; ok {
		e.runtime.WatcherEnabled = enabled
	}
}

func (m *manager) ensureSourceDirs(sourceID string) error {
	sourceID = strings.TrimSpace(sourceID)
	if sourceID == "" {
		return fmt.Errorf("source_id is required")
	}
	dirs := []string{}
	if m.cfg.Staging.Enabled && strings.TrimSpace(m.cfg.Staging.HostRoot) != "" {
		dirs = append(dirs, filepath.Join(m.cfg.Staging.HostRoot, "sources", sourceID, "files"))
	}
	if strings.TrimSpace(m.cfg.Snapshot.HostRoot) != "" {
		dirs = append(dirs, filepath.Join(m.cfg.Snapshot.HostRoot, "sources", sourceID))
	}
	if strings.TrimSpace(m.cfg.LogDir) != "" {
		dirs = append(dirs, filepath.Join(m.cfg.LogDir, "sources", sourceID))
	}
	for _, dir := range dirs {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return fmt.Errorf("create source scoped dir %s failed: %w", dir, err)
		}
	}
	return nil
}

// Stats 返回运行时统计，供心跳上报使用。
func (m *manager) Stats() (sourceCount, watchCount, taskCount int) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	sourceCount = len(m.runtimes)
	for sourceID := range m.runtimes {
		health := m.watcher.Health(sourceID)
		if health.Enabled && health.Healthy {
			watchCount++
		}
	}
	return
}
