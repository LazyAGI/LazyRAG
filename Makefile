# Code style: Python (flake8) + Go (gofmt). Mirrors algorithm/lazyllm Makefile pattern.
.PHONY: help lint install-flake8 lint-python lint-go test build up up-build down clear
.DEFAULT_GOAL := help

# Use legacy Docker builder by default to avoid pulling moby/buildkit:buildx-stable-1 from Docker Hub
# (which often times out in restricted networks). Override with: make up DOCKER_BUILDKIT=1
export DOCKER_BUILDKIT ?= 0
PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

# ---------------------------------------------------------------------------
# Compose project (optional). Pass -p only when COMPOSE_PROJECT is set.
# Usage: make up                           →  docker compose up -d
#        make up COMPOSE_PROJECT=myproj    →  docker compose -p myproj up -d
#        make down                         →  docker compose down
#        make down COMPOSE_PROJECT=myproj  →  docker compose -p myproj down
# ---------------------------------------------------------------------------
_COMPOSE := DOCKER_BUILDKIT=$(DOCKER_BUILDKIT) docker compose $(if $(COMPOSE_PROJECT),-p $(COMPOSE_PROJECT),)
ifneq (,$(wildcard .env))
include .env
export $(shell sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1/p' .env)
endif

# ---------------------------------------------------------------------------
# Environment variables (override via: make up LAZYRAG_OCR_SERVER_TYPE=mineru)
# ---------------------------------------------------------------------------
# Auth
LAZYRAG_DATABASE_URL ?= postgresql+psycopg://app:app@db:5432/app
LAZYRAG_JWT_SECRET ?= dev-secret-change-me
LAZYRAG_JWT_TTL_MINUTES ?= 60
LAZYRAG_JWT_REFRESH_TTL_DAYS ?= 7
LAZYRAG_BOOTSTRAP_ADMIN_USERNAME ?= admin
LAZYRAG_BOOTSTRAP_ADMIN_PASSWORD ?= admin
LAZYRAG_AUTH_API_PERMISSIONS_FILE ?=

# Core / ACL
ACL_DB_DRIVER ?= postgres
ACL_DB_DSN ?= host=db user=app password=app dbname=app port=5432 sslmode=disable TimeZone=UTC
# For docker-compose, core reaches chat via service DNS name.
LAZYRAG_CHAT_SERVICE_URL ?= http://chat:8046

# Processor
LAZYRAG_DOCUMENT_PROCESSOR_PORT ?= 8000
LAZYRAG_DOCUMENT_WORKER_PORT ?= 8001
LAZYRAG_DOCUMENT_WORKER_NUM_WORKERS ?= 1
LAZYRAG_DOCUMENT_WORKER_LEASE_DURATION ?= 300
LAZYRAG_DOCUMENT_WORKER_LEASE_RENEW_INTERVAL ?= 60
LAZYRAG_DOCUMENT_WORKER_HIGH_PRIORITY_TASK_TYPES ?=
LAZYRAG_DOCUMENT_WORKER_HIGH_PRIORITY_ONLY ?= false
LAZYRAG_DOCUMENT_WORKER_POLL_MODE ?= direct

# Parsing / OCR (none=built-in PDFReader, mineru, paddleocr)
LAZYRAG_DOCUMENT_PROCESSOR_URL ?= http://processor-server:8000
LAZYRAG_DOCUMENT_SERVICE_URL ?= http://lazyllm-doc-server:8000
LAZYRAG_PARSING_SERVICE_URL ?= http://lazyllm-parse-server:8000
LAZYRAG_DOCUMENT_SERVER_PORT ?= 8000
LAZYRAG_OCR_SERVER_TYPE ?= none
LAZYRAG_MODEL_CONFIG_PATH ?=
# Auto-derive URL from type when not set: mineru->http://mineru:8000, paddleocr->http://paddleocr:8080, none->placeholder
LAZYRAG_OCR_SERVER_URL ?= $(if $(filter mineru,$(LAZYRAG_OCR_SERVER_TYPE)),http://mineru:8000,$(if $(filter paddleocr,$(LAZYRAG_OCR_SERVER_TYPE)),http://paddleocr:8080,http://localhost:8000))
LAZYRAG_MINERU_UPLOAD_MODE ?=

# Vector / segment stores (required when using Processor/Worker). Default URIs use built-in services.
# If user provides external URIs, milvus/opensearch are not deployed.
LAZYRAG_MILVUS_URI ?= http://milvus:19530
LAZYRAG_OPENSEARCH_URI ?= https://opensearch:9200
LAZYRAG_OPENSEARCH_USER ?= admin
LAZYRAG_OPENSEARCH_PASSWORD ?= LazyRAG_OpenSearch123!
LAZYRAG_ENABLE_STORE_DASHBOARDS ?= 0
LAZYRAG_ENABLE_MILVUS_DASHBOARD ?= $(LAZYRAG_ENABLE_STORE_DASHBOARDS)
LAZYRAG_ENABLE_OPENSEARCH_DASHBOARD ?= $(LAZYRAG_ENABLE_STORE_DASHBOARDS)

# MinerU
LAZYRAG_MINERU_SERVER_PORT ?= 8000
LAZYRAG_MINERU_VERSION ?= 2.7.1
LAZYRAG_MINERU_PACKAGE_VARIANT ?= pipeline
LAZYRAG_MINERU_PREINSTALL_CPU_TORCH ?= 1
LAZYRAG_MINERU_TORCH_VERSION ?= 2.11.0
LAZYRAG_MINERU_TORCHVISION_VERSION ?= 0.26.0
LAZYRAG_MINERU_NUMPY_VERSION ?= 1.26.4
LAZYRAG_MINERU_PYTORCH_INDEX_URL ?= https://download.pytorch.org/whl/cpu
LAZYRAG_MINERU_PYPI_INDEX_URL ?= https://mirrors.aliyun.com/pypi/simple/
LAZYRAG_MINERU_BACKEND ?= pipeline
LAZYRAG_MINERU_CACHE_DIR ?= /app/.mineru-cache
LAZYRAG_MINERU_IMAGE_SAVE_DIR ?= /app/.mineru-images

# Chat
LAZYRAG_DOCUMENT_SERVER_URL ?= http://parsing:8000
LAZYRAG_MAX_CONCURRENCY ?= 10
LAZYRAG_LLM_PRIORITY ?= 0
LAZYRAG_CHAT_PROMPT ?=

# PaddleOCR (when LAZYRAG_OCR_SERVER_TYPE=paddleocr)
PADDLEOCR_VLM_IMAGE_TAG ?= latest-nvidia-gpu
PADDLEOCR_API_IMAGE_TAG ?= latest-nvidia-gpu
PADDLEOCR_VLM_BACKEND ?= vllm

# Milvus / OpenSearch (when using built-in profiles)
MILVUS_IMAGE_TAG ?= v2.6.11
OPENSEARCH_IMAGE_TAG ?= 2.18.0
ATTU_IMAGE_TAG ?= v2.6.3
MINIO_ACCESS_KEY ?= minioadmin
MINIO_SECRET_KEY ?= minioadmin

# JuiceFS S3 Gateway
JUICEFS_MINIO_USER ?= minioadmin
JUICEFS_MINIO_PASSWORD ?= minioadmin
JUICEFS_ACCESS_KEY ?= juicefs
JUICEFS_SECRET_KEY ?= juicefs123

export LAZYRAG_DATABASE_URL LAZYRAG_JWT_SECRET LAZYRAG_JWT_TTL_MINUTES LAZYRAG_JWT_REFRESH_TTL_DAYS
export LAZYRAG_BOOTSTRAP_ADMIN_USERNAME LAZYRAG_BOOTSTRAP_ADMIN_PASSWORD LAZYRAG_AUTH_API_PERMISSIONS_FILE
export ACL_DB_DRIVER ACL_DB_DSN LAZYRAG_CHAT_SERVICE_URL
export LAZYRAG_DOCUMENT_PROCESSOR_PORT LAZYRAG_DOCUMENT_WORKER_PORT LAZYRAG_DOCUMENT_WORKER_NUM_WORKERS
export LAZYRAG_DOCUMENT_WORKER_LEASE_DURATION LAZYRAG_DOCUMENT_WORKER_LEASE_RENEW_INTERVAL
export LAZYRAG_DOCUMENT_WORKER_HIGH_PRIORITY_TASK_TYPES LAZYRAG_DOCUMENT_WORKER_HIGH_PRIORITY_ONLY
export LAZYRAG_DOCUMENT_WORKER_POLL_MODE
export LAZYRAG_DOCUMENT_PROCESSOR_URL LAZYRAG_DOCUMENT_SERVICE_URL LAZYRAG_PARSING_SERVICE_URL
export LAZYRAG_DOCUMENT_SERVER_PORT LAZYRAG_OCR_SERVER_TYPE LAZYRAG_MODEL_CONFIG_PATH LAZYRAG_OCR_SERVER_URL
export LAZYRAG_MINERU_UPLOAD_MODE
export LAZYRAG_MILVUS_URI LAZYRAG_OPENSEARCH_URI LAZYRAG_OPENSEARCH_USER LAZYRAG_OPENSEARCH_PASSWORD
export LAZYRAG_ENABLE_STORE_DASHBOARDS LAZYRAG_ENABLE_MILVUS_DASHBOARD LAZYRAG_ENABLE_OPENSEARCH_DASHBOARD
export LAZYRAG_MINERU_SERVER_PORT LAZYRAG_MINERU_VERSION LAZYRAG_MINERU_PACKAGE_VARIANT
export LAZYRAG_MINERU_PREINSTALL_CPU_TORCH LAZYRAG_MINERU_TORCH_VERSION LAZYRAG_MINERU_TORCHVISION_VERSION
export LAZYRAG_MINERU_NUMPY_VERSION
export LAZYRAG_MINERU_PYTORCH_INDEX_URL LAZYRAG_MINERU_PYPI_INDEX_URL LAZYRAG_MINERU_BACKEND
export LAZYRAG_MINERU_CACHE_DIR LAZYRAG_MINERU_IMAGE_SAVE_DIR
export LAZYRAG_DOCUMENT_SERVER_URL LAZYRAG_MAX_CONCURRENCY LAZYRAG_LLM_PRIORITY LAZYRAG_CHAT_PROMPT
export PADDLEOCR_VLM_IMAGE_TAG PADDLEOCR_API_IMAGE_TAG PADDLEOCR_VLM_BACKEND
export MILVUS_IMAGE_TAG OPENSEARCH_IMAGE_TAG ATTU_IMAGE_TAG MINIO_ACCESS_KEY MINIO_SECRET_KEY
export JUICEFS_MINIO_USER JUICEFS_MINIO_PASSWORD JUICEFS_ACCESS_KEY JUICEFS_SECRET_KEY

# Python dirs to lint (exclude submodule algorithm/lazyllm via .flake8)
PYTHON_DIRS := algorithm backend evo

# Go dirs to lint
GO_DIRS := backend/core

help:
	@echo "LazyRAG Make targets:"
	@echo "  make up         - Start services in background (with derived profiles)"
	@echo "  make up-build   - Build images and start services"
	@echo "  make down       - Stop services"
	@echo "  make build      - Build compose services (mineru profile only when needed)"
	@echo "                    Use LAZYRAG_ENABLE_STORE_DASHBOARDS=1 to add Attu/OpenSearch Dashboards for built-in stores"
	@echo "  make lint       - Run Python flake8 and Go gofmt checks"
	@echo "  make test       - Run project test script"
	@echo "  make clear      - Stop services, remove volumes, clear Python cache"

# Require flake8 to be installed (e.g. in a venv). Do not auto pip-install to avoid PEP 668 errors.
install-flake8:
	@for pkg in flake8 flake8-quotes flake8-bugbear; do \
		case $$pkg in \
			flake8) mod="flake8" ;; \
			flake8-quotes) mod="flake8_quotes" ;; \
			flake8-bugbear) mod="bugbear" ;; \
		esac; \
		$(PYTHON) -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$$mod') else 1)" \
			|| $(PIP) install $$pkg; \
	done

lint-python: install-flake8
	@echo "🐍 Linting Python ($(PYTHON_DIRS))..."
	@$(PYTHON) -m flake8 $(PYTHON_DIRS)

lint-go:
	@echo "🔷 Linting Go ($(GO_DIRS))..."
	@FMT=$$(gofmt -l -s $(GO_DIRS) 2>/dev/null); \
	if [ -n "$$FMT" ]; then \
		echo "❌ Go files not formatted (run: gofmt -w -s $(GO_DIRS)):"; \
		echo "$$FMT"; \
		exit 1; \
	fi
	@echo "✅ Go fmt OK."

lint: lint-python lint-go

test:
	@./tests/run-all.sh

# Only build/start mineru/paddleocr when LAZYRAG_OCR_SERVER_TYPE is mineru/paddleocr
# AND LAZYRAG_OCR_SERVER_URL points to the internal service (user has not specified external URL).
# Only mineru has build:; paddleocr/milvus/opensearch use image: only, so only needed for up.
_need_mineru := $(and $(filter mineru,$(LAZYRAG_OCR_SERVER_TYPE)),$(findstring mineru:8000,$(LAZYRAG_OCR_SERVER_URL)))
_need_paddleocr := $(and $(filter paddleocr,$(LAZYRAG_OCR_SERVER_TYPE)),$(findstring paddleocr:8080,$(LAZYRAG_OCR_SERVER_URL)))
# Deploy milvus/opensearch only when URI exactly matches the built-in services; external URIs = no deployment
_builtin_milvus_uris := http://milvus:19530 http://milvus:19530/
_builtin_opensearch_uris := https://opensearch:9200 https://opensearch:9200/
_need_milvus := $(filter $(strip $(LAZYRAG_MILVUS_URI)),$(_builtin_milvus_uris))
_need_opensearch := $(filter $(strip $(LAZYRAG_OPENSEARCH_URI)),$(_builtin_opensearch_uris))
_enable_milvus_dashboard := $(filter 1 true TRUE yes YES on ON,$(LAZYRAG_ENABLE_MILVUS_DASHBOARD))
_enable_opensearch_dashboard := $(filter 1 true TRUE yes YES on ON,$(LAZYRAG_ENABLE_OPENSEARCH_DASHBOARD))
_need_milvus_dashboard := $(and $(_need_milvus),$(_enable_milvus_dashboard))
_need_opensearch_dashboard := $(and $(_need_opensearch),$(_enable_opensearch_dashboard))

# Shared compose profile flags for up/down/up-build
_COMPOSE_PROFILES := $(strip $(if $(_need_mineru),--profile mineru) $(if $(_need_paddleocr),--profile paddleocr) $(if $(_need_milvus),--profile milvus) $(if $(_need_opensearch),--profile opensearch) $(if $(_need_milvus_dashboard),--profile milvus-dashboard) $(if $(_need_opensearch_dashboard),--profile opensearch-dashboard))

# Only init submodules when not yet cloned; if already present (even with different commit), do nothing. Never recursive.
_SUBMODULE_INIT = @git submodule status | grep -q '^-' && git submodule update --init || true

build:
	$(_SUBMODULE_INIT)
	@$(_COMPOSE) $(strip $(if $(_need_mineru),--profile mineru)) build

up:
	@$(_COMPOSE) $(_COMPOSE_PROFILES) up -d

down:
	@$(_COMPOSE) $(_COMPOSE_PROFILES) down

up-build:
	$(_SUBMODULE_INIT)
	@$(_COMPOSE) $(_COMPOSE_PROFILES) up --build -d

clear:
	@echo "🧹 Stopping containers and removing volumes (keeping built images/base cache)..."
	@$(_COMPOSE) $(_COMPOSE_PROFILES) down -v 2>/dev/null || true
	@echo "🧹 Clearing Python cache..."
	@find . -type d -name '__pycache__' ! -path '*/\.git/*' -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name '*.pyc' ! -path '*/\.git/*' -delete 2>/dev/null || true
	@echo "✅ Clear done."
