# Stage: base - lazyllm[rag] only. Rebuilt only when upgrading lazyllm version.
FROM python:3.11-slim AS base
WORKDIR /app

ARG APT_MIRROR=http://mirrors.aliyun.com/debian
ARG APT_SECURITY_MIRROR=http://mirrors.aliyun.com/debian-security
ARG LAZYLLM_GITHUB_REF=main
ARG LAZYLLM_ARCHIVE_BASE=https://codeload.github.com/LazyAGI/LazyLLM/tar.gz/refs/heads
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG PIP_DEFAULT_TIMEOUT=300
ARG PIP_RETRIES=10

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
    apt-get update && apt-get install -y \
        ca-certificates \
        curl \
        build-essential \
        gcc \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libxcb1 \
        python3-dev \
    && update-ca-certificates \
    && rm -f /etc/apt/apt.conf.d/99proxy \
    && rm -rf /var/lib/apt/lists/*

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
    chmod 0755 /usr/local/bin/lazyllm; \
    cd /opt/lazyllm; \
    lazyllm install rag

# Stage: default - base + requirements.txt + code. Rebuilt when requirements.txt or code changes.
# Use the LazyLLM runtime installed under /opt/lazyllm so tracing behavior matches Evo/chat images.
FROM base AS default
ARG LAZYRAG_GIT_SHA=unknown
ARG LAZYLLM_GIT_SHA=unknown
LABEL org.opencontainers.image.title="LazyRAG algorithm/chat"
LABEL org.opencontainers.image.revision="${LAZYRAG_GIT_SHA}"
LABEL io.lazyrag.lazyrag_git_sha="${LAZYRAG_GIT_SHA}"
LABEL io.lazyrag.lazyllm_git_sha="${LAZYLLM_GIT_SHA}"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x /app/docker-entrypoint.sh
ENV PYTHONPATH=/opt/lazyllm:/app
ENV LAZYRAG_DOCUMENT_SERVER_URL=http://parsing:8000
ENV LAZYRAG_SHARED_UPLOAD_DIR=/var/lib/lazyrag/uploads
ENV LAZYLLM_MOUNT_DIR=/var/lib/lazyrag/uploads
ENV LAZYRAG_MAX_CONCURRENCY=10
ENV LAZYRAG_LLM_PRIORITY=0
ENV LAZYRAG_DEFAULT_CHAT_DATASET=algo
ENV LAZYRAG_CORE_API_URL=http://core:8000
ENV LAZYRAG_MAX_RETRIES=20
ENV LAZYRAG_REVIEW_MAX_RETRIES=5
ENV LAZYRAG_MEMORY_REVIEW_INTERVAL=1
ENV LAZYRAG_SKILL_REVIEW_INTERVAL=5
ENV LAZYRAG_SKILL_REVIEW_DEBUG=false
ENV LAZYRAG_MODEL_CONFIG_PATH=/app/chat/runtime_models.inner.yaml
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "parsing/parsing.py"]

# Stage: mineru - base + requirements.txt + configurable mineru extra + code.
# Use the same LazyLLM runtime as the default stage.
FROM base AS mineru
ARG LAZYRAG_GIT_SHA=unknown
ARG LAZYLLM_GIT_SHA=unknown
LABEL org.opencontainers.image.title="LazyRAG algorithm/mineru"
LABEL org.opencontainers.image.revision="${LAZYRAG_GIT_SHA}"
LABEL io.lazyrag.lazyrag_git_sha="${LAZYRAG_GIT_SHA}"
LABEL io.lazyrag.lazyllm_git_sha="${LAZYLLM_GIT_SHA}"
ARG MINERU_VERSION=2.7.1
ARG MINERU_PACKAGE_VARIANT=pipeline
ARG MINERU_PREINSTALL_CPU_TORCH=1
ARG MINERU_TORCH_VERSION=2.11.0
ARG MINERU_TORCHVISION_VERSION=0.26.0
ARG MINERU_NUMPY_VERSION=1.26.4
ARG MINERU_PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG MINERU_PYPI_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN if [ "$MINERU_PREINSTALL_CPU_TORCH" = "1" ]; then \
        pip install --no-cache-dir \
        --index-url "$MINERU_PYTORCH_INDEX_URL" \
        "torch==${MINERU_TORCH_VERSION}+cpu" \
        "torchvision==${MINERU_TORCHVISION_VERSION}+cpu"; \
    fi
RUN pip install --no-cache-dir "mineru[${MINERU_PACKAGE_VARIANT}]==${MINERU_VERSION}" -i "$MINERU_PYPI_INDEX_URL"
RUN if [ -n "$MINERU_NUMPY_VERSION" ]; then \
        pip install --no-cache-dir "numpy==${MINERU_NUMPY_VERSION}"; \
    fi
COPY . .
ENV PYTHONPATH=/opt/lazyllm:/app
CMD ["python", "parsing/mineru.py"]
