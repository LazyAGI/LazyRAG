package fs

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"go.uber.org/zap"

	internal "github.com/lazyrag/file_watcher/internal"
	"github.com/lazyrag/file_watcher/internal/config"
)

// StagingService 文件落地接口。
type StagingService interface {
	StageFile(ctx context.Context, sourceID, documentID, versionID, srcPath string) (internal.StageResult, error)
}

type stagingService struct {
	cfg config.StagingConfig
	log *zap.Logger
	mu  sync.Mutex
}

func NewStagingService(cfg config.StagingConfig, log *zap.Logger) StagingService {
	return &stagingService{cfg: cfg, log: log}
}

type stagingIndex struct {
	Entries map[string]string `json:"entries"` // key(sourceID|srcPath) -> staged filename
}

// StageFile 将源文件流式复制到 staging 落地区，按 source 分目录隔离。
// 文件名使用稳定 hash（保留扩展名）；同一源文件重复触发时保持稳定映射并覆盖原文件。
func (s *stagingService) StageFile(_ context.Context, sourceID, documentID, versionID, srcPath string) (internal.StageResult, error) {
	if !s.cfg.Enabled {
		return internal.StageResult{}, fmt.Errorf("%s: staging is disabled", internal.ErrStageFailed)
	}

	safeSourceID, err := safePathSegment("source_id", sourceID)
	if err != nil {
		return internal.StageResult{}, fmt.Errorf("%s: %w", internal.ErrStageFailed, err)
	}
	_ = documentID
	_ = versionID

	// 确保目标目录存在
	if err := os.MkdirAll(s.cfg.HostRoot, 0o755); err != nil {
		return internal.StageResult{}, fmt.Errorf("%s: mkdir: %w", internal.ErrStageFailed, err)
	}

	srcInfo, err := os.Stat(srcPath)
	if err != nil {
		return internal.StageResult{}, fmt.Errorf("%s: stat src: %w", internal.ErrStageFailed, err)
	}
	if srcInfo.IsDir() {
		return internal.StageResult{}, fmt.Errorf("%s: source path is a directory", internal.ErrStageFailed)
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	idx, err := s.loadIndex()
	if err != nil {
		return internal.StageResult{}, fmt.Errorf("%s: load index: %w", internal.ErrStageFailed, err)
	}
	key := stagingIndexKey(safeSourceID, srcPath)
	prevPath := strings.TrimSpace(idx.Entries[key])
	relPath, collisionDepth := nextHashedRelativePath(safeSourceID, srcPath, key, idx.Entries)
	if prevPath != relPath {
		idx.Entries[key] = relPath
		if err := s.persistIndex(idx); err != nil {
			return internal.StageResult{}, fmt.Errorf("%s: persist index: %w", internal.ErrStageFailed, err)
		}
		if collisionDepth > 0 {
			s.log.Info("staging hash collision resolved",
				zap.String("source_id", safeSourceID),
				zap.String("src_path", srcPath),
				zap.Int("collision_depth", collisionDepth),
				zap.String("mapped_name", relPath),
			)
		}
		if prevPath == "" {
			s.log.Info("staging mapping created",
				zap.String("source_id", safeSourceID),
				zap.String("src_path", srcPath),
				zap.String("mapped_name", relPath),
			)
		} else {
			s.log.Info("staging mapping migrated to hash name",
				zap.String("source_id", safeSourceID),
				zap.String("src_path", srcPath),
				zap.String("old_name", prevPath),
				zap.String("mapped_name", relPath),
			)
		}
	} else {
		s.log.Info("staging mapping hit",
			zap.String("source_id", safeSourceID),
			zap.String("src_path", srcPath),
			zap.String("mapped_name", relPath),
		)
	}

	hostDest, err := joinUnderRoot(s.cfg.HostRoot, relPath)
	if err != nil {
		return internal.StageResult{}, fmt.Errorf("%s: %w", internal.ErrStageFailed, err)
	}
	containerDest, err := joinUnderRoot(s.cfg.ContainerRoot, relPath)
	if err != nil {
		return internal.StageResult{}, fmt.Errorf("%s: %w", internal.ErrStageFailed, err)
	}
	if err := os.MkdirAll(filepath.Dir(hostDest), 0o755); err != nil {
		return internal.StageResult{}, fmt.Errorf("%s: mkdir target dir: %w", internal.ErrStageFailed, err)
	}

	// 幂等检查：目标已存在且 size+mtime 一致则跳过
	if destInfo, err := os.Stat(hostDest); err == nil {
		if destInfo.Size() == srcInfo.Size() && destInfo.ModTime().Equal(srcInfo.ModTime()) {
			s.log.Info("staging skipped (already up-to-date)", zap.String("dest", hostDest))
			return internal.StageResult{
				HostPath:      hostDest,
				ContainerPath: containerDest,
				URI:           "file://" + containerDest,
				Size:          destInfo.Size(),
			}, nil
		}
		s.log.Info("staging overwrite target path",
			zap.String("source_id", safeSourceID),
			zap.String("src_path", srcPath),
			zap.String("dest", hostDest),
			zap.Int64("old_size", destInfo.Size()),
			zap.Int64("new_size", srcInfo.Size()),
			zap.Time("old_mtime", destInfo.ModTime()),
			zap.Time("new_mtime", srcInfo.ModTime()),
		)
	}

	// 流式复制
	written, err := copyFile(srcPath, hostDest, srcInfo.ModTime())
	if err != nil {
		return internal.StageResult{}, fmt.Errorf("%s: copy: %w", internal.ErrStageFailed, err)
	}

	s.log.Info("file staged", zap.String("src", srcPath), zap.String("dest", hostDest), zap.Int64("bytes", written))
	return internal.StageResult{
		HostPath:      hostDest,
		ContainerPath: containerDest,
		URI:           "file://" + containerDest,
		Size:          written,
	}, nil
}

func safePathSegment(label, value string) (string, error) {
	if value == "" {
		return "", fmt.Errorf("%s is empty", label)
	}
	if strings.Contains(value, "/") || strings.Contains(value, "\\") {
		return "", fmt.Errorf("%s contains path separator", label)
	}
	clean := filepath.Clean(value)
	if clean != value || clean == "." || clean == ".." {
		return "", fmt.Errorf("%s contains invalid path segment", label)
	}
	return value, nil
}

func joinUnderRoot(root, relPath string) (string, error) {
	if root == "" {
		return "", fmt.Errorf("empty root")
	}
	cleanRoot := filepath.Clean(root)
	candidate := filepath.Join(cleanRoot, relPath)
	if candidate != cleanRoot && !strings.HasPrefix(candidate, cleanRoot+string(filepath.Separator)) {
		return "", fmt.Errorf("path escapes root")
	}
	return candidate, nil
}

func (s *stagingService) indexPath() string {
	return filepath.Join(filepath.Clean(s.cfg.HostRoot), ".staging-index.json")
}

func (s *stagingService) loadIndex() (stagingIndex, error) {
	path := s.indexPath()
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return stagingIndex{Entries: map[string]string{}}, nil
		}
		return stagingIndex{}, err
	}
	var idx stagingIndex
	if err := json.Unmarshal(data, &idx); err != nil {
		return stagingIndex{}, err
	}
	if idx.Entries == nil {
		idx.Entries = map[string]string{}
	}
	return idx, nil
}

func (s *stagingService) persistIndex(idx stagingIndex) error {
	if idx.Entries == nil {
		idx.Entries = map[string]string{}
	}
	path := s.indexPath()
	data, err := json.Marshal(idx)
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), ".staging-index-*")
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

func stagingIndexKey(sourceID, srcPath string) string {
	return sourceID + "|" + filepath.Clean(srcPath)
}

func nextHashedRelativePath(sourceID, srcPath, key string, entries map[string]string) (string, int) {
	used := make(map[string]struct{}, len(entries))
	for k, v := range entries {
		if k == key {
			continue
		}
		name := strings.TrimSpace(v)
		if name == "" {
			continue
		}
		used[name] = struct{}{}
	}
	for salt := 0; ; salt++ {
		candidate := hashedFileRelativePath(sourceID, srcPath, salt)
		if _, exists := used[candidate]; !exists {
			return candidate, salt
		}
	}
}

func hashedFileRelativePath(sourceID, srcPath string, salt int) string {
	return filepath.Join("sources", sourceID, "files", hashedFileName(sourceID, srcPath, salt))
}

func hashedFileName(sourceID, srcPath string, salt int) string {
	cleanPath := filepath.Clean(srcPath)
	key := sourceID + "|" + cleanPath
	if salt > 0 {
		key = fmt.Sprintf("%s|%d", key, salt)
	}
	sum := sha256.Sum256([]byte(key))
	// 128bit hex 足够作为 staging 名称，且长度更可控。
	hash := hex.EncodeToString(sum[:16])
	ext := filepath.Ext(filepath.Base(cleanPath))
	if ext == "" {
		return hash
	}
	return hash + ext
}

func copyFile(src, dst string, modTime time.Time) (_ int64, retErr error) {
	in, err := os.Open(src)
	if err != nil {
		return 0, err
	}
	defer in.Close()

	tmp, err := os.CreateTemp(filepath.Dir(dst), ".stage-*")
	if err != nil {
		return 0, err
	}
	tmpPath := tmp.Name()
	defer func() {
		if retErr != nil {
			_ = os.Remove(tmpPath)
		}
	}()

	n, err := io.Copy(tmp, in)
	if err != nil {
		_ = tmp.Close()
		return 0, err
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		return 0, err
	}
	if err := tmp.Close(); err != nil {
		return 0, err
	}
	if err := os.Chtimes(tmpPath, modTime, modTime); err != nil {
		return 0, err
	}
	_ = os.Remove(dst)
	if err := os.Rename(tmpPath, dst); err != nil {
		return 0, err
	}
	return n, nil
}
