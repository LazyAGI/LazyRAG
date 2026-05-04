FROM golang:1.24.6 AS build
WORKDIR /app

# 配置国内源
ENV GOPROXY=https://goproxy.cn,direct
ENV GOSUMDB=sum.golang.google.cn

COPY core/ ./

# Allow overriding Go module proxy / network proxy at build time.
ARG GOPROXY=https://goproxy.cn,direct
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV GOPROXY=${GOPROXY}
ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}

RUN CGO_ENABLED=0 go build -o /core .

FROM alpine:3.19
RUN apk add --no-cache ca-certificates wget
COPY --from=build /core /core
# Startup wrapper (runs /core; hooks for optional checks)
# COPY --from=build /app/entrypoint.sh /entrypoint.sh
# SQL migrations (read by MIGRATIONS_DIR, default /migrations in docker-compose)
COPY --from=build /app/migrations /migrations
EXPOSE 8000
CMD ["/core"]
# CMD ["/bin/sh", "/entrypoint.sh"]
