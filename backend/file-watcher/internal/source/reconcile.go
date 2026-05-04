package source

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"go.uber.org/zap"

	internal "github.com/lazyrag/file_watcher/internal"
	"github.com/lazyrag/file_watcher/internal/fs"
)

// Reconciler 负责周期性快照 diff，补偿 watcher 漏事件。
type Reconciler struct {
	sourceID     string
	tenantID     string
	agentID      string
	rootPath     string
	snapshotRoot string
	interval     time.Duration
	schedule     *reconcileSchedule
	scanner      fs.Scanner
	reporter     EventReporter
	log          *zap.Logger

	lastSnapshot *internal.Snapshot
	mu           sync.Mutex // 保护 lastSnapshot 和防止并发执行
	running      bool       // 是否正在执行，防止并发 RunOnce
}

type persistedSnapshot struct {
	SourceID string                           `json:"source_id"`
	TakenAt  time.Time                        `json:"taken_at"`
	Files    map[string]persistedSnapshotItem `json:"files"`
}

type persistedSnapshotItem struct {
	Size            int64  `json:"size"`
	ModTimeUnix     int64  `json:"mod_time_unix,omitempty"`
	ModTimeUnixNano int64  `json:"mod_time_unix_nano,omitempty"`
	IsDir           bool   `json:"is_dir"`
	Checksum        string `json:"checksum,omitempty"`
}

type reconcileSchedule struct {
	everyDays int
	hour      int
	minute    int
}

func NewReconciler(sourceID, tenantID, agentID, rootPath, snapshotRoot string, interval time.Duration, scanner fs.Scanner, reporter EventReporter, log *zap.Logger, scheduleExpr ...string) *Reconciler {
	r := &Reconciler{
		sourceID:     sourceID,
		tenantID:     tenantID,
		agentID:      agentID,
		rootPath:     rootPath,
		snapshotRoot: snapshotRoot,
		interval:     interval,
		scanner:      scanner,
		reporter:     reporter,
		log:          log,
	}
	if len(scheduleExpr) > 0 {
		if sc, err := parseReconcileScheduleExpr(scheduleExpr[0]); err != nil {
			if log != nil {
				log.Warn("invalid reconcile schedule, fallback to interval", zap.String("schedule", scheduleExpr[0]), zap.Error(err))
			}
		} else {
			r.schedule = sc
		}
	}
	return r
}

// Run 启动周期性 reconcile，阻塞直到 ctx 取消。
func (r *Reconciler) Run(ctx context.Context) {
	if r.schedule != nil {
		r.runBySchedule(ctx)
		return
	}
	if r.interval <= 0 {
		r.interval = 10 * time.Minute
	}
	ticker := time.NewTicker(r.interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			r.RunOnce(ctx)
		}
	}
}

func (r *Reconciler) runBySchedule(ctx context.Context) {
	for {
		next := r.schedule.next(time.Now())
		wait := time.Until(next)
		if wait < 0 {
			wait = 0
		}
		timer := time.NewTimer(wait)
		select {
		case <-ctx.Done():
			timer.Stop()
			return
		case <-timer.C:
			r.RunOnce(ctx)
		}
	}
}

func parseReconcileScheduleExpr(expr string) (*reconcileSchedule, error) {
	raw := strings.TrimSpace(expr)
	if raw == "" {
		return nil, fmt.Errorf("empty schedule")
	}
	lower := strings.ToLower(raw)
	if strings.HasPrefix(lower, "daily@") {
		h, m, err := parseHourMinuteToken(raw[len("daily@"):])
		if err != nil {
			return nil, err
		}
		return &reconcileSchedule{everyDays: 1, hour: h, minute: m}, nil
	}
	if strings.HasPrefix(lower, "every") && strings.Contains(lower, "d@") {
		pos := strings.Index(lower, "d@")
		days, err := strconv.Atoi(strings.TrimSpace(raw[len("every"):pos]))
		if err != nil || days <= 0 {
			return nil, fmt.Errorf("invalid everyNd day token")
		}
		h, m, err := parseHourMinuteToken(raw[pos+2:])
		if err != nil {
			return nil, err
		}
		return &reconcileSchedule{everyDays: days, hour: h, minute: m}, nil
	}
	if strings.HasPrefix(raw, "每天") {
		h, m, err := parseHourMinuteToken(strings.TrimSpace(strings.TrimPrefix(raw, "每天")))
		if err != nil {
			return nil, err
		}
		return &reconcileSchedule{everyDays: 1, hour: h, minute: m}, nil
	}
	if strings.HasPrefix(raw, "每") && strings.Contains(raw, "天") {
		pos := strings.Index(raw, "天")
		days, err := parseDayToken(strings.TrimSpace(raw[len("每"):pos]))
		if err != nil {
			return nil, err
		}
		h, m, err := parseHourMinuteToken(strings.TrimSpace(raw[pos+len("天"):]))
		if err != nil {
			return nil, err
		}
		return &reconcileSchedule{everyDays: days, hour: h, minute: m}, nil
	}
	return nil, fmt.Errorf("invalid schedule format")
}

func (s *reconcileSchedule) next(after time.Time) time.Time {
	loc := after.Location()
	if loc == nil {
		loc = time.Local
	}
	startOfDay := time.Date(after.Year(), after.Month(), after.Day(), 0, 0, 0, 0, loc)
	if s.everyDays <= 1 {
		candidate := time.Date(after.Year(), after.Month(), after.Day(), s.hour, s.minute, 0, 0, loc)
		if !candidate.After(after) {
			candidate = candidate.AddDate(0, 0, 1)
		}
		return candidate
	}
	anchor := time.Date(1970, 1, 1, 0, 0, 0, 0, loc)
	daysSinceAnchor := int(startOfDay.Sub(anchor).Hours() / 24)
	remainder := daysSinceAnchor % s.everyDays
	if remainder < 0 {
		remainder += s.everyDays
	}
	offsetDays := 0
	if remainder != 0 {
		offsetDays = s.everyDays - remainder
	}
	candidateDay := startOfDay.AddDate(0, 0, offsetDays)
	candidate := time.Date(candidateDay.Year(), candidateDay.Month(), candidateDay.Day(), s.hour, s.minute, 0, 0, loc)
	if !candidate.After(after) {
		candidate = candidate.AddDate(0, 0, s.everyDays)
	}
	return candidate
}

func parseHourMinuteToken(token string) (int, int, error) {
	value := strings.TrimSpace(token)
	if value == "" {
		return 0, 0, fmt.Errorf("empty time token")
	}
	value = strings.ReplaceAll(value, "：", ":")
	if strings.Contains(value, ":") {
		parts := strings.Split(value, ":")
		if len(parts) != 2 {
			return 0, 0, fmt.Errorf("invalid hh:mm")
		}
		h, errH := strconv.Atoi(strings.TrimSpace(parts[0]))
		m, errM := strconv.Atoi(strings.TrimSpace(parts[1]))
		if errH != nil || errM != nil {
			return 0, 0, fmt.Errorf("invalid hh:mm")
		}
		if h < 0 || h > 23 || m < 0 || m > 59 {
			return 0, 0, fmt.Errorf("hour/minute out of range")
		}
		return h, m, nil
	}
	value = strings.ReplaceAll(value, "时", "点")
	if strings.Contains(value, "点") {
		parts := strings.SplitN(value, "点", 2)
		h, err := strconv.Atoi(strings.TrimSpace(parts[0]))
		if err != nil {
			return 0, 0, fmt.Errorf("invalid hour")
		}
		minuteRaw := strings.TrimSpace(strings.TrimSuffix(parts[1], "分"))
		m := 0
		if minuteRaw != "" {
			mv, err := strconv.Atoi(minuteRaw)
			if err != nil {
				return 0, 0, fmt.Errorf("invalid minute")
			}
			m = mv
		}
		if h < 0 || h > 23 || m < 0 || m > 59 {
			return 0, 0, fmt.Errorf("hour/minute out of range")
		}
		return h, m, nil
	}
	h, err := strconv.Atoi(value)
	if err != nil {
		return 0, 0, fmt.Errorf("invalid hour")
	}
	if h < 0 || h > 23 {
		return 0, 0, fmt.Errorf("hour out of range")
	}
	return h, 0, nil
}

func parseDayToken(token string) (int, error) {
	raw := strings.TrimSpace(token)
	if raw == "" {
		return 0, fmt.Errorf("empty day token")
	}
	if v, err := strconv.Atoi(raw); err == nil && v > 0 {
		return v, nil
	}
	v := parseChineseNumber(raw)
	if v <= 0 {
		return 0, fmt.Errorf("invalid day token")
	}
	return v, nil
}

func parseChineseNumber(raw string) int {
	s := strings.TrimSpace(raw)
	if s == "" {
		return 0
	}
	digit := map[string]int{
		"零": 0,
		"一": 1,
		"二": 2,
		"两": 2,
		"三": 3,
		"四": 4,
		"五": 5,
		"六": 6,
		"七": 7,
		"八": 8,
		"九": 9,
	}
	if v, ok := digit[s]; ok {
		return v
	}
	if strings.Contains(s, "十") {
		parts := strings.SplitN(s, "十", 2)
		tens := 1
		if strings.TrimSpace(parts[0]) != "" {
			v, ok := digit[strings.TrimSpace(parts[0])]
			if !ok {
				return 0
			}
			tens = v
		}
		ones := 0
		if len(parts) > 1 && strings.TrimSpace(parts[1]) != "" {
			v, ok := digit[strings.TrimSpace(parts[1])]
			if !ok {
				return 0
			}
			ones = v
		}
		return tens*10 + ones
	}
	return 0
}

// CaptureSnapshot 采集并持久化当前快照，不做 diff。
func (r *Reconciler) CaptureSnapshot(ctx context.Context) (*internal.Snapshot, error) {
	snap, err := r.scanner.ReconcileScan(ctx, r.sourceID, r.rootPath)
	if err != nil {
		return nil, err
	}
	r.mu.Lock()
	r.lastSnapshot = snap
	r.mu.Unlock()
	if err := r.persistSnapshot(snap); err != nil {
		return nil, err
	}
	r.reportSnapshotMeta(ctx, snap)
	return snap, nil
}

// RunOnce 执行一次 reconcile，对比快照差异并上报差异事件。
// 若上一次 reconcile 尚未完成，直接跳过本次。
func (r *Reconciler) RunOnce(ctx context.Context) {
	r.mu.Lock()
	if r.running {
		r.mu.Unlock()
		r.log.Warn("reconcile already running, skipping", zap.String("source_id", r.sourceID))
		return
	}
	r.running = true
	r.mu.Unlock()

	defer func() {
		r.mu.Lock()
		r.running = false
		r.mu.Unlock()
	}()

	r.log.Info("reconcile started", zap.String("source_id", r.sourceID))
	reconcileStart := time.Now()

	newSnap, err := r.scanner.ReconcileScan(ctx, r.sourceID, r.rootPath)
	if err != nil {
		r.log.Error("reconcile scan failed",
			zap.String("source_id", r.sourceID),
			zap.Duration("reconcile_cost", time.Since(reconcileStart)),
			zap.Error(err),
		)
		return
	}

	r.mu.Lock()
	lastSnap := r.lastSnapshot
	r.mu.Unlock()
	if lastSnap == nil {
		if loaded, loadErr := r.loadSnapshot(); loadErr != nil {
			r.log.Warn("load snapshot failed", zap.String("source_id", r.sourceID), zap.Error(loadErr))
		} else if loaded != nil {
			lastSnap = loaded
			r.mu.Lock()
			r.lastSnapshot = loaded
			r.mu.Unlock()
		}
	}

	if lastSnap == nil {
		// 没有历史快照，退化为全量扫描
		r.log.Info("no previous snapshot, triggering full scan", zap.String("source_id", r.sourceID))
		if err := r.scanner.FullScan(ctx, r.sourceID, r.rootPath); err != nil {
			r.log.Error("fallback full scan failed", zap.String("source_id", r.sourceID), zap.Error(err))
		}
		r.mu.Lock()
		r.lastSnapshot = newSnap
		r.mu.Unlock()
		if persistErr := r.persistSnapshot(newSnap); persistErr != nil {
			r.log.Warn("persist snapshot failed after fallback full scan", zap.String("source_id", r.sourceID), zap.Error(persistErr))
		} else {
			r.reportSnapshotMeta(ctx, newSnap)
		}
		r.log.Info("reconcile done",
			zap.String("source_id", r.sourceID),
			zap.Int("diff_events", 0),
			zap.Duration("reconcile_cost", time.Since(reconcileStart)),
		)
		return
	}

	events := r.diff(lastSnap, newSnap)

	r.mu.Lock()
	r.lastSnapshot = newSnap
	r.mu.Unlock()
	if persistErr := r.persistSnapshot(newSnap); persistErr != nil {
		r.log.Warn("persist snapshot failed", zap.String("source_id", r.sourceID), zap.Error(persistErr))
	} else {
		r.reportSnapshotMeta(ctx, newSnap)
	}

	r.log.Info("reconcile done",
		zap.String("source_id", r.sourceID),
		zap.Int("diff_events", len(events)),
		zap.Duration("reconcile_cost", time.Since(reconcileStart)),
	)

	if len(events) == 0 {
		return
	}

	// 上报差异事件到控制面
	if err := r.reporter.ReportEvents(ctx, internal.ReportEventsRequest{
		AgentID: r.agentID,
		Events:  events,
	}); err != nil {
		r.log.Error("reconcile report events failed", zap.String("source_id", r.sourceID), zap.Error(err))
	}
}

// diff 对比两个快照，返回差异事件列表。
func (r *Reconciler) diff(old, new *internal.Snapshot) []internal.FileEvent {
	var events []internal.FileEvent
	now := time.Now()

	// 新增 / 修改
	for path, newEntry := range new.Files {
		oldEntry, exists := old.Files[path]
		if !exists {
			events = append(events, internal.FileEvent{
				SourceID:   r.sourceID,
				TenantID:   r.tenantID,
				EventType:  internal.FileCreated,
				Path:       path,
				IsDir:      newEntry.IsDir,
				OccurredAt: now,
			})
		} else if newEntry.ModTime != oldEntry.ModTime ||
			newEntry.Size != oldEntry.Size ||
			(oldEntry.Checksum != "" && newEntry.Checksum != "" && newEntry.Checksum != oldEntry.Checksum) {
			events = append(events, internal.FileEvent{
				SourceID:   r.sourceID,
				TenantID:   r.tenantID,
				EventType:  internal.FileModified,
				Path:       path,
				IsDir:      newEntry.IsDir,
				OccurredAt: now,
			})
		}
	}

	// 删除
	for path, oldEntry := range old.Files {
		if _, exists := new.Files[path]; !exists {
			events = append(events, internal.FileEvent{
				SourceID:   r.sourceID,
				TenantID:   r.tenantID,
				EventType:  internal.FileDeleted,
				Path:       path,
				IsDir:      oldEntry.IsDir,
				OccurredAt: now,
			})
		}
	}

	return events
}

func (r *Reconciler) snapshotPath() string {
	base := r.snapshotRoot
	if base == "" {
		base = "/var/lib/ragscan/snapshots"
	}
	return filepath.Join(base, "sources", r.sourceID, "snapshot.json")
}

func (r *Reconciler) loadSnapshot() (*internal.Snapshot, error) {
	path := r.snapshotPath()
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	var persisted persistedSnapshot
	if err := json.Unmarshal(data, &persisted); err != nil {
		return nil, err
	}
	snap := &internal.Snapshot{
		SourceID: persisted.SourceID,
		TakenAt:  persisted.TakenAt,
		Files:    make(map[string]internal.SnapshotEntry, len(persisted.Files)),
	}
	for path, item := range persisted.Files {
		modNs := item.ModTimeUnixNano
		if modNs == 0 && item.ModTimeUnix != 0 {
			modNs = item.ModTimeUnix * int64(time.Second)
		}
		modTime := time.Time{}
		if modNs > 0 {
			modTime = time.Unix(0, modNs).UTC()
		}
		snap.Files[path] = internal.SnapshotEntry{
			Size:     item.Size,
			ModTime:  modTime,
			IsDir:    item.IsDir,
			Checksum: item.Checksum,
		}
	}
	return snap, nil
}

func (r *Reconciler) persistSnapshot(snap *internal.Snapshot) error {
	if snap == nil {
		return nil
	}
	path := r.snapshotPath()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	persisted := persistedSnapshot{
		SourceID: snap.SourceID,
		TakenAt:  snap.TakenAt.UTC(),
		Files:    make(map[string]persistedSnapshotItem, len(snap.Files)),
	}
	for p, item := range snap.Files {
		mod := item.ModTime.UTC()
		persisted.Files[p] = persistedSnapshotItem{
			Size:            item.Size,
			ModTimeUnix:     mod.Unix(),
			ModTimeUnixNano: mod.UnixNano(),
			IsDir:           item.IsDir,
			Checksum:        item.Checksum,
		}
	}
	data, err := json.Marshal(persisted)
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), ".snapshot-*")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	if _, err := tmp.Write(data); err != nil {
		_ = tmp.Close()
		_ = os.Remove(tmpPath)
		return err
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		_ = os.Remove(tmpPath)
		return err
	}
	if err := tmp.Close(); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}
	if err := os.Rename(tmpPath, path); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}
	return nil
}

func (r *Reconciler) reportSnapshotMeta(ctx context.Context, snap *internal.Snapshot) {
	if snap == nil {
		return
	}
	req := internal.ReportSnapshotRequest{
		AgentID:     r.agentID,
		SourceID:    r.sourceID,
		SnapshotRef: r.snapshotPath(),
		FileCount:   int64(len(snap.Files)),
		TakenAt:     snap.TakenAt.UTC(),
	}
	if err := r.reporter.ReportSnapshot(ctx, req); err != nil {
		r.log.Warn("report snapshot metadata failed", zap.String("source_id", r.sourceID), zap.Error(err))
	}
}
