# Code style: Python (flake8) + Go (gofmt). Mirrors algorithm/lazyllm Makefile pattern.
.PHONY: help lint install-flake8 lint-python lint-go test build up up-build down clear
.DEFAULT_GOAL := help

# Use legacy Docker builder by default to avoid pulling moby/buildkit:buildx-stable-1 from Docker Hub
# (which often times out in restricted networks). Override with: make up DOCKER_BUILDKIT=1
export DOCKER_BUILDKIT ?= 1
PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
comma := ,

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
# Environment variables (override via: make up VAR=value, or set in .env)
# Only variables that users are likely to change are listed here.
# Internal service URLs, version pins, and fixed paths are hardcoded in docker-compose.yml.
# ---------------------------------------------------------------------------

# Auth — credentials and secrets (change in production)
LAZYRAG_DATABASE_URL ?= postgresql+psycopg://app:app@db:5432/app
LAZYRAG_JWT_SECRET ?= dev-secret-change-me
LAZYRAG_BOOTSTRAP_ADMIN_USERNAME ?= admin
LAZYRAG_BOOTSTRAP_ADMIN_PASSWORD ?= admin
LAZYRAG_RESET_ALGO_ON_STARTUP ?= false

# Core database
LAZYRAG_CORE_DATABASE_URL ?= postgresql+psycopg://root:123456@db:5432/core

# OCR backend selection (none=built-in PDFReader, mineru, paddleocr)
# Auto-derives LAZYRAG_OCR_SERVER_URL when not set.
LAZYRAG_OCR_SERVER_TYPE ?= none
LAZYRAG_OCR_SERVER_URL ?= $(if $(filter mineru,$(LAZYRAG_OCR_SERVER_TYPE)),http://mineru:8000,$(if $(filter paddleocr,$(LAZYRAG_OCR_SERVER_TYPE)),http://paddleocr:8080,http://localhost:8000))

# Vector / segment stores — override to use external services (skips built-in profile)
LAZYRAG_MILVUS_URI ?= http://milvus:19530
LAZYRAG_OPENSEARCH_URI ?= https://opensearch:9200
LAZYRAG_OPENSEARCH_USER ?= admin
LAZYRAG_OPENSEARCH_PASSWORD ?= LazyRAG_OpenSearch123!

# Dashboard toggles (set to 1 to enable Attu / OpenSearch Dashboards)
LAZYRAG_ENABLE_STORE_DASHBOARDS ?= 0
LAZYRAG_ENABLE_MILVUS_DASHBOARD ?= $(LAZYRAG_ENABLE_STORE_DASHBOARDS)
LAZYRAG_ENABLE_OPENSEARCH_DASHBOARD ?= $(LAZYRAG_ENABLE_STORE_DASHBOARDS)

# Chat tuning
LAZYRAG_MAX_CONCURRENCY ?= 10
LAZYRAG_LLM_PRIORITY ?= 0

# Tracing (set LAZYLLM_TRACE_ENABLED=0 to disable; requires LANGFUSE_* keys when enabled)
LAZYLLM_TRACE_ENABLED ?= 1
LAZYLLM_TRACE_BACKEND ?= langfuse

# MinIO credentials (used by built-in Milvus profile)
MINIO_ACCESS_KEY ?= minioadmin
MINIO_SECRET_KEY ?= minioadmin

# pip timeout
PIP_DEFAULT_TIMEOUT ?= 2400
PIP_RETRIES ?= 10

# model config path
LAZYRAG_MODEL_CONFIG_PATH ?= online

export LAZYRAG_DATABASE_URL LAZYRAG_JWT_SECRET
export LAZYRAG_BOOTSTRAP_ADMIN_USERNAME LAZYRAG_BOOTSTRAP_ADMIN_PASSWORD
export LAZYRAG_CORE_DATABASE_URL
export LAZYRAG_OCR_SERVER_TYPE LAZYRAG_OCR_SERVER_URL
export LAZYRAG_MILVUS_URI LAZYRAG_OPENSEARCH_URI LAZYRAG_OPENSEARCH_USER LAZYRAG_OPENSEARCH_PASSWORD
export LAZYRAG_ENABLE_STORE_DASHBOARDS LAZYRAG_ENABLE_MILVUS_DASHBOARD LAZYRAG_ENABLE_OPENSEARCH_DASHBOARD
export LAZYRAG_MAX_CONCURRENCY LAZYRAG_LLM_PRIORITY
export LAZYLLM_TRACE_ENABLED LAZYLLM_TRACE_BACKEND
export MINIO_ACCESS_KEY MINIO_SECRET_KEY
export PIP_DEFAULT_TIMEOUT PIP_RETRIES
export LAZYRAG_MODEL_CONFIG_PATH
export LAZYRAG_RESET_ALGO_ON_STARTUP

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
	@$(_COMPOSE) $(strip $(if $(_need_mineru),--profile mineru)) build \
		$(if $(SERVICES),$(subst $(comma), ,$(SERVICES)),)

up:
	$(_SUBMODULE_INIT)
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
