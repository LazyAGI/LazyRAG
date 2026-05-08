package main

import (
	"context"
	"flag"
	"fmt"
	"os"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"

	"github.com/lazyrag/file_watcher/internal/app"
	"github.com/lazyrag/file_watcher/internal/config"
)

func main() {
	cfgPath := flag.String("config", "configs/agent.yaml", "path to config file")
	flag.Parse()

	cfg, err := config.Load(*cfgPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "load config: %v\n", err)
		os.Exit(1)
	}

	log, err := buildLogger(cfg.LogLevel, cfg.LogDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "init logger: %v\n", err)
		os.Exit(1)
	}
	defer log.Sync() //nolint:errcheck

	a := app.New(cfg, log)
	if err := a.Run(context.Background()); err != nil {
		log.Error("run failed", zap.Error(err))
		os.Exit(1)
	}
}

func buildLogger(level, logDir string) (*zap.Logger, error) {
	var zapLevel zapcore.Level
	if err := zapLevel.UnmarshalText([]byte(level)); err != nil {
		zapLevel = zapcore.InfoLevel
	}

	encoderCfg := zap.NewProductionEncoderConfig()
	encoderCfg.TimeKey = "ts"
	encoderCfg.EncodeTime = zapcore.ISO8601TimeEncoder

	zapCfg := zap.Config{
		Level:            zap.NewAtomicLevelAt(zapLevel),
		Development:      false,
		Encoding:         "json",
		EncoderConfig:    encoderCfg,
		OutputPaths:      []string{"stdout"},
		ErrorOutputPaths: []string{"stderr"},
	}

	if logDir != "" {
		if err := os.MkdirAll(logDir, 0o755); err == nil {
			zapCfg.OutputPaths = append(zapCfg.OutputPaths, logDir+"/file_watcher.log")
		}
	}

	return zapCfg.Build()
}
