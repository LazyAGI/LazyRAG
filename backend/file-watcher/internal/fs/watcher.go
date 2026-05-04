package fs

import (
	"context"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"
	"go.uber.org/zap"

	internal "github.com/lazyrag/file_watcher/internal"
	"github.com/lazyrag/file_watcher/internal/config"
)

// RecursiveWatcher 递归文件监听接口。
type RecursiveWatcher interface {
	Start(ctx context.Context, sourceID, tenantID, root string) error
	Stop(sourceID string) error
	Health(sourceID string) WatcherHealth
}

// EventReporter 事件上报接口（由 control.Client 实现）。
type EventReporter interface {
	ReportEvents(ctx context.Context, req internal.ReportEventsRequest) error
}

type WatcherHealth struct {
	Enabled     bool
	Healthy     bool
	LastEventAt time.Time
	LastError   string
}

type watcherEntry struct {
	cancel      context.CancelFunc
	watcher     *fsnotify.Watcher
	tenantID    string
	running     bool
	lastEventAt time.Time
	lastError   string
}

type recursiveWatcher struct {
	cfg      config.WatchConfig
	agentID  string
	reporter EventReporter
	mapper   PathMapper
	log      *zap.Logger

	mu      sync.Mutex
	entries map[string]*watcherEntry // sourceID -> entry
}

func NewRecursiveWatcher(agentID string, cfg config.WatchConfig, reporter EventReporter, mapper PathMapper, log *zap.Logger) RecursiveWatcher {
	if mapper == nil {
		mapper = NewPathMapper("", nil)
	}
	return &recursiveWatcher{
		cfg:      cfg,
		agentID:  agentID,
		reporter: reporter,
		mapper:   mapper,
		log:      log,
		entries:  make(map[string]*watcherEntry),
	}
}

func (rw *recursiveWatcher) Start(ctx context.Context, sourceID, tenantID, root string) error {
	rw.mu.Lock()
	defer rw.mu.Unlock()

	if _, exists := rw.entries[sourceID]; exists {
		return nil // 已在监听
	}

	// 先做一次试探性创建，确认 root 可访问后再启动 goroutine
	fw, err := fsnotify.NewWatcher()
	if err != nil {
		return err
	}
	if err := addRecursive(fw, root); err != nil {
		_ = fw.Close()
		return err
	}
	_ = fw.Close() // 由 runWithRestart 内部重新创建，保持统一管理

	watchCtx, cancel := context.WithCancel(ctx)
	entry := &watcherEntry{cancel: cancel, watcher: nil, tenantID: tenantID}
	rw.entries[sourceID] = entry

	go rw.runWithRestart(watchCtx, sourceID, tenantID, root)
	rw.log.Info("watcher started", zap.String("source_id", sourceID), zap.String("root", root))
	return nil
}

// runWithRestart 在 watcher loop 异常退出后自动重建，使用指数退避。
func (rw *recursiveWatcher) runWithRestart(ctx context.Context, sourceID, tenantID, root string) {
	const maxBackoff = 60 * time.Second
	backoff := time.Second

	for {
		if ctx.Err() != nil {
			return
		}

		fw, err := fsnotify.NewWatcher()
		if err != nil {
			rw.markUnhealthy(sourceID, err.Error())
			rw.log.Error("watcher rebuild failed", zap.String("source_id", sourceID), zap.Error(err))
		} else {
			if err := addRecursive(fw, root); err != nil {
				rw.markUnhealthy(sourceID, err.Error())
				rw.log.Error("watcher addRecursive failed", zap.String("source_id", sourceID), zap.Error(err))
				_ = fw.Close()
			} else {
				// 更新 entry 中的 watcher 引用
				rw.mu.Lock()
				if e, ok := rw.entries[sourceID]; ok {
					if e.watcher != nil && e.watcher != fw {
						_ = e.watcher.Close()
					}
					e.watcher = fw
					e.running = true
					e.lastError = ""
				}
				rw.mu.Unlock()

				rw.log.Info("watcher loop running", zap.String("source_id", sourceID))
				rw.loop(ctx, sourceID, tenantID, fw)

				// loop 正常退出（ctx 取消）则不重建
				if ctx.Err() != nil {
					_ = fw.Close()
					return
				}

				rw.log.Warn("watcher loop exited unexpectedly, rebuilding",
					zap.String("source_id", sourceID),
					zap.Duration("backoff", backoff),
				)
				rw.markUnhealthy(sourceID, "watcher loop exited unexpectedly")
				_ = fw.Close()
				backoff = min(backoff*2, maxBackoff)
			}
		}

		select {
		case <-ctx.Done():
			return
		case <-time.After(backoff):
		}
	}
}

func min(a, b time.Duration) time.Duration {
	if a < b {
		return a
	}
	return b
}

func (rw *recursiveWatcher) Stop(sourceID string) error {
	rw.mu.Lock()
	defer rw.mu.Unlock()

	entry, ok := rw.entries[sourceID]
	if !ok {
		return nil
	}
	entry.cancel()
	entry.running = false
	entry.lastError = ""
	if entry.watcher != nil {
		_ = entry.watcher.Close()
	}
	delete(rw.entries, sourceID)
	rw.log.Info("watcher stopped", zap.String("source_id", sourceID))
	return nil
}

func (rw *recursiveWatcher) Health(sourceID string) WatcherHealth {
	rw.mu.Lock()
	defer rw.mu.Unlock()

	entry, ok := rw.entries[sourceID]
	if !ok {
		return WatcherHealth{}
	}
	return WatcherHealth{
		Enabled:     true,
		Healthy:     entry.running && entry.watcher != nil,
		LastEventAt: entry.lastEventAt,
		LastError:   entry.lastError,
	}
}

// loop 是每个 Source 的 watcher 主循环，内置 debounce。
func (rw *recursiveWatcher) loop(ctx context.Context, sourceID, tenantID string, fw *fsnotify.Watcher) {
	defer func() {
		rw.mu.Lock()
		defer rw.mu.Unlock()
		if e, ok := rw.entries[sourceID]; ok {
			e.running = false
			if ctx.Err() != nil {
				e.lastError = ""
			}
		}
	}()

	// debounce: path -> (eventType, timer)
	type pending struct {
		eventType internal.FileEventType
		isDir     bool
		timer     *time.Timer
	}
	debounced := make(map[string]*pending)
	var mu sync.Mutex

	flush := func(path string, et internal.FileEventType, isDir bool) {
		publicPath := rw.mapper.ToPublic(path)
		ev := internal.FileEvent{
			SourceID:   sourceID,
			TenantID:   tenantID,
			EventType:  et,
			Path:       publicPath,
			IsDir:      isDir,
			OccurredAt: time.Now(),
		}
		if err := rw.reporter.ReportEvents(ctx, internal.ReportEventsRequest{
			AgentID: rw.agentID,
			Events:  []internal.FileEvent{ev},
		}); err != nil {
			rw.log.Warn("report events failed", zap.String("source_id", sourceID), zap.Error(err))
		} else {
			rw.log.Debug("reported debounced event",
				zap.String("source_id", sourceID),
				zap.String("path", publicPath),
				zap.String("type", string(et)),
				zap.Bool("is_dir", isDir),
			)
		}
	}

	schedule := func(path string, et internal.FileEventType, isDir bool) {
		mu.Lock()
		defer mu.Unlock()
		if p, ok := debounced[path]; ok {
			p.timer.Reset(rw.cfg.DebounceWindow)
			p.eventType = et
			rw.log.Debug("debounce event merged",
				zap.String("source_id", sourceID),
				zap.String("path", path),
				zap.String("type", string(et)),
			)
			return
		}
		p := &pending{eventType: et, isDir: isDir}
		p.timer = time.AfterFunc(rw.cfg.DebounceWindow, func() {
			mu.Lock()
			delete(debounced, path)
			mu.Unlock()
			flush(path, p.eventType, p.isDir)
		})
		debounced[path] = p
	}

	for {
		select {
		case <-ctx.Done():
			return
		case ev, ok := <-fw.Events:
			if !ok {
				rw.markUnhealthy(sourceID, "watcher events channel closed")
				return
			}
			rw.markEvent(sourceID)
			rw.handleFsEvent(ev, fw, schedule)
		case err, ok := <-fw.Errors:
			if !ok {
				rw.markUnhealthy(sourceID, "watcher error channel closed")
				return
			}
			rw.markUnhealthy(sourceID, err.Error())
			rw.log.Error("watcher error", zap.String("source_id", sourceID), zap.Error(err))
		}
	}
}

func (rw *recursiveWatcher) markEvent(sourceID string) {
	rw.mu.Lock()
	defer rw.mu.Unlock()
	if e, ok := rw.entries[sourceID]; ok {
		e.running = true
		e.lastEventAt = time.Now()
		e.lastError = ""
	}
}

func (rw *recursiveWatcher) markUnhealthy(sourceID, message string) {
	rw.mu.Lock()
	defer rw.mu.Unlock()
	if e, ok := rw.entries[sourceID]; ok {
		e.running = false
		if message != "" {
			e.lastError = message
		}
	}
}

func (rw *recursiveWatcher) handleFsEvent(
	ev fsnotify.Event,
	fw *fsnotify.Watcher,
	schedule func(string, internal.FileEventType, bool),
) {
	isDir := isDirectory(ev.Name)

	switch {
	case ev.Op&fsnotify.Create != 0:
		if isDir {
			_ = addRecursive(fw, ev.Name)
		}
		schedule(ev.Name, internal.FileCreated, isDir)

	case ev.Op&fsnotify.Write != 0:
		schedule(ev.Name, internal.FileModified, isDir)

	case ev.Op&fsnotify.Remove != 0:
		_ = fw.Remove(ev.Name)
		schedule(ev.Name, internal.FileDeleted, isDir)

	case ev.Op&fsnotify.Rename != 0:
		// P0: rename 按删除处理，新路径会触发 Create 事件
		_ = fw.Remove(ev.Name)
		schedule(ev.Name, internal.FileDeleted, isDir)

		// Chmod 忽略
	}
}

// addRecursive 递归注册目录树到 fsnotify.Watcher。
func addRecursive(fw *fsnotify.Watcher, root string) error {
	return filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return nil
		}
		if d.IsDir() {
			return fw.Add(path)
		}
		return nil
	})
}

func isDirectory(path string) bool {
	info, err := os.Stat(path)
	if err != nil {
		return false
	}
	return info.IsDir()
}
