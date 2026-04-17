package fs

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"time"

	"go.uber.org/zap"

	internal "github.com/lazyrag/file_watcher/internal"
	"github.com/lazyrag/file_watcher/internal/config"
)

// Scanner 扫描接口。
type Scanner interface {
	FullScan(ctx context.Context, sourceID string, root string) error
	ReconcileScan(ctx context.Context, sourceID string, root string) (*internal.Snapshot, error)
	Stat(ctx context.Context, path string) (internal.FileMeta, error)
}

// ScanReporter 扫描结果上报接口（由 control.Client 实现）。
type ScanReporter interface {
	ReportScanResults(ctx context.Context, req internal.ReportScanResultsRequest) error
}

type scanner struct {
	agentID   string
	cfg       config.ScanConfig
	reporter  ScanReporter
	validator PathValidator
	log       *zap.Logger

	// 预处理后的扩展名集合，key 统一为小写带点（如 ".pdf"）
	includeExts map[string]struct{}
	excludeExts map[string]struct{}
}

func NewScanner(agentID string, cfg config.ScanConfig, reporter ScanReporter, validator PathValidator, log *zap.Logger) Scanner {
	s := &scanner{
		agentID:   agentID,
		cfg:       cfg,
		reporter:  reporter,
		validator: validator,
		log:       log,
	}
	if len(cfg.IncludeExtensions) > 0 {
		s.includeExts = normalizeExts(cfg.IncludeExtensions)
	} else if len(cfg.ExcludeExtensions) > 0 {
		s.excludeExts = normalizeExts(cfg.ExcludeExtensions)
	}
	return s
}

// normalizeExts 统一扩展名格式：小写 + 确保有 "." 前缀。
func normalizeExts(exts []string) map[string]struct{} {
	m := make(map[string]struct{}, len(exts))
	for _, e := range exts {
		e = strings.ToLower(e)
		if !strings.HasPrefix(e, ".") {
			e = "." + e
		}
		m[e] = struct{}{}
	}
	return m
}

// shouldInclude 判断文件是否应该被扫描。目录始终通过（需要继续遍历子目录）。
func (s *scanner) shouldInclude(path string, isDir bool) bool {
	if isDir {
		return true
	}
	ext := strings.ToLower(filepath.Ext(path))
	if s.includeExts != nil {
		_, ok := s.includeExts[ext]
		return ok
	}
	if s.excludeExts != nil {
		_, ok := s.excludeExts[ext]
		return !ok
	}
	return true
}

// FullScan 遍历目录树，按批次上报扫描结果。
func (s *scanner) FullScan(ctx context.Context, sourceID string, root string) error {
	batch := make([]internal.ScanRecord, 0, s.cfg.BatchSize)

	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			s.log.Warn("walkdir error", zap.String("path", path), zap.Error(err))
			return nil
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		// 跳过符号链接
		if d.Type()&os.ModeSymlink != 0 {
			return nil
		}
		// 跳过白名单外路径
		if err := s.validator.EnsureAllowed(path); err != nil {
			return nil
		}

		info, err := d.Info()
		if err != nil {
			return nil
		}

		// 文件类型过滤
		if !s.shouldInclude(path, d.IsDir()) {
			s.log.Debug("skipped by extension filter", zap.String("path", path))
			return nil
		}

		batch = append(batch, internal.ScanRecord{
			SourceID: sourceID,
			Path:     path,
			IsDir:    d.IsDir(),
			Size:     info.Size(),
			ModTime:  info.ModTime(),
			Checksum: s.computeChecksum(path, info),
		})

		if len(batch) >= s.cfg.BatchSize {
			if err := s.reportBatch(ctx, sourceID, internal.ScanModeFull, batch); err != nil {
				return err
			}
			batch = batch[:0]
		}
		return nil
	})
	if err != nil {
		return err
	}

	if len(batch) > 0 {
		return s.reportBatch(ctx, sourceID, internal.ScanModeFull, batch)
	}
	return nil
}

// ReconcileScan 扫描目录并返回快照，不上报（由 reconcile 模块负责 diff 后上报）。
func (s *scanner) ReconcileScan(ctx context.Context, sourceID string, root string) (*internal.Snapshot, error) {
	snap := &internal.Snapshot{
		SourceID: sourceID,
		Files:    make(map[string]internal.SnapshotEntry),
		TakenAt:  time.Now(),
	}

	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil || ctx.Err() != nil {
			return nil
		}
		if d.Type()&os.ModeSymlink != 0 {
			return nil
		}
		info, err := d.Info()
		if err != nil {
			return nil
		}
		if !s.shouldInclude(path, d.IsDir()) {
			return nil
		}
		snap.Files[path] = internal.SnapshotEntry{
			Size:     info.Size(),
			ModTime:  info.ModTime(),
			IsDir:    d.IsDir(),
			Checksum: s.computeChecksum(path, info),
		}
		return nil
	})

	return snap, err
}

// Stat 读取单个文件元数据。
func (s *scanner) Stat(_ context.Context, path string) (internal.FileMeta, error) {
	info, err := os.Stat(path)
	if err != nil {
		return internal.FileMeta{}, err
	}
	canonical, err := filepath.EvalSymlinks(path)
	if err != nil {
		canonical = filepath.Clean(path) // 降级：无法解析符号链接时用 Clean
	}
	return internal.FileMeta{
		Path:          path,
		CanonicalPath: canonical,
		Name:          info.Name(),
		Size:          info.Size(),
		ModTime:       info.ModTime(),
		IsDir:         info.IsDir(),
		MimeType:      detectMimeType(path, info),
		Checksum:      s.computeChecksum(path, info),
	}, nil
}

// detectMimeType 通过扩展名做简单 MIME 检测，避免读取文件内容。
func detectMimeType(path string, info os.FileInfo) string {
	if info.IsDir() {
		return "inode/directory"
	}
	ext := strings.ToLower(filepath.Ext(path))
	mimeMap := map[string]string{
		".pdf":  "application/pdf",
		".doc":  "application/msword",
		".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		".xls":  "application/vnd.ms-excel",
		".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
		".ppt":  "application/vnd.ms-powerpoint",
		".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
		".txt":  "text/plain",
		".md":   "text/markdown",
		".csv":  "text/csv",
		".json": "application/json",
		".xml":  "application/xml",
		".html": "text/html",
		".htm":  "text/html",
		".png":  "image/png",
		".jpg":  "image/jpeg",
		".jpeg": "image/jpeg",
		".gif":  "image/gif",
		".zip":  "application/zip",
		".tar":  "application/x-tar",
		".gz":   "application/gzip",
	}
	if mime, ok := mimeMap[ext]; ok {
		return mime
	}
	return "application/octet-stream"
}

func (s *scanner) reportBatch(ctx context.Context, sourceID string, mode internal.ScanMode, batch []internal.ScanRecord) error {
	cp := make([]internal.ScanRecord, len(batch))
	copy(cp, batch)
	return s.reporter.ReportScanResults(ctx, internal.ReportScanResultsRequest{
		AgentID:  s.agentID,
		SourceID: sourceID,
		Mode:     mode,
		Records:  cp,
	})
}

// computeChecksum 对小文件计算 sha256，大文件（超过阈值）跳过返回空字符串。
func (s *scanner) computeChecksum(path string, info os.FileInfo) string {
	if info.IsDir() {
		return ""
	}
	thresholdBytes := s.cfg.LargeFileThresholdMB * 1024 * 1024
	if info.Size() > thresholdBytes {
		return "" // 大文件延后计算
	}
	sum, err := checksumFile(path)
	if err != nil {
		s.log.Warn("checksum failed", zap.String("path", path), zap.Error(err))
		return ""
	}
	return sum
}

// checksumFile 计算文件的 sha256 hex 摘要。
func checksumFile(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()

	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
