# Stage: base - lazyllm[rag] only. Rebuilt only when upgrading lazyllm version.
FROM python:3.11-slim AS base
WORKDIR /app

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    build-essential \
    gcc \
    python3-dev \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir 'lazyllm[rag]==0.7.6a0'

# Stage: default - base + requirements.txt + code. Rebuilt when requirements.txt or code changes.
# Submodule lazyllm is copied via COPY . . and its parent dir is prepended to PYTHONPATH so
# "import lazyllm" resolves to /app/lazyllm/lazyllm/ (submodule) instead of pip-installed lazyllm.
FROM base AS default
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app/lazyllm:/app
CMD ["python", "parsing/parsing.py"]

# Stage: mineru - base + requirements.txt + mineru + code.
# Submodule lazyllm is copied via COPY . . and its parent dir is prepended to PYTHONPATH so
# "import lazyllm" resolves to /app/lazyllm/lazyllm/ (submodule) instead of pip-installed lazyllm.
FROM base AS mineru
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir 'mineru[all]==2.7.1' -i https://mirrors.aliyun.com/pypi/simple/
COPY . .
ENV PYTHONPATH=/app/lazyllm:/app
CMD ["python", "parsing/mineru.py"]
