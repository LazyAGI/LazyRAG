FROM python:3.11-slim

ARG OPENCODE_VERSION=1.14.28
ARG OPENCODE_DOWNLOAD_PREFIX=https://gh-proxy.com/
ARG TARGETARCH
ARG LAZYLLM_GITHUB_REF=main
ARG LAZYLLM_ARCHIVE_BASE=https://codeload.github.com/LazyAGI/LazyLLM/tar.gz/refs/heads
ARG APT_MIRROR=http://mirrors.aliyun.com/debian
ARG APT_SECURITY_MIRROR=http://mirrors.aliyun.com/debian-security
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG PIP_DEFAULT_TIMEOUT=300
ARG PIP_RETRIES=10

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENCODE_BIN=/usr/local/bin/opencode \
    OPENCODE_DATA_DIR=/var/lib/lazyrag/evo/opencode \
    EVO_BASE_DIR=/var/lib/lazyrag/evo \
    EVO_CHAT_SOURCE=/var/lib/lazyrag/chat-source \
    LAZYRAG_MODEL_CONFIG_PATH=/app/chat/runtime_models.inner.yaml \
    PYTHONPATH=/app

RUN --mount=type=secret,id=apt_http_proxy,required=false \
    --mount=type=secret,id=apt_https_proxy,required=false \
    set -eu; \
    apt_http_proxy="$(cat /run/secrets/apt_http_proxy 2>/dev/null || true)"; \
    apt_https_proxy="$(cat /run/secrets/apt_https_proxy 2>/dev/null || true)"; \
    for source_file in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources; do \
      [ -f "$source_file" ] || continue; \
      sed -i \
        -e "s|http://deb.debian.org/debian-security|${APT_SECURITY_MIRROR}|g" \
        -e "s|http://deb.debian.org/debian|${APT_MIRROR}|g" \
        "$source_file"; \
    done; \
    if [ -n "$apt_http_proxy" ] || [ -n "$apt_https_proxy" ]; then \
      { \
        [ -z "$apt_http_proxy" ] || printf 'Acquire::http::Proxy "%s";\n' "$apt_http_proxy"; \
        [ -z "$apt_https_proxy" ] || printf 'Acquire::https::Proxy "%s";\n' "$apt_https_proxy"; \
        printf 'Acquire::Retries "5";\n'; \
        printf 'Acquire::http::Timeout "120";\n'; \
        printf 'Acquire::https::Timeout "120";\n'; \
        printf 'Acquire::ForceIPv4 "true";\n'; \
      } > /etc/apt/apt.conf.d/99proxy; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git curl ca-certificates ripgrep build-essential cmake ninja-build \
        libgl1 libglib2.0-0; \
    rm -f /etc/apt/apt.conf.d/99proxy; \
    rm -rf /var/lib/apt/lists/*

# Keep LazyLLM on the official main branch while avoiding the C++ editable build path.
RUN --mount=type=secret,id=apt_http_proxy,required=false \
    --mount=type=secret,id=apt_https_proxy,required=false \
    set -eu; \
    proxy_http="$(cat /run/secrets/apt_http_proxy 2>/dev/null || true)"; \
    proxy_https="$(cat /run/secrets/apt_https_proxy 2>/dev/null || true)"; \
    export http_proxy="$proxy_http" https_proxy="$proxy_https"; \
    export HTTP_PROXY="$proxy_http" HTTPS_PROXY="$proxy_https"; \
    export PIP_INDEX_URL="${PIP_INDEX_URL}" PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT}" PIP_RETRIES="${PIP_RETRIES}"; \
    export PIP_DISABLE_PIP_VERSION_CHECK=1; \
    curl -fL --http1.1 --no-progress-meter \
      --retry 8 --retry-all-errors --retry-delay 3 \
      --connect-timeout 30 --speed-limit 1024 --speed-time 60 --max-time 900 \
      "${LAZYLLM_ARCHIVE_BASE}/${LAZYLLM_GITHUB_REF}" -o /tmp/lazyllm.tar.gz; \
    mkdir -p /opt/lazyllm; \
    tar -xzf /tmp/lazyllm.tar.gz -C /opt/lazyllm --strip-components=1; \
    rm /tmp/lazyllm.tar.gz; \
    pip install --no-cache-dir \
      toml tqdm filelock pyyaml packaging \
      "fastapi>=0.111.0" "loguru>=0.7.2" "pydantic>=2.11.7,<3.0.0" \
      "requests>=2.32.2" "uvicorn>=0.23.2" "cloudpickle>=3.0.0" \
      "docstring-parser>=0.16,<0.17" "json5>=0.9.25,<0.10.0" \
      "pyjwt>=2.8.0" "psutil>=6.0.0,<7.0.0" "deepdiff>=8.6.1"; \
    site_packages="$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"; \
    printf '/opt/lazyllm\n' > "${site_packages}/lazyllm-main.pth"; \
    printf '%s\n' '#!/usr/bin/env sh' \
      'PYTHONPATH="/opt/lazyllm:${PYTHONPATH:-}" exec python -m lazyllm.cli.main "$@"' \
      > /usr/local/bin/lazyllm; \
    chmod 0755 /usr/local/bin/lazyllm

RUN --mount=type=secret,id=apt_http_proxy,required=false \
    --mount=type=secret,id=apt_https_proxy,required=false \
    set -eu; \
    proxy_http="$(cat /run/secrets/apt_http_proxy 2>/dev/null || true)"; \
    proxy_https="$(cat /run/secrets/apt_https_proxy 2>/dev/null || true)"; \
    export http_proxy="$proxy_http" https_proxy="$proxy_https"; \
    export HTTP_PROXY="$proxy_http" HTTPS_PROXY="$proxy_https"; \
    export PIP_INDEX_URL="${PIP_INDEX_URL}" PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT}" PIP_RETRIES="${PIP_RETRIES}"; \
    export PIP_DISABLE_PIP_VERSION_CHECK=1; \
    cd /opt/lazyllm; \
    lazyllm install rag

RUN --mount=type=secret,id=apt_http_proxy,required=false \
    --mount=type=secret,id=apt_https_proxy,required=false \
    set -eu; \
    proxy_http="$(cat /run/secrets/apt_http_proxy 2>/dev/null || true)"; \
    proxy_https="$(cat /run/secrets/apt_https_proxy 2>/dev/null || true)"; \
    export http_proxy="$proxy_http" https_proxy="$proxy_https"; \
    export HTTP_PROXY="$proxy_http" HTTPS_PROXY="$proxy_https"; \
    case "${TARGETARCH:-amd64}" in \
      amd64) ARCH=x64 ;; \
      arm64) ARCH=arm64 ;; \
      *) echo "unsupported arch ${TARGETARCH}" && exit 1 ;; \
    esac; \
    URL="${OPENCODE_DOWNLOAD_PREFIX}https://github.com/sst/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${ARCH}.tar.gz"; \
    curl -fL --http1.1 --no-progress-meter \
      --retry 8 --retry-all-errors --retry-delay 3 \
      --connect-timeout 30 --speed-limit 1024 --speed-time 60 --max-time 900 \
      "$URL" -o /tmp/opencode.tar.gz; \
    tar -xzf /tmp/opencode.tar.gz -C /usr/local/bin opencode; \
    chmod 0755 /usr/local/bin/opencode; \
    rm /tmp/opencode.tar.gz; \
    opencode --version

COPY evo/requirements.txt /tmp/evo-requirements.txt
RUN --mount=type=secret,id=apt_http_proxy,required=false \
    --mount=type=secret,id=apt_https_proxy,required=false \
    set -eu; \
    proxy_http="$(cat /run/secrets/apt_http_proxy 2>/dev/null || true)"; \
    proxy_https="$(cat /run/secrets/apt_https_proxy 2>/dev/null || true)"; \
    export http_proxy="$proxy_http" https_proxy="$proxy_https"; \
    export HTTP_PROXY="$proxy_http" HTTPS_PROXY="$proxy_https"; \
    export PIP_INDEX_URL="${PIP_INDEX_URL}" PIP_DEFAULT_TIMEOUT="${PIP_DEFAULT_TIMEOUT}" PIP_RETRIES="${PIP_RETRIES}"; \
    export PIP_DISABLE_PIP_VERSION_CHECK=1; \
    pip install -r /tmp/evo-requirements.txt; \
    pip install --no-cache-dir python-dotenv

WORKDIR /app
COPY evo/ /app/evo/
COPY algorithm/chat /app/chat
COPY algorithm/common /app/common
COPY algorithm/vocab /app/vocab
COPY algorithm/processor /app/processor
RUN chmod +x /app/evo/service/entrypoint.sh

EXPOSE 8047
ENTRYPOINT ["/app/evo/service/entrypoint.sh"]
