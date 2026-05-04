package parser

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"go.uber.org/zap"

	"github.com/lazyrag/scan_control_plane/internal/config"
	"github.com/lazyrag/scan_control_plane/internal/store"
)

type Client interface {
	Parse(ctx context.Context, task store.PendingTask, stagedPath string, stagedURI string, stagedSize int64) error
}

type httpClient struct {
	cfg    config.ParserConfig
	client *http.Client
	log    *zap.Logger
}

type parseRequest struct {
	TenantID       string `json:"tenant_id"`
	DocumentID     int64  `json:"document_id"`
	VersionID      string `json:"version_id"`
	SourceID       string `json:"source_id"`
	SourceObjectID string `json:"source_object_id"`
	OriginType     string `json:"origin_type"`
	OriginPlatform string `json:"origin_platform"`
	TriggerPolicy  string `json:"trigger_policy"`
	StagedPath     string `json:"staged_path"`
	StagedURI      string `json:"staged_uri"`
	StagedSize     int64  `json:"staged_size"`
}

func New(cfg config.ParserConfig, log *zap.Logger) Client {
	return &httpClient{
		cfg: cfg,
		client: &http.Client{
			Timeout: timeoutOrDefault(cfg.Timeout),
		},
		log: log,
	}
}

func (c *httpClient) Parse(ctx context.Context, task store.PendingTask, stagedPath string, stagedURI string, stagedSize int64) error {
	if !c.cfg.Enabled {
		return nil
	}
	body, err := json.Marshal(parseRequest{
		TenantID:       task.TenantID,
		DocumentID:     task.DocumentID,
		VersionID:      task.TargetVersionID,
		SourceID:       task.SourceID,
		SourceObjectID: task.SourceObjectID,
		OriginType:     task.OriginType,
		OriginPlatform: task.OriginPlatform,
		TriggerPolicy:  task.TriggerPolicy,
		StagedPath:     stagedPath,
		StagedURI:      stagedURI,
		StagedSize:     stagedSize,
	})
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.cfg.Endpoint, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	if strings.TrimSpace(c.cfg.AuthToken) != "" {
		req.Header.Set("Authorization", "Bearer "+strings.TrimSpace(c.cfg.AuthToken))
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return fmt.Errorf("call parser endpoint failed: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= http.StatusBadRequest {
		return fmt.Errorf("parser endpoint returned status %d", resp.StatusCode)
	}
	c.log.Debug("parser accepted task",
		zap.Int64("document_id", task.DocumentID),
		zap.String("version", task.TargetVersionID),
		zap.Duration("timeout", c.cfg.Timeout),
	)
	return nil
}

type noopClient struct{}

func NewNoop() Client {
	return noopClient{}
}

func (noopClient) Parse(context.Context, store.PendingTask, string, string, int64) error { return nil }

func timeoutOrDefault(d time.Duration) time.Duration {
	if d <= 0 {
		return 60 * time.Second
	}
	return d
}
