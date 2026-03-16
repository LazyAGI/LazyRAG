# OpenAPI 接口自动生成

## 概述

本项目使用 OpenAPI Generator 自动生成前端 API 客户端代码。

## 配置说明

### 1. OpenAPI 规范文件

本地维护的 OpenAPI 规范文件位于：
```
scripts/openapi/specs/auth-openapi.yaml
scripts/openapi/specs/core.yaml
```

### 2. 生成的接口位置

生成的 TypeScript 接口代码位于：
```
src/api/generated/auth-client/
src/api/generated/core-client/
```

## 使用方法

### 自动生成（推荐）

当您运行 `npm run dev` 时，会自动执行接口生成：

```bash
npm run dev
```

这个命令会：
1. 自动生成 `auth` 和 `core` 接口（通过 `predev` 钩子）
2. 启动开发服务器

### 手动生成

如果需要手动生成接口，可以使用以下命令：

```bash
# 只生成 auth 接口
npm run gen:auth

# 使用通用命令生成指定服务
npm run gen:openapi auth
npm run gen:openapi core

# 生成所有配置的接口
npm run gen:openapi
```

## 环境要求

- **Java 17+**: OpenAPI Generator 需要 Java 运行时
  - macOS: 已通过 Homebrew 安装 `openjdk@17`
  - 路径: `/opt/homebrew/opt/openjdk@17/bin/java`

## 添加新的 OpenAPI 规范

1. 将新的 OpenAPI YAML 文件放到 `scripts/openapi/specs/` 目录
2. 修改 `scripts/openapi/generate-api.mjs`，添加新的 API 配置：

```javascript
const apis = [
  {
    name: "your-service",
    input: path.resolve(localSpecsDir, "your-service-openapi.yaml"),
    output: path.resolve(outputDirname, "your-service-client"),
  },
  // ... 其他配置
];
```

3. 生成接口：

```bash
npm run gen:openapi your-service
```

## 配置文件

- `scripts/openapi/generate-api.mjs`: 主生成脚本
- `scripts/openapi/generate-auth.sh`: Auth 服务生成脚本（带 Java 环境配置）
- `scripts/openapi/openapi-generator-config.json`: OpenAPI Generator 配置
- `scripts/openapi/.openapi-cache.json`: 缓存文件（避免重复生成）

## 缓存机制

生成脚本使用 SHA256 哈希来检测 OpenAPI 文件的变化。只有当文件内容改变时才会重新生成接口。

如果需要强制重新生成，可以：

```bash
# 使用 --skip-cache 标志
node scripts/openapi/generate-api.mjs auth --skip-cache
```

## 故障排查

### Java 未找到错误

如果遇到 "Unable to locate a Java Runtime" 错误：

1. 确认 Java 已安装：
```bash
/opt/homebrew/opt/openjdk@17/bin/java -version
```

2. 如果未安装，使用 Homebrew 安装：
```bash
brew install openjdk@17
```

3. 设置环境变量（已在生成脚本中配置）：
```bash
export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"
```

### 生成失败

如果生成失败，请检查：
1. OpenAPI YAML 文件格式是否正确
2. Java 环境是否配置正确
3. 网络连接是否正常（首次运行需要下载 OpenAPI Generator）

## 技术栈

- **OpenAPI Generator CLI**: v2.20.2+
- **生成器**: typescript-axios
- **Axios 版本**: 1.6.8
