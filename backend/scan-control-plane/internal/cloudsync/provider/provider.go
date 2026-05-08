package provider

import (
	"context"
	"time"
)

type ListRequest struct {
	AccessToken     string
	TargetType      string
	TargetRef       string
	ProviderOptions map[string]any
}

type RemoteObject struct {
	ExternalObjectID   string
	ExternalParentID   string
	ExternalPath       string
	ExternalName       string
	ExternalKind       string
	ExternalVersion    string
	ExternalModifiedAt *time.Time
	SizeBytes          int64
	DownloadRef        string
	ProviderMeta       map[string]any
}

type Provider interface {
	Name() string
	ListObjects(ctx context.Context, req ListRequest) ([]RemoteObject, error)
	DownloadObject(ctx context.Context, accessToken string, object RemoteObject) ([]byte, error)
}
