#!/usr/bin/env bash
# 从 core（及 auth-service）代码中静态解析 API 权限，并在服务启动后导出最新 OpenAPI 文件。
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT/backend"
python3 scripts/extract_api_permissions.py
echo "API 权限已同步；启动 core/auth-service 后会自动导出最新 openapi 文件到 api/backend/*"
