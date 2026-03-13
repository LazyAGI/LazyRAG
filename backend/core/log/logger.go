// Package log 提供与 neutrino 一致的 zerolog 结构化日志，便于 docker logs 查看。
package log

import (
	"os"
	"time"

	"github.com/rs/zerolog"
)

// Logger 全局 zerolog.Logger，在 main 或 dbmigrate 入口处调用 Init() 后使用
var Logger zerolog.Logger

// Init 初始化全局 Logger：输出到 stdout，控制台可读格式，带时间戳。便于 docker logs 查看
func Init() {
	Logger = zerolog.New(zerolog.ConsoleWriter{
		Out:        os.Stdout,
		TimeFormat: time.RFC3339,
	}).With().Timestamp().Logger()
}

// InitNop 将 Logger 设为 Nop，用于测试或未显式 Init 时避免写日志
func InitNop() {
	Logger = zerolog.Nop()
}
