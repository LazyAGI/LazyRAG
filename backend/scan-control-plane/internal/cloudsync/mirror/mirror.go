package mirror

import (
	"errors"
	"os"
	"path/filepath"
)

func EnsureDir(absPath string) error {
	return os.MkdirAll(absPath, 0o755)
}

func WriteFileAtomic(absPath string, data []byte) error {
	dir := filepath.Dir(absPath)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	f, err := os.CreateTemp(dir, ".cloudsync-*")
	if err != nil {
		return err
	}
	tmpPath := f.Name()
	cleanup := func() {
		_ = f.Close()
		_ = os.Remove(tmpPath)
	}
	if _, err := f.Write(data); err != nil {
		cleanup()
		return err
	}
	if err := f.Sync(); err != nil {
		cleanup()
		return err
	}
	if err := f.Close(); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}
	if err := os.Rename(tmpPath, absPath); err != nil {
		_ = os.Remove(tmpPath)
		return err
	}
	return nil
}

func DeletePath(absPath string, isDir bool) error {
	if isDir {
		if err := os.Remove(absPath); err != nil && !errors.Is(err, os.ErrNotExist) {
			return err
		}
		return nil
	}
	if err := os.Remove(absPath); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	return nil
}
