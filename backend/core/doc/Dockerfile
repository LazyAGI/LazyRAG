ARG DOCKER_MIRROR=docker.m.daocloud.io/library/
FROM ${DOCKER_MIRROR}python:3.11-slim

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG PIP_DEFAULT_TIMEOUT=300

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    build-essential \
    gcc \
    python3-dev \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY algorithm/requirements.txt /app/algorithm/requirements.txt
RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" --timeout "${PIP_DEFAULT_TIMEOUT}" 'lazyllm[rag]==0.7.6a0'
RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" --timeout "${PIP_DEFAULT_TIMEOUT}" -r /app/algorithm/requirements.txt

COPY algorithm /app/algorithm
COPY backend/core/doc /app/backend/core/doc

ENV PYTHONPATH=/app/algorithm/lazyllm:/app/algorithm:/app

CMD ["python", "backend/core/doc/doc_server.py"]
