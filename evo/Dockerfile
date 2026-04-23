FROM python:3.11-slim

ARG OPENCODE_VERSION=1.4.3
ARG TARGETARCH

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENCODE_DATA_DIR=/var/lib/lazyrag/evo/opencode \
    EVO_BASE_DIR=/var/lib/lazyrag/evo \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) ARCH=x64 ;; \
      arm64) ARCH=arm64 ;; \
      *) echo "unsupported arch ${TARGETARCH}" && exit 1 ;; \
    esac; \
    URL="https://github.com/sst/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${ARCH}.tar.gz"; \
    curl -fSL "$URL" -o /tmp/opencode.tar.gz; \
    tar -xzf /tmp/opencode.tar.gz -C /usr/local/bin opencode; \
    chmod 0755 /usr/local/bin/opencode; \
    rm /tmp/opencode.tar.gz; \
    opencode --version

COPY evo/requirements.txt /tmp/evo-requirements.txt
RUN pip install -r /tmp/evo-requirements.txt

WORKDIR /app
COPY evo/ /app/evo/

EXPOSE 8047
ENTRYPOINT ["/app/evo/service/entrypoint.sh"]
