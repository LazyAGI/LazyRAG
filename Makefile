# Code style: Python (flake8) + Go (gofmt). Mirrors algorithm/lazyllm Makefile pattern.
.PHONY: lint lint-only-diff install-flake8 lint-python lint-python-only-diff lint-go lint-go-only-diff test build up up-build

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
LAZYRAG_CHAT_SERVICE_URL ?= http://localhost:8046

# Processor
LAZYRAG_DOCUMENT_PROCESSOR_PORT ?= 8000
LAZYRAG_DOCUMENT_WORKER_PORT ?= 8001
LAZYRAG_DOC_TASK_DATABASE_URL ?= postgresql+psycopg://app:app@db:5432/app

# Parsing / OCR (none=built-in PDFReader, mineru, paddleocr)
LAZYRAG_DOCUMENT_PROCESSOR_URL ?= http://processor-server:8000
LAZYRAG_DOCUMENT_SERVER_PORT ?= 8000
LAZYRAG_OCR_SERVER_TYPE ?= none
# Auto-derive URL from type when not set: mineru->http://mineru:8000, paddleocr->http://paddleocr:8080
LAZYRAG_OCR_SERVER_URL ?= $(if $(filter mineru,$(LAZYRAG_OCR_SERVER_TYPE)),http://mineru:8000,$(if $(filter paddleocr,$(LAZYRAG_OCR_SERVER_TYPE)),http://paddleocr:8080,))

# Vector / segment stores (required when using Processor/Worker). Default URIs use built-in services.
# If user provides external URIs, milvus/opensearch are not deployed.
LAZYRAG_MILVUS_URI ?= http://milvus:19530
LAZYRAG_OPENSEARCH_URI ?= https://opensearch:9200
LAZYRAG_OPENSEARCH_USER ?= admin
LAZYRAG_OPENSEARCH_PASSWORD ?= LazyRAG_OpenSearch123!

# MinerU
LAZYRAG_MINERU_SERVER_PORT ?= 8000

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

export LAZYRAG_DATABASE_URL LAZYRAG_JWT_SECRET LAZYRAG_JWT_TTL_MINUTES LAZYRAG_JWT_REFRESH_TTL_DAYS
export LAZYRAG_BOOTSTRAP_ADMIN_USERNAME LAZYRAG_BOOTSTRAP_ADMIN_PASSWORD LAZYRAG_AUTH_API_PERMISSIONS_FILE
export ACL_DB_DRIVER ACL_DB_DSN LAZYRAG_CHAT_SERVICE_URL
export LAZYRAG_DOCUMENT_PROCESSOR_PORT LAZYRAG_DOCUMENT_WORKER_PORT LAZYRAG_DOC_TASK_DATABASE_URL
export LAZYRAG_DOCUMENT_PROCESSOR_URL LAZYRAG_DOCUMENT_SERVER_PORT LAZYRAG_OCR_SERVER_TYPE LAZYRAG_OCR_SERVER_URL
export LAZYRAG_MILVUS_URI LAZYRAG_OPENSEARCH_URI LAZYRAG_OPENSEARCH_USER LAZYRAG_OPENSEARCH_PASSWORD
export LAZYRAG_MINERU_SERVER_PORT LAZYRAG_DOCUMENT_SERVER_URL LAZYRAG_MAX_CONCURRENCY LAZYRAG_LLM_PRIORITY LAZYRAG_CHAT_PROMPT
export PADDLEOCR_VLM_IMAGE_TAG PADDLEOCR_API_IMAGE_TAG PADDLEOCR_VLM_BACKEND
export MILVUS_IMAGE_TAG OPENSEARCH_IMAGE_TAG

# Python dirs to lint (exclude submodule algorithm/lazyllm via .flake8)
PYTHON_DIRS := algorithm backend

# Go dirs to lint
GO_DIRS := backend/core

install-flake8:
	@python3 -c "import flake8" 2>/dev/null || pip3 install flake8
	@for pkg in flake8-quotes flake8-bugbear; do \
		case $$pkg in \
			flake8-quotes) mod="flake8_quotes" ;; \
			flake8-bugbear) mod="bugbear" ;; \
		esac; \
		python3 -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('$$mod') else 1)" \
			|| pip3 install $$pkg; \
	done

lint-python: install-flake8
	@echo "🐍 Linting Python ($(PYTHON_DIRS))..."
	@python3 -m flake8 $(PYTHON_DIRS)

.ONESHELL:
lint-python-only-diff:
	@set -e
	@$(MAKE) -s install-flake8
	@if [ -n "$(CHANGED_PY_FILES)" ]; then \
		echo "$(CHANGED_PY_FILES)" | xargs python3 -m flake8; \
		exit 0; \
	fi
	@echo "🔍 Collecting changed Python files..."
	@FILES=$$( \
		{ \
			git diff --name-only origin/main..HEAD 2>/dev/null || true; \
			git diff --cached --name-only 2>/dev/null || true; \
			git diff --name-only 2>/dev/null || true; \
		} | sort -u | while read f; do \
			case "$$f" in \
				*.py) \
					case "$$f" in algorithm/lazyllm/*) ;; *) [ -f "$$f" ] && echo "$$f";; esac;; \
			esac; \
		done \
	); \
	if [ -n "$$FILES" ]; then \
		echo "➡️  Running flake8 on:"; \
		echo "$$FILES"; \
		echo "$$FILES" | xargs python3 -m flake8; \
	else \
		echo "✅ No Python file changes to lint."; \
	fi

lint-go:
	@echo "🔷 Linting Go ($(GO_DIRS))..."
	@FMT=$$(gofmt -l -s $(GO_DIRS) 2>/dev/null); \
	if [ -n "$$FMT" ]; then \
		echo "❌ Go files not formatted (run: gofmt -w -s $(GO_DIRS)):"; \
		echo "$$FMT"; \
		exit 1; \
	fi
	@echo "✅ Go fmt OK."

.ONESHELL:
lint-go-only-diff:
	@set -e
	@echo "🔍 Collecting changed Go files..."
	@FILES=$$( \
		{ \
			git diff --name-only origin/main..HEAD 2>/dev/null || true; \
			git diff --cached --name-only 2>/dev/null || true; \
			git diff --name-only 2>/dev/null || true; \
		} | sort -u | while read f; do \
			case "$$f" in backend/core/*.go) [ -f "$$f" ] && echo "$$f";; esac; \
		done \
	); \
	if [ -n "$$FILES" ]; then \
		FMT=$$(echo "$$FILES" | xargs gofmt -l -s 2>/dev/null); \
		if [ -n "$$FMT" ]; then \
			echo "❌ Go files not formatted (run: gofmt -w -s <files>):"; \
			echo "$$FMT"; \
			exit 1; \
		fi; \
		echo "✅ Go fmt OK for changed files."; \
	else \
		echo "✅ No Go file changes to lint."; \
	fi

lint: lint-python lint-go

lint-only-diff: lint-python-only-diff lint-go-only-diff

test:
	@./tests/run-all.sh

# Only build/start mineru/paddleocr when LAZYRAG_OCR_SERVER_TYPE is mineru/paddleocr
# AND LAZYRAG_OCR_SERVER_URL points to the internal service (user has not specified external URL).
# Only mineru has build:; paddleocr/milvus/opensearch use image: only, so only needed for up.
_need_mineru := $(and $(filter mineru,$(LAZYRAG_OCR_SERVER_TYPE)),$(findstring mineru:8000,$(LAZYRAG_OCR_SERVER_URL)))
_need_paddleocr := $(and $(filter paddleocr,$(LAZYRAG_OCR_SERVER_TYPE)),$(findstring paddleocr:8080,$(LAZYRAG_OCR_SERVER_URL)))
# Deploy milvus/opensearch only when URI points to built-in services; external URIs = no deployment
_need_milvus := $(findstring milvus:19530,$(LAZYRAG_MILVUS_URI))
_need_opensearch := $(findstring opensearch:9200,$(LAZYRAG_OPENSEARCH_URI))

# Shared compose profile flags for up/down/up-build
_COMPOSE_PROFILES := $(strip $(if $(_need_mineru),--profile mineru) $(if $(_need_paddleocr),--profile paddleocr) $(if $(_need_milvus),--profile milvus) $(if $(_need_opensearch),--profile opensearch))

build:
	@docker compose $(strip $(if $(_need_mineru),--profile mineru)) build

up:
	@docker compose $(_COMPOSE_PROFILES) up

down:
	@docker compose $(_COMPOSE_PROFILES) down

up-build:
	@docker compose $(_COMPOSE_PROFILES) up --build
