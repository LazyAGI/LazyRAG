package config

import (
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

type Config struct {
	ListenAddr        string          `yaml:"listen_addr"`
	DatabaseDriver    string          `yaml:"database_driver"`
	DatabaseDSN       string          `yaml:"database_dsn"`
	DatabasePath      string          `yaml:"database_path"` // deprecated: kept for backward compatibility
	LogLevel          string          `yaml:"log_level"`
	AgentToken        string          `yaml:"agent_token"`
	DefaultIdleWindow time.Duration   `yaml:"default_idle_window"`
	SchedulerTick     time.Duration   `yaml:"scheduler_tick"`
	EventMerge        MergeConfig     `yaml:"event_merge"`
	Parser            ParserConfig    `yaml:"parser"`
	Core              CoreConfig      `yaml:"core"`
	Metrics           MetricsConfig   `yaml:"metrics"`
	Worker            WorkerConfig    `yaml:"worker"`
	CloudSync         CloudSyncConfig `yaml:"cloud_sync"`
}

type MergeConfig struct {
	FlushTick      time.Duration `yaml:"flush_tick"`
	FlushIdle      time.Duration `yaml:"flush_idle"`
	FlushMaxWait   time.Duration `yaml:"flush_max_wait"`
	FlushBatchSize int           `yaml:"flush_batch_size"`
	MaxMemoryKeys  int           `yaml:"max_memory_keys"`
}

type WorkerConfig struct {
	Enabled bool `yaml:"enabled"`
	// Deprecated: execution mode has been unified to core_task.
	ExecutionMode       string        `yaml:"execution_mode"`
	Tick                time.Duration `yaml:"tick"`
	MaxConcurrent       int           `yaml:"max_concurrent"`
	MaxPerTenant        int           `yaml:"max_per_tenant"`
	MaxPerSource        int           `yaml:"max_per_source"`
	MaxLargeFile        int           `yaml:"max_large_file"`
	LargeFileThreshold  int64         `yaml:"large_file_threshold_bytes"`
	ClaimBatchSize      int           `yaml:"claim_batch_size"`
	LeaseDuration       time.Duration `yaml:"lease_duration"`
	RetryBaseBackoff    time.Duration `yaml:"retry_base_backoff"`
	RetryMaxBackoff     time.Duration `yaml:"retry_max_backoff"`
	AgentTimeout        time.Duration `yaml:"agent_timeout"`
	CommandAckTimeout   time.Duration `yaml:"command_ack_timeout"`
	CommandMaxAttempts  int           `yaml:"command_max_attempts"`
	AgentOfflineTimeout time.Duration `yaml:"agent_offline_timeout"`
}

type ParserConfig struct {
	// Deprecated: parser is no longer used by runtime execution path.
	Enabled   bool          `yaml:"enabled"`
	Endpoint  string        `yaml:"endpoint"`
	Timeout   time.Duration `yaml:"timeout"`
	AuthToken string        `yaml:"auth_token"`
}

type CoreConfig struct {
	Enabled   bool          `yaml:"enabled"`
	Endpoint  string        `yaml:"endpoint"`
	DatasetID string        `yaml:"dataset_id"`
	UserID    string        `yaml:"user_id"`
	UserName  string        `yaml:"user_name"`
	StartMode string        `yaml:"start_mode"`
	AuthToken string        `yaml:"auth_token"`
	Timeout   time.Duration `yaml:"timeout"`
}

type MetricsConfig struct {
	Enabled bool          `yaml:"enabled"`
	Tick    time.Duration `yaml:"tick"`
}

type CloudSyncConfig struct {
	Enabled                  bool          `yaml:"enabled"`
	Tick                     time.Duration `yaml:"tick"`
	MaxConcurrent            int           `yaml:"max_concurrent"`
	LockTTL                  time.Duration `yaml:"lock_ttl"`
	DefaultScheduleTZ        string        `yaml:"default_schedule_tz"`
	HTTPTimeout              time.Duration `yaml:"http_timeout"`
	RetryMaxAttempts         int           `yaml:"retry_max_attempts"`
	RetryBaseBackoff         time.Duration `yaml:"retry_base_backoff"`
	RetryMaxBackoff          time.Duration `yaml:"retry_max_backoff"`
	AuthServiceBaseURL       string        `yaml:"auth_service_base_url"`
	AuthServiceInternalToken string        `yaml:"auth_service_internal_token"`
	TempDir                  string        `yaml:"temp_dir"`
}

func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}
	cfg := defaultConfig()
	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}
	cfg.normalizeDatabaseConfig()
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	if strings.EqualFold(cfg.DatabaseDriver, "sqlite") {
		path := strings.TrimSpace(cfg.DatabaseDSN)
		if strings.HasPrefix(path, "file:") {
			path = strings.TrimPrefix(path, "file:")
			if idx := strings.Index(path, "?"); idx >= 0 {
				path = path[:idx]
			}
		}
		if path != "" && path != ":memory:" {
			if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
				return nil, fmt.Errorf("mkdir db dir: %w", err)
			}
		}
	}
	return cfg, nil
}

func defaultConfig() *Config {
	return &Config{
		ListenAddr:        "127.0.0.1:18080",
		DatabaseDriver:    "postgres",
		DatabaseDSN:       "host=127.0.0.1 user=root password=123456 dbname=scan_control_plane port=5432 sslmode=disable TimeZone=UTC",
		LogLevel:          "info",
		AgentToken:        "",
		DefaultIdleWindow: time.Hour,
		SchedulerTick:     30 * time.Second,
		EventMerge: MergeConfig{
			FlushTick:      500 * time.Millisecond,
			FlushIdle:      2 * time.Second,
			FlushMaxWait:   5 * time.Second,
			FlushBatchSize: 256,
			MaxMemoryKeys:  10000,
		},
		Worker: WorkerConfig{
			Enabled:             true,
			ExecutionMode:       "core_task",
			Tick:                time.Second,
			MaxConcurrent:       4,
			MaxPerTenant:        2,
			MaxPerSource:        2,
			MaxLargeFile:        1,
			LargeFileThreshold:  100 * 1024 * 1024,
			ClaimBatchSize:      32,
			LeaseDuration:       30 * time.Second,
			RetryBaseBackoff:    2 * time.Second,
			RetryMaxBackoff:     60 * time.Second,
			AgentTimeout:        15 * time.Second,
			CommandAckTimeout:   30 * time.Second,
			CommandMaxAttempts:  8,
			AgentOfflineTimeout: 45 * time.Second,
		},
		Parser: ParserConfig{
			Enabled:   false,
			Endpoint:  "",
			Timeout:   60 * time.Second,
			AuthToken: "",
		},
		Core: CoreConfig{
			Enabled:   false,
			Endpoint:  "",
			DatasetID: "",
			UserID:    "scan-control-plane",
			UserName:  "scan-control-plane",
			StartMode: "ASYNC",
			AuthToken: "",
			Timeout:   60 * time.Second,
		},
		Metrics: MetricsConfig{
			Enabled: true,
			Tick:    30 * time.Second,
		},
		CloudSync: CloudSyncConfig{
			Enabled:            true,
			Tick:               30 * time.Second,
			MaxConcurrent:      4,
			LockTTL:            20 * time.Minute,
			DefaultScheduleTZ:  "Asia/Shanghai",
			HTTPTimeout:        30 * time.Second,
			RetryMaxAttempts:   3,
			RetryBaseBackoff:   time.Second,
			RetryMaxBackoff:    30 * time.Second,
			AuthServiceBaseURL: "http://auth-service:8000",
			TempDir:            "/var/lib/ragscan/cloud-sync-tmp",
		},
	}
}

func (c *Config) normalizeDatabaseConfig() {
	c.DatabaseDriver = strings.ToLower(strings.TrimSpace(c.DatabaseDriver))
	c.DatabaseDSN = strings.TrimSpace(c.DatabaseDSN)
	c.DatabasePath = strings.TrimSpace(c.DatabasePath)

	if c.DatabaseDriver == "" && c.DatabasePath != "" {
		c.DatabaseDriver = "sqlite"
	}
	if c.DatabaseDSN == "" && c.DatabasePath != "" {
		c.DatabaseDSN = c.DatabasePath
	}
	if c.DatabaseDriver == "" {
		c.DatabaseDriver = "postgres"
	}
	c.Worker.ExecutionMode = strings.ToLower(strings.TrimSpace(c.Worker.ExecutionMode))
	c.AgentToken = strings.TrimSpace(c.AgentToken)
	c.Core.Endpoint = strings.TrimSpace(c.Core.Endpoint)
	c.Core.DatasetID = strings.TrimSpace(c.Core.DatasetID)
	c.Core.UserID = strings.TrimSpace(c.Core.UserID)
	c.Core.UserName = strings.TrimSpace(c.Core.UserName)
	c.Core.StartMode = strings.TrimSpace(c.Core.StartMode)
	c.CloudSync.DefaultScheduleTZ = strings.TrimSpace(c.CloudSync.DefaultScheduleTZ)
	c.CloudSync.AuthServiceBaseURL = strings.TrimSpace(c.CloudSync.AuthServiceBaseURL)
	c.CloudSync.AuthServiceInternalToken = strings.TrimSpace(c.CloudSync.AuthServiceInternalToken)
	c.CloudSync.TempDir = strings.TrimSpace(c.CloudSync.TempDir)
}

func (c *Config) Validate() error {
	if c.ListenAddr == "" {
		return fmt.Errorf("listen_addr is required")
	}
	if c.AgentToken == "" && !listenAddrIsLoopback(c.ListenAddr) {
		return fmt.Errorf("agent_token is required when listen_addr is not loopback")
	}
	if c.DatabaseDriver != "postgres" && c.DatabaseDriver != "sqlite" {
		return fmt.Errorf("database_driver must be one of: postgres, sqlite")
	}
	if strings.TrimSpace(c.DatabaseDSN) == "" {
		return fmt.Errorf("database_dsn is required")
	}
	if c.DefaultIdleWindow <= 0 {
		return fmt.Errorf("default_idle_window must be > 0")
	}
	if c.SchedulerTick <= 0 {
		return fmt.Errorf("scheduler_tick must be > 0")
	}
	if c.EventMerge.FlushTick <= 0 {
		return fmt.Errorf("event_merge.flush_tick must be > 0")
	}
	if c.EventMerge.FlushIdle <= 0 {
		return fmt.Errorf("event_merge.flush_idle must be > 0")
	}
	if c.EventMerge.FlushMaxWait <= 0 {
		return fmt.Errorf("event_merge.flush_max_wait must be > 0")
	}
	if c.EventMerge.FlushBatchSize <= 0 {
		return fmt.Errorf("event_merge.flush_batch_size must be > 0")
	}
	if c.EventMerge.MaxMemoryKeys <= 0 {
		return fmt.Errorf("event_merge.max_memory_keys must be > 0")
	}
	if c.Worker.Tick <= 0 {
		return fmt.Errorf("worker.tick must be > 0")
	}
	if c.Worker.ExecutionMode == "" {
		c.Worker.ExecutionMode = "core_task"
	}
	if c.Worker.ExecutionMode != "core_task" {
		// Keep backward compatibility with legacy configs and force the only
		// supported runtime mode.
		c.Worker.ExecutionMode = "core_task"
	}
	if c.Worker.MaxConcurrent <= 0 {
		return fmt.Errorf("worker.max_concurrent must be > 0")
	}
	if c.Worker.MaxPerTenant <= 0 {
		return fmt.Errorf("worker.max_per_tenant must be > 0")
	}
	if c.Worker.MaxPerSource <= 0 {
		return fmt.Errorf("worker.max_per_source must be > 0")
	}
	if c.Worker.MaxLargeFile <= 0 {
		return fmt.Errorf("worker.max_large_file must be > 0")
	}
	if c.Worker.LargeFileThreshold <= 0 {
		return fmt.Errorf("worker.large_file_threshold_bytes must be > 0")
	}
	if c.Worker.ClaimBatchSize <= 0 {
		return fmt.Errorf("worker.claim_batch_size must be > 0")
	}
	if c.Worker.LeaseDuration <= 0 {
		return fmt.Errorf("worker.lease_duration must be > 0")
	}
	if c.Worker.RetryBaseBackoff <= 0 || c.Worker.RetryMaxBackoff <= 0 {
		return fmt.Errorf("worker retry backoff must be > 0")
	}
	if c.Worker.CommandMaxAttempts <= 0 {
		return fmt.Errorf("worker.command_max_attempts must be > 0")
	}
	if c.Worker.CommandAckTimeout <= 0 {
		return fmt.Errorf("worker.command_ack_timeout must be > 0")
	}
	if c.Worker.AgentOfflineTimeout <= 0 {
		return fmt.Errorf("worker.agent_offline_timeout must be > 0")
	}
	if c.CloudSync.Enabled {
		if c.CloudSync.Tick <= 0 {
			return fmt.Errorf("cloud_sync.tick must be > 0")
		}
		if c.CloudSync.MaxConcurrent <= 0 {
			return fmt.Errorf("cloud_sync.max_concurrent must be > 0")
		}
		if c.CloudSync.LockTTL <= 0 {
			return fmt.Errorf("cloud_sync.lock_ttl must be > 0")
		}
		if c.CloudSync.HTTPTimeout <= 0 {
			return fmt.Errorf("cloud_sync.http_timeout must be > 0")
		}
		if c.CloudSync.RetryMaxAttempts <= 0 {
			return fmt.Errorf("cloud_sync.retry_max_attempts must be > 0")
		}
		if c.CloudSync.RetryBaseBackoff <= 0 || c.CloudSync.RetryMaxBackoff <= 0 {
			return fmt.Errorf("cloud_sync retry backoff must be > 0")
		}
		if c.CloudSync.AuthServiceBaseURL == "" {
			return fmt.Errorf("cloud_sync.auth_service_base_url is required when cloud_sync.enabled=true")
		}
	}
	if c.Core.Enabled && strings.TrimSpace(c.Core.Endpoint) == "" {
		return fmt.Errorf("core.endpoint is required when core.enabled=true")
	}
	if c.Core.Enabled && strings.TrimSpace(c.Core.UserID) == "" {
		return fmt.Errorf("core.user_id is required when core.enabled=true")
	}
	if c.Core.Timeout <= 0 {
		return fmt.Errorf("core.timeout must be > 0")
	}
	if c.Metrics.Tick <= 0 {
		return fmt.Errorf("metrics.tick must be > 0")
	}
	return nil
}

func listenAddrIsLoopback(listenAddr string) bool {
	host := strings.TrimSpace(listenAddr)
	if host == "" {
		return false
	}
	if parsedHost, _, err := net.SplitHostPort(host); err == nil {
		host = strings.TrimSpace(parsedHost)
	}
	host = strings.Trim(host, "[]")
	if host == "" {
		return false
	}
	if strings.EqualFold(host, "localhost") {
		return true
	}
	if ip := net.ParseIP(host); ip != nil {
		return ip.IsLoopback()
	}
	return false
}
