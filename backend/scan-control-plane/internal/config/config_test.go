package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestValidateRejectsNonPositiveCommandAckTimeout(t *testing.T) {
	t.Parallel()
	cfg := defaultConfig()
	cfg.Worker.CommandAckTimeout = 0

	err := cfg.Validate()
	if err == nil {
		t.Fatalf("expected validate to fail when command_ack_timeout <= 0")
	}
	if !strings.Contains(err.Error(), "worker.command_ack_timeout") {
		t.Fatalf("expected command_ack_timeout validation error, got %v", err)
	}
}

func TestValidateRejectsNonPositiveAgentOfflineTimeout(t *testing.T) {
	t.Parallel()
	cfg := defaultConfig()
	cfg.Worker.AgentOfflineTimeout = -1

	err := cfg.Validate()
	if err == nil {
		t.Fatalf("expected validate to fail when agent_offline_timeout <= 0")
	}
	if !strings.Contains(err.Error(), "worker.agent_offline_timeout") {
		t.Fatalf("expected agent_offline_timeout validation error, got %v", err)
	}
}

func TestValidateRequiresAgentTokenOnNonLoopbackListenAddr(t *testing.T) {
	t.Parallel()
	cfg := defaultConfig()
	cfg.ListenAddr = "0.0.0.0:18080"
	cfg.AgentToken = ""

	err := cfg.Validate()
	if err == nil {
		t.Fatalf("expected validate to fail when non-loopback listen_addr has empty agent_token")
	}
	if !strings.Contains(err.Error(), "agent_token") {
		t.Fatalf("expected agent_token validation error, got %v", err)
	}
}

func TestValidateAllowsEmptyAgentTokenOnLoopbackListenAddr(t *testing.T) {
	t.Parallel()
	cfg := defaultConfig()
	cfg.ListenAddr = "127.0.0.1:18080"
	cfg.AgentToken = ""

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected loopback listen_addr to allow empty agent_token, got %v", err)
	}
}

func TestValidateAllowsDeprecatedParserConfigWithoutEndpoint(t *testing.T) {
	t.Parallel()
	cfg := defaultConfig()
	cfg.Parser.Enabled = true
	cfg.Parser.Endpoint = ""
	cfg.Parser.Timeout = 0

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected deprecated parser config to be ignored, got %v", err)
	}
}

func TestLoadOverridesAuthServiceInternalTokenFromEnv(t *testing.T) {
	t.Setenv("LAZYRAG_AUTH_SERVICE_INTERNAL_TOKEN", "env-internal-token")

	cfgPath := filepath.Join(t.TempDir(), "control-plane.yml")
	if err := os.WriteFile(cfgPath, []byte(`
listen_addr: "127.0.0.1:18080"
database_driver: "sqlite"
database_dsn: ":memory:"
cloud_sync:
  enabled: true
  tick: "30s"
  max_concurrent: 1
  lock_ttl: "20m"
  default_schedule_tz: "Asia/Shanghai"
  http_timeout: "30s"
  retry_max_attempts: 1
  retry_base_backoff: "1s"
  retry_max_backoff: "30s"
  auth_service_base_url: "http://auth-service:8000"
  auth_service_internal_token: "file-internal-token"
`), 0o644); err != nil {
		t.Fatalf("write config failed: %v", err)
	}

	cfg, err := Load(cfgPath)
	if err != nil {
		t.Fatalf("load config failed: %v", err)
	}
	if cfg.CloudSync.AuthServiceInternalToken != "env-internal-token" {
		t.Fatalf("expected env token override, got %q", cfg.CloudSync.AuthServiceInternalToken)
	}
}

func TestValidateCoercesDeprecatedWorkerExecutionMode(t *testing.T) {
	t.Parallel()
	cfg := defaultConfig()
	cfg.Worker.ExecutionMode = "direct_parser"

	if err := cfg.Validate(); err != nil {
		t.Fatalf("expected deprecated worker.execution_mode to be coerced, got %v", err)
	}
	if cfg.Worker.ExecutionMode != "core_task" {
		t.Fatalf("expected execution_mode coerced to core_task, got %s", cfg.Worker.ExecutionMode)
	}
}
