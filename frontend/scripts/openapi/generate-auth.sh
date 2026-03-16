#!/bin/bash

set -e

# 设置 Java 环境路径
export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"

# 执行本地 OpenAPI 生成命令
node scripts/openapi/generate-api.mjs auth
node scripts/openapi/generate-api.mjs core
