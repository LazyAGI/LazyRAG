ARG DOCKER_MIRROR=docker.m.daocloud.io/library/
FROM ${DOCKER_MIRROR}golang:1.24.6 AS build
WORKDIR /app

# Configure Go module mirrors.
ARG GOPROXY=https://goproxy.cn,direct
ARG GOSUMDB=sum.golang.google.cn
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY
ENV GOPROXY=${GOPROXY}
ENV GOSUMDB=${GOSUMDB}
ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}

COPY core/ ./

RUN CGO_ENABLED=0 go build -o /core .

ARG DOCKER_MIRROR=docker.m.daocloud.io/library/
FROM ${DOCKER_MIRROR}alpine:3.19
RUN apk add --no-cache ca-certificates wget
COPY --from=build /core /core
# Startup wrapper (runs /core; hooks for optional checks)
# COPY --from=build /app/entrypoint.sh /entrypoint.sh
# SQL migrations (read by MIGRATIONS_DIR, default /migrations in docker-compose)
COPY --from=build /app/migrations /migrations
EXPOSE 8000
CMD ["/core"]
# CMD ["/bin/sh", "/entrypoint.sh"]
