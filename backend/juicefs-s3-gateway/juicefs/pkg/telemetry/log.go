/*
 * SigNoz OTLP gRPC 日志上报。
 *
 * 说明：
 * - 仅负责初始化 OTLP gRPC log exporter 和 LoggerProvider；
 * - 具体业务代码可以通过 otel.GetLoggerProvider() 获取 logger，并配合 TraceFieldsFromContext 将 trace_id/span_id 打到日志中；
 * - 为了保持与 trace 一致，资源里同样设置 service.name / service.version。
 */

package telemetry

import (
	"context"

	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc"
	sdklog "go.opentelemetry.io/otel/sdk/log"
	"go.opentelemetry.io/otel/sdk/resource"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
	"google.golang.org/grpc/credentials"
)

// InitLoggerProvider 初始化 OTLP gRPC 日志 exporter，并设置全局 LoggerProvider。
// - serviceName: 服务名，例如 "juicefs-s3-gateway"
// - serviceVersion: 版本号，例如 "v1.0.0"
// - endpoint: OTLP gRPC 地址，如 "signoz-otel-collector:4317"
// - insecure: 是否使用明文（k8s 内网通常为 true）
func InitLoggerProvider(serviceName, serviceVersion, endpoint string, insecure bool) *sdklog.LoggerProvider {
	ctx := context.Background()

	res, err := resource.New(ctx,
		resource.WithAttributes(
			semconv.ServiceNameKey.String(serviceName),
			semconv.ServiceVersionKey.String(serviceVersion),
		),
	)
	if err != nil {
		return nil
	}

	var secureOpt otlploggrpc.Option
	if insecure {
		secureOpt = otlploggrpc.WithInsecure()
	} else {
		secureOpt = otlploggrpc.WithTLSCredentials(credentials.NewClientTLSFromCert(nil, ""))
	}

	exporter, err := otlploggrpc.New(ctx,
		otlploggrpc.WithEndpoint(endpoint),
		secureOpt,
	)
	if err != nil {
		return nil
	}

	lp := sdklog.NewLoggerProvider(
		sdklog.WithResource(res),
		sdklog.WithProcessor(sdklog.NewBatchProcessor(exporter)),
	)
	return lp
}
