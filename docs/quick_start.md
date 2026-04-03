# Quick Start

这份文档只包含两件事：

- 如何配置环境变量
- 如何启动服务

所有命令都默认在仓库根目录执行。

## 前置条件

- 已安装 Docker / Docker Compose
- 已在仓库根目录
- 如需使用线上 API 模型，提前准备好对应 API key
- 如需使用内网模型，确保当前机器能访问对应内网服务

## 环境变量

### 1. 线上 API 模型

使用 [`algorithm/configs/runtime_models.yaml`](algorithm/configs/runtime_models.yaml)：

```bash
export LAZYLLM_SILICONFLOW_API_KEY=你的key
export LAZYRAG_MODEL_CONFIG_PATH=/app/configs/runtime_models.yaml
```

这里的环境变量名必须和 yaml 里使用的占位符一致。例如 yaml 中写的是 `${LAZYLLM_SILICONFLOW_API_KEY}`，那就必须 export `LAZYLLM_SILICONFLOW_API_KEY`。
如果一份 yaml 同时引用多个 provider 的 key，也可以同时 export 多个环境变量。`docker-compose.yml` 已经透传常见的在线模型环境变量。

### 2. 内网已部署模型

有两种方式。

方式 A：继续使用默认 `auto_model.yaml`

```bash
unset LAZYRAG_MODEL_CONFIG_PATH
```

这会走镜像内默认的 [`algorithm/configs/auto_model.yaml`](algorithm/configs/auto_model.yaml)。

方式 B：显式使用新的 runtime 配置

```bash
export LAZYRAG_MODEL_CONFIG_PATH=/app/configs/runtime_models.inner.yaml
```

对应配置文件是 [`algorithm/configs/runtime_models.inner.yaml`](algorithm/configs/runtime_models.inner.yaml)。

### 3. OCR 相关

默认不启用 OCR 服务：

```bash
export LAZYRAG_OCR_SERVER_TYPE=none
```

如果要启用本地 MinerU：

```bash
export LAZYRAG_OCR_SERVER_TYPE=mineru
export LAZYRAG_OCR_SERVER_URL=http://mineru:8000
export LAZYRAG_MINERU_BACKEND=pipeline
export LAZYRAG_MINERU_UPLOAD_MODE=true
```

如果要复用 ECS / 内网已经部署好的 MinerU：

```bash
export LAZYRAG_OCR_SERVER_TYPE=mineru
export LAZYRAG_OCR_SERVER_URL=http://your-inner-mineru:port
export LAZYRAG_MINERU_UPLOAD_MODE=true
```

`http://mineru:8000` 表示使用当前 `docker compose` 启动的本地 MinerU。
如果 `LAZYRAG_OCR_SERVER_URL` 指向外部地址，服务会复用外部 MinerU，`make up-build` 也不会自动启动本地 `mineru` profile。

如果使用外部 Milvus / OpenSearch，也在启动前 export 对应变量：

```bash
export LAZYRAG_MILVUS_URI=http://your-milvus:19530
export LAZYRAG_OPENSEARCH_URI=https://your-opensearch:9200
export LAZYRAG_OPENSEARCH_USER=admin
export LAZYRAG_OPENSEARCH_PASSWORD=your-password
```

## 启动服务

### 1. 默认启动

```bash
make up-build
```

### 2. 使用线上 API 模型启动

```bash
export LAZYLLM_SILICONFLOW_API_KEY=你的key
export LAZYRAG_MODEL_CONFIG_PATH=/app/configs/runtime_models.yaml
export LAZYRAG_OCR_SERVER_TYPE=none

make up-build
```

### 3. 使用内网旧模型启动

```bash
unset LAZYRAG_MODEL_CONFIG_PATH
export LAZYRAG_OCR_SERVER_TYPE=none

make up-build
```

### 4. 使用内网 runtime 配置启动

```bash
export LAZYRAG_MODEL_CONFIG_PATH=/app/configs/runtime_models.inner.yaml
export LAZYRAG_OCR_SERVER_TYPE=none

make up-build
```

### 5. 启用 MinerU 启动

```bash
export LAZYRAG_MODEL_CONFIG_PATH=/app/configs/runtime_models.inner.yaml
export LAZYRAG_OCR_SERVER_TYPE=mineru
export LAZYRAG_OCR_SERVER_URL=http://mineru:8000
export LAZYRAG_MINERU_BACKEND=pipeline
export LAZYRAG_MINERU_UPLOAD_MODE=true

make up-build
```

## 常用运维命令

只重启容器，不重新 build：

```bash
docker compose up -d --force-recreate
```

停止服务：

```bash
make down
```

清理容器和卷后重新启动：

```bash
make clear
make up-build
```

查看服务状态：

```bash
docker compose ps
```

查看日志：

```bash
docker compose logs --tail=200
```

## 完整启动示例

### 1. 线上 API 模型

```bash
export LAZYLLM_SILICONFLOW_API_KEY=你的key
export LAZYRAG_MODEL_CONFIG_PATH=/app/configs/runtime_models.yaml
export LAZYRAG_OCR_SERVER_TYPE=none

make up-build
```

如果 yaml 里同时引用了多个 provider 的 key，就把对应环境变量一并 export，变量名要和 yaml 中的占位符保持一致。

### 2. 内网已部署模型

使用新的内网 runtime 配置 + 本地 MinerU：

```bash
export LAZYRAG_MODEL_CONFIG_PATH=/app/configs/runtime_models.inner.yaml
export LAZYRAG_OCR_SERVER_TYPE=mineru
export LAZYRAG_OCR_SERVER_URL=http://mineru:8000
export LAZYRAG_MINERU_BACKEND=pipeline
export LAZYRAG_MINERU_UPLOAD_MODE=true

make up-build
```

如果要复用 ECS / 内网已经部署好的 MinerU：

```bash
export LAZYRAG_MODEL_CONFIG_PATH=/app/configs/runtime_models.inner.yaml
export LAZYRAG_OCR_SERVER_TYPE=mineru
export LAZYRAG_OCR_SERVER_URL=http://your-inner-mineru:port
export LAZYRAG_MINERU_UPLOAD_MODE=true

make up-build
```

如果想继续走旧的 `auto_model.yaml` 路径：

```bash
unset LAZYRAG_MODEL_CONFIG_PATH
export LAZYRAG_OCR_SERVER_TYPE=none

make up-build
```
