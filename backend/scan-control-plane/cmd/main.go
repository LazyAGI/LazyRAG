package main

import (
	"context"
	"flag"
	"fmt"
	"os"

	"github.com/lazyrag/scan_control_plane/internal/app"
	"github.com/lazyrag/scan_control_plane/internal/config"
)

func main() {
	configPath := flag.String("config", "configs/control-plane.yaml", "path to control plane config")
	flag.Parse()

	cfg, err := config.Load(*configPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "load config failed: %v\n", err)
		os.Exit(1)
	}

	application, err := app.New(cfg)
	if err != nil {
		fmt.Fprintf(os.Stderr, "create app failed: %v\n", err)
		os.Exit(1)
	}
	if err := application.Run(context.Background()); err != nil {
		fmt.Fprintf(os.Stderr, "run app failed: %v\n", err)
		os.Exit(1)
	}
}
