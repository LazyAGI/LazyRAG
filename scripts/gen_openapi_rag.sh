#!/usr/bin/env bash
# 从 core（及 auth-service）代码中静态解析 API 权限，写入 api_permissions.json，供 Kong RBAC 鉴权使用。
# OpenAPI 规范维护在 api/backend/core/openapi.yml（可手写或由 proto 生成）。
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT/backend"
python3 scripts/extract_api_permissions.py
echo "OpenAPI 定义见: api/backend/core/openapi.yml"
