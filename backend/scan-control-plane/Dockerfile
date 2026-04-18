FROM golang:1.24.6-alpine AS builder
WORKDIR /build

ARG GOPROXY=https://proxy.golang.org,direct
ENV GOPROXY=${GOPROXY}
RUN apk add --no-cache build-base

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=1 GOOS=linux go build -o /out/scan-control-plane ./cmd/main.go

FROM alpine:3.19
RUN apk add --no-cache ca-certificates wget
WORKDIR /app

COPY --from=builder /out/scan-control-plane /usr/local/bin/scan-control-plane
COPY --from=builder /build/configs /app/configs

EXPOSE 18080
ENTRYPOINT ["/usr/local/bin/scan-control-plane"]
CMD ["-config", "/app/configs/control-plane.yaml"]
