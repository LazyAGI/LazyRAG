FROM python:3.11-slim

ARG OPENCODE_VERSION=1.14.28
ARG TARGETARCH
ARG LAZYLLM_GIT_URL=https://github.com/Mustafa974/LazyLLM.git
ARG LAZYLLM_GIT_BRANCH=tracing_v3
ARG APT_MIRROR=http://mirrors.aliyun.com/debian
ARG APT_SECURITY_MIRROR=http://mirrors.aliyun.com/debian-security
ARG http_proxy
ARG https_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG no_proxy
ARG NO_PROXY

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENCODE_BIN=/usr/local/bin/opencode \
    OPENCODE_DATA_DIR=/var/lib/lazyrag/evo/opencode \
    EVO_BASE_DIR=/var/lib/lazyrag/evo \
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
        git curl ca-certificates build-essential cmake ninja-build \
        libgl1 libglib2.0-0; \
    rm -f /etc/apt/apt.conf.d/99proxy; \
    rm -rf /var/lib/apt/lists/*

# Editable install keeps repo-root pyproject.toml on disk; lazyllm.thirdparty resolves it via
# parents[2] from lazyllm/thirdparty/__init__.py. Plain pip-from-git leaves site-packages without it.
# Pip does not expose Poetry's [rag] extra; use upstream helper to install that group.
RUN --mount=type=secret,id=apt_http_proxy,required=false \
    --mount=type=secret,id=apt_https_proxy,required=false \
    set -eu; \
    proxy_http="$(cat /run/secrets/apt_http_proxy 2>/dev/null || true)"; \
    proxy_https="$(cat /run/secrets/apt_https_proxy 2>/dev/null || true)"; \
    export http_proxy="$proxy_http" https_proxy="$proxy_https"; \
    export HTTP_PROXY="$proxy_http" HTTPS_PROXY="$proxy_https"; \
    git clone --branch "${LAZYLLM_GIT_BRANCH}" --depth 1 "${LAZYLLM_GIT_URL}" /opt/lazyllm; \
    pip install --no-cache-dir -e /opt/lazyllm

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG PIP_DEFAULT_TIMEOUT=300
ARG PIP_RETRIES=10

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
    URL="https://github.com/sst/opencode/releases/download/v${OPENCODE_VERSION}/opencode-linux-${ARCH}.tar.gz"; \
    curl -fSL "$URL" -o /tmp/opencode.tar.gz; \
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
COPY algorithm/processor /app/processor
RUN chmod +x /app/evo/service/entrypoint.sh

EXPOSE 8047
ENTRYPOINT ["/app/evo/service/entrypoint.sh"]
