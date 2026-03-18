/*
 * JuiceFS, Copyright 2020 Juicedata, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// Package telemetry 提供 SigNoz OTLP gRPC 的 trace 与 log 上报，并实现 trace 与 log 的关联。
package telemetry

import (
	"context"

	"github.com/sirupsen/logrus"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
	"go.opentelemetry.io/otel/trace"
	"google.golang.org/grpc/credentials"
)

// InitTracerProvider 初始化 OTLP gRPC trace exporter，上报到 SigNoz；insecure 为 true 时使用 WithInsecure()。
func InitTracerProvider(serviceName, serviceVersion, endpoint string, insecure, sampled bool) *sdktrace.TracerProvider {
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

	var secureOpt otlptracegrpc.Option
	if insecure {
		secureOpt = otlptracegrpc.WithInsecure()
	} else {
		secureOpt = otlptracegrpc.WithTLSCredentials(credentials.NewClientTLSFromCert(nil, ""))
	}
	exporter, err := otlptracegrpc.New(ctx,
		otlptracegrpc.WithEndpoint(endpoint),
		secureOpt,
	)
	if err != nil {
		return nil
	}

	var root sdktrace.Sampler
	if sampled {
		root = sdktrace.AlwaysSample()
	} else {
		root = sdktrace.NeverSample()
	}

	tp := sdktrace.NewTracerProvider(
		sdktrace.WithResource(res),
		sdktrace.WithSampler(sdktrace.ParentBased(root)),
		sdktrace.WithBatcher(exporter),
	)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(propagation.TraceContext{}, propagation.Baggage{}))

	return tp
}

// TraceFieldsFromContext 从 context 中提取 trace_id / span_id，方便 logrus 记录到日志里，实现 log 与 trace 的关联。
func TraceFieldsFromContext(ctx context.Context) logrus.Fields {
	if ctx == nil {
		return nil
	}
	span := trace.SpanFromContext(ctx)
	if span == nil {
		return nil
	}
	sc := span.SpanContext()
	if !sc.IsValid() {
		return nil
	}
	return logrus.Fields{
		"trace_id": sc.TraceID().String(),
		"span_id":  sc.SpanID().String(),
	}
}
