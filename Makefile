# Code style: Python (flake8) + Go (gofmt). Mirrors algorithm/lazyllm Makefile pattern.
.PHONY: lint lint-only-diff install-flake8 lint-python lint-python-only-diff lint-go lint-go-only-diff

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
