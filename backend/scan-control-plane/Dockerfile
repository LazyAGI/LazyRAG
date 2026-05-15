ARG DOCKER_MIRROR=docker.m.daocloud.io/library/
FROM ${DOCKER_MIRROR}golang:1.24.6-alpine AS builder
WORKDIR /build

ARG ALPINE_MIRROR=https://mirrors.aliyun.com/alpine
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ENV GOPROXY=${GOPROXY} \
    GOSUMDB=${GOSUMDB}

RUN sed -i "s|https://dl-cdn.alpinelinux.org/alpine|${ALPINE_MIRROR}|g" /etc/apk/repositories \
    && apk add --no-cache build-base

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=1 GOOS=linux go build -o /out/scan-control-plane ./cmd/main.go

FROM ${DOCKER_MIRROR}alpine:3.19
ARG ALPINE_MIRROR=https://mirrors.aliyun.com/alpine
RUN sed -i "s|https://dl-cdn.alpinelinux.org/alpine|${ALPINE_MIRROR}|g" /etc/apk/repositories \
    && apk add --no-cache ca-certificates wget
WORKDIR /app

COPY --from=builder /out/scan-control-plane /usr/local/bin/scan-control-plane
COPY --from=builder /build/configs /app/configs

EXPOSE 18080
ENTRYPOINT ["/usr/local/bin/scan-control-plane"]
CMD ["-config", "/app/configs/control-plane.yaml"]
