package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

type Config struct {
	AgentID             string        `yaml:"agent_id"`
	TenantID            string        `yaml:"tenant_id"`
	AgentToken          string        `yaml:"agent_token"`
	ListenAddr          string        `yaml:"listen_addr"`
	AdvertiseAddr       string        `yaml:"advertise_addr"`
	ControlPlaneBaseURL string        `yaml:"control_plane_base_url"`
	HeartbeatInterval   time.Duration `yaml:"heartbeat_interval"`
	PullInterval        time.Duration `yaml:"pull_interval"`
	ReconcileInterval   time.Duration `yaml:"reconcile_interval"`
	BaseRoot            string        `yaml:"base_root"`
	HostPathStyle       string        `yaml:"host_path_style"`
	PathMappings        []PathMapping `yaml:"path_mappings"`
	LogLevel            string        `yaml:"log_level"`
	// 以下目录均由 base_root 自动派生，不直接从配置文件读取。
	LogDir   string         `yaml:"-"`
	Staging  StagingConfig  `yaml:"-"`
	Snapshot SnapshotConfig `yaml:"-"`
	Watch    WatchConfig    `yaml:"watch"`
	Scan     ScanConfig     `yaml:"scan"`
	Security SecurityConfig `yaml:"security"`
	HTTP     HTTPConfig     `yaml:"http"`
}

type StagingConfig struct {
	Enabled       bool   `yaml:"-"`
	HostRoot      string `yaml:"-"`
	ContainerRoot string `yaml:"-"`
}

type SnapshotConfig struct {
	HostRoot string `yaml:"-"`
}

type PathMapping struct {
	PublicRoot  string `yaml:"public_root"`
	RuntimeRoot string `yaml:"runtime_root"`
}

type WatchConfig struct {
	DebounceWindow time.Duration `yaml:"debounce_window"`
	MaxBatchSize   int           `yaml:"max_batch_size"`
	Recursive      bool          `yaml:"recursive"`
}

type ScanConfig struct {
	BatchSize            int   `yaml:"batch_size"`
	MaxConcurrency       int   `yaml:"max_concurrency"`
	LargeFileThresholdMB int64 `yaml:"large_file_threshold_mb"`
	// IncludeExtensions 白名单：只扫描这些扩展名（如 [".pdf", ".docx"]）。
	// 与 ExcludeExtensions 互斥，两者同时配置时 Include 优先。
	// 不配置则不过滤。
	IncludeExtensions []string `yaml:"include_extensions"`
	// ExcludeExtensions 黑名单：跳过这些扩展名（如 [".tmp", ".log"]）。
	ExcludeExtensions []string `yaml:"exclude_extensions"`
}

type SecurityConfig struct {
	AllowedRoots []string `yaml:"allowed_roots"`
}

type HTTPConfig struct {
	ReadTimeout  time.Duration `yaml:"read_timeout"`
	WriteTimeout time.Duration `yaml:"write_timeout"`
}

// Load 从 YAML 文件加载配置，并填充默认值。
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config file: %w", err)
	}

	cfg := defaultConfig()
	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("parse config file: %w", err)
	}
	if err := cfg.expandEnvOverrides(); err != nil {
		return nil, err
	}
	if err := cfg.deriveDirsFromBaseRoot(configDir(path)); err != nil {
		return nil, fmt.Errorf("derive dirs from base_root: %w", err)
	}

	if err := cfg.validate(); err != nil {
		return nil, fmt.Errorf("invalid config: %w", err)
	}

	return cfg, nil
}

func configDir(path string) string {
	abs, err := filepath.Abs(path)
	if err != nil {
		return "."
	}
	return filepath.Dir(abs)
}

// expandEnvWithDefault 支持以下两种写法：
// 1) ${VAR}
// 2) ${VAR:-default}
func expandEnvWithDefault(raw string) string {
	return os.Expand(raw, func(key string) string {
		if name, fallback, ok := strings.Cut(key, ":-"); ok {
			if val, exists := os.LookupEnv(name); exists && strings.TrimSpace(val) != "" {
				return val
			}
			return fallback
		}
		return os.Getenv(key)
	})
}

func defaultConfig() *Config {
	return &Config{
		ListenAddr:        "127.0.0.1:19090",
		HeartbeatInterval: 15 * time.Second,
		PullInterval:      10 * time.Second,
		ReconcileInterval: 10 * time.Minute,
		BaseRoot:          "",
		HostPathStyle:     "auto",
		LogLevel:          "info",
		Staging: StagingConfig{
			Enabled:       true,
			ContainerRoot: "/data/staging",
		},
		Watch: WatchConfig{
			DebounceWindow: 2 * time.Second,
			MaxBatchSize:   256,
			Recursive:      true,
		},
		Scan: ScanConfig{
			BatchSize:            500,
			MaxConcurrency:       4,
			LargeFileThresholdMB: 100,
		},
		HTTP: HTTPConfig{
			ReadTimeout:  10 * time.Second,
			WriteTimeout: 30 * time.Second,
		},
	}
}

func (c *Config) expandEnvOverrides() error {
	c.AgentID = strings.TrimSpace(expandEnvWithDefault(c.AgentID))
	c.TenantID = strings.TrimSpace(expandEnvWithDefault(c.TenantID))
	c.AgentToken = strings.TrimSpace(expandEnvWithDefault(c.AgentToken))
	c.ListenAddr = strings.TrimSpace(expandEnvWithDefault(c.ListenAddr))
	c.AdvertiseAddr = strings.TrimSpace(expandEnvWithDefault(c.AdvertiseAddr))
	c.ControlPlaneBaseURL = strings.TrimSpace(expandEnvWithDefault(c.ControlPlaneBaseURL))
	c.BaseRoot = strings.TrimSpace(expandEnvWithDefault(c.BaseRoot))
	c.HostPathStyle = strings.TrimSpace(expandEnvWithDefault(c.HostPathStyle))
	c.LogLevel = strings.TrimSpace(expandEnvWithDefault(c.LogLevel))
	for i := range c.Security.AllowedRoots {
		c.Security.AllowedRoots[i] = strings.TrimSpace(expandEnvWithDefault(c.Security.AllowedRoots[i]))
	}
	for i := range c.PathMappings {
		c.PathMappings[i].PublicRoot = strings.TrimSpace(expandEnvWithDefault(c.PathMappings[i].PublicRoot))
		c.PathMappings[i].RuntimeRoot = strings.TrimSpace(expandEnvWithDefault(c.PathMappings[i].RuntimeRoot))
	}
	if raw, ok := os.LookupEnv("RAGSCAN_HOST_PATH_STYLE"); ok {
		c.HostPathStyle = strings.TrimSpace(raw)
	}
	if raw, ok := os.LookupEnv("RAGSCAN_PATH_MAPPINGS"); ok && strings.TrimSpace(raw) != "" {
		mappings, err := parsePathMappingsEnv(raw)
		if err != nil {
			return fmt.Errorf("parse RAGSCAN_PATH_MAPPINGS: %w", err)
		}
		c.PathMappings = mappings
	} else if len(c.PathMappings) == 0 {
		if mapping, ok := watchVolumePathMappingFromEnv(); ok {
			c.PathMappings = []PathMapping{mapping}
		}
	}
	return nil
}

func watchVolumePathMappingFromEnv() (PathMapping, bool) {
	hostRoot := strings.TrimSpace(os.Getenv("RAGSCAN_WATCH_HOST_DIR"))
	runtimeRoot := strings.TrimSpace(os.Getenv("RAGSCAN_WATCH_CONTAINER_DIR"))
	if hostRoot == "" || runtimeRoot == "" {
		return PathMapping{}, false
	}
	return PathMapping{PublicRoot: hostRoot, RuntimeRoot: runtimeRoot}, true
}

func parsePathMappingsEnv(raw string) ([]PathMapping, error) {
	parts := strings.Split(raw, ",")
	mappings := make([]PathMapping, 0, len(parts))
	for _, part := range parts {
		item := strings.TrimSpace(part)
		if item == "" {
			continue
		}
		left, right, ok := strings.Cut(item, "=")
		if !ok {
			return nil, fmt.Errorf("mapping %q must use public_root=runtime_root", item)
		}
		publicRoot := strings.TrimSpace(left)
		runtimeRoot := strings.TrimSpace(right)
		if publicRoot == "" || runtimeRoot == "" {
			return nil, fmt.Errorf("mapping %q has empty public_root or runtime_root", item)
		}
		mappings = append(mappings, PathMapping{PublicRoot: publicRoot, RuntimeRoot: runtimeRoot})
	}
	return mappings, nil
}

func (c *Config) deriveDirsFromBaseRoot(baseDir string) error {
	base := strings.TrimSpace(c.BaseRoot)
	if base == "" {
		return fmt.Errorf("base_root is required")
	}
	if !filepath.IsAbs(base) {
		base = filepath.Join(baseDir, base)
	}
	base = filepath.Clean(base)
	c.BaseRoot = base

	c.LogDir = filepath.Join(base, "logs")
	c.Staging.HostRoot = filepath.Join(base, "staging")
	c.Staging.Enabled = true
	if strings.TrimSpace(c.Staging.ContainerRoot) == "" {
		c.Staging.ContainerRoot = "/data/staging"
	}
	c.Snapshot.HostRoot = filepath.Join(base, "snapshots")
	return nil
}

// AgentListenURL 返回上报给 control-plane 的 agent 地址（带 scheme）。
func (c *Config) AgentListenURL() string {
	addr := strings.TrimSpace(c.AdvertiseAddr)
	if addr == "" {
		addr = strings.TrimSpace(c.ListenAddr)
	}
	if addr == "" {
		return ""
	}
	if strings.HasPrefix(addr, "http://") || strings.HasPrefix(addr, "https://") {
		return addr
	}
	return "http://" + addr
}

func (c *Config) validate() error {
	if c.AgentID == "" {
		return fmt.Errorf("agent_id is required")
	}
	if c.TenantID == "" {
		return fmt.Errorf("tenant_id is required")
	}
	if c.ControlPlaneBaseURL == "" {
		return fmt.Errorf("control_plane_base_url is required")
	}
	if strings.TrimSpace(c.BaseRoot) == "" {
		return fmt.Errorf("base_root is required (set host path via RAGSCAN_BASE_ROOT)")
	}
	style := strings.ToLower(strings.TrimSpace(c.HostPathStyle))
	if style == "" {
		c.HostPathStyle = "auto"
		style = "auto"
	}
	switch style {
	case "auto", "posix", "windows":
		c.HostPathStyle = style
	default:
		return fmt.Errorf("host_path_style must be auto, posix, or windows")
	}
	for i, mapping := range c.PathMappings {
		if strings.TrimSpace(mapping.PublicRoot) == "" || strings.TrimSpace(mapping.RuntimeRoot) == "" {
			return fmt.Errorf("path_mappings[%d] requires public_root and runtime_root", i)
		}
	}
	return nil
}
