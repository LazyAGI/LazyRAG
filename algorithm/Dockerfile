# Stage: base - lazyllm[rag] only. Rebuilt only when upgrading lazyllm version.
FROM python:3.11-slim AS base
WORKDIR /app

RUN apt-get update && apt-get install -y \
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
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir 'lazyllm[rag]==0.7.6a0'

# Stage: default - base + requirements.txt + code. Rebuilt when requirements.txt or code changes.
# Submodule lazyllm is copied via COPY . . and its parent dir is prepended to PYTHONPATH so
# "import lazyllm" resolves to /app/lazyllm/lazyllm/ (submodule) instead of pip-installed lazyllm.
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
ENV PYTHONPATH=/app/lazyllm:/app
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "parsing/parsing.py"]

# Stage: mineru - base + requirements.txt + configurable mineru extra + code.
# Submodule lazyllm is copied via COPY . . and its parent dir is prepended to PYTHONPATH so
# "import lazyllm" resolves to /app/lazyllm/lazyllm/ (submodule) instead of pip-installed lazyllm.
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
ENV PYTHONPATH=/app/lazyllm:/app
CMD ["python", "parsing/mineru.py"]
