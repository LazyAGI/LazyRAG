ARG DOCKER_MIRROR=docker.m.daocloud.io/library/
FROM ${DOCKER_MIRROR}golang:1.24.6-alpine AS builder
WORKDIR /src

ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ENV GOPROXY=${GOPROXY} \
    GOSUMDB=${GOSUMDB}

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -o /out/file_watcher ./cmd/main.go

FROM ${DOCKER_MIRROR}alpine:3.19
ARG ALPINE_MIRROR=https://mirrors.aliyun.com/alpine
WORKDIR /app

RUN sed -i "s|https://dl-cdn.alpinelinux.org/alpine|${ALPINE_MIRROR}|g" /etc/apk/repositories \
    && apk add --no-cache ca-certificates tzdata

COPY --from=builder /out/file_watcher /app/file_watcher
COPY configs/agent.yaml /app/configs/agent.yaml

ENTRYPOINT ["/app/file_watcher"]
CMD ["-config", "/app/configs/agent.yaml"]
