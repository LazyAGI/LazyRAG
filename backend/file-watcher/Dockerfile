FROM golang:1.24.6-alpine AS builder
WORKDIR /src

ARG GOPROXY=https://proxy.golang.org,direct
ENV GOPROXY=${GOPROXY}

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -o /out/file_watcher ./cmd/main.go

FROM alpine:3.19
WORKDIR /app

RUN apk add --no-cache ca-certificates tzdata

COPY --from=builder /out/file_watcher /app/file_watcher
COPY configs/agent.yaml /app/configs/agent.yaml

ENTRYPOINT ["/app/file_watcher"]
CMD ["-config", "/app/configs/agent.yaml"]
