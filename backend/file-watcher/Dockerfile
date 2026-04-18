# file_watcher 是宿主机常驻进程。
# 这个 Dockerfile 的定位是：在没有本地 Go 环境时，用容器构建可执行产物。
# 构建容器完成后可直接退出，不作为在线服务容器使用。
#
# 构建与导出示例：
#   docker build -t file-watcher-builder \
#     --network host .
#   docker create --name fw-artifact file-watcher-builder
#   docker cp fw-artifact:/out/file_watcher ./file_watcher
#   docker rm fw-artifact
#
# 导出后在宿主机运行：
#   ./file_watcher -config configs/agent.yaml

FROM golang:1.24.6-alpine AS builder
WORKDIR /build

ARG GOPROXY=https://proxy.golang.org,direct
ENV GOPROXY=${GOPROXY}

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -o /out/file_watcher ./cmd/main.go
