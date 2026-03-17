# JuiceFS S3 Gateway 集成指南

本文档说明 JuiceFS S3 Gateway 如何集成到 LazyRAG-back 项目中。

## ✅ 已完成的集成工作

### 1. 文件拷贝
- ✅ 已将 `tieyiyuan/neutrino/prod/appplatform/juicefs-s3-gateway` 目录完整拷贝到 `LazyRAG-back/backend/juicefs-s3-gateway`
- ✅ 包含所有必要文件: Dockerfile, Dockerfile.arm64, juicefs 源码, minio 源码

### 2. Docker Compose 配置
已在 `docker-compose.yml` 中添加以下服务:

#### `juicefs-minio`
- MinIO 对象存储后端,存储 JuiceFS 的数据块
- 端口: 9000 (API), 9002 (Console)
- 默认凭证: minioadmin/minioadmin

#### `juicefs-s3-gateway`
- JuiceFS S3 网关服务,提供 S3 兼容接口
- 端口: 9003
- 默认凭证: juicefs/juicefs123
- 元数据存储: Redis DB1 (redis://test:123456@redis:6379/1)
- 卷名称: lazyrag

### 3. Makefile 配置
已添加以下环境变量支持:
- `JUICEFS_MINIO_USER`: MinIO 用户名(默认: minioadmin)
- `JUICEFS_MINIO_PASSWORD`: MinIO 密码(默认: minioadmin)
- `JUICEFS_ACCESS_KEY`: JuiceFS S3 访问密钥(默认: juicefs)
- `JUICEFS_SECRET_KEY`: JuiceFS S3 密钥(默认: juicefs123)

### 4. 文档和测试
- ✅ 创建了详细的 `backend/juicefs-s3-gateway/README.md`
- ✅ 创建了测试脚本 `backend/juicefs-s3-gateway/test-juicefs.sh`

## 🚀 快速启动

### 方法一: 使用 Makefile (推荐)

```bash
cd /Users/wangbochao.vendor/Desktop/object/lazyRag_shift/LazyRAG-back

# 构建并启动所有服务
make up-build

# 等待服务启动完成(约 1-2 分钟)
docker compose ps

# 查看 JuiceFS 日志
docker compose logs -f juicefs-s3-gateway
```

### 方法二: 使用 Docker Compose 直接启动

```bash
cd /Users/wangbochao.vendor/Desktop/object/lazyRag_shift/LazyRAG-back

# 启动所有服务
docker compose up -d

# 查看服务状态
docker compose ps
```

## 🧪 验证安装

启动服务后,运行测试脚本验证 JuiceFS S3 Gateway 是否正常工作:

```bash
# 安装 AWS CLI (如果尚未安装)
pip install awscli

# 运行测试脚本
./backend/juicefs-s3-gateway/test-juicefs.sh
```

测试脚本会执行以下操作:
1. ✅ 检查 JuiceFS S3 Gateway 连接性
2. ✅ 创建测试存储桶
3. ✅ 上传测试文件
4. ✅ 列出对象
5. ✅ 下载并验证文件
6. ✅ 清理测试资源

## 🔌 服务访问

### JuiceFS S3 Gateway
```
Endpoint: http://localhost:9003
Access Key: juicefs
Secret Key: juicefs123
```

### MinIO 对象存储 (JuiceFS 后端)
```
API Endpoint: http://localhost:9010
Console: http://localhost:9012
Username: minioadmin
Password: minioadmin
```

### 其他 LazyRAG 服务
```
Kong API Gateway: http://localhost:8000
Auth Service: http://localhost:9001
PostgreSQL: localhost:9009
```

## 📊 架构说明

```
┌──────────────────────────────────────────────────────┐
│                  LazyRAG-back 服务                    │
├──────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────┐  ┌──────┐  ┌──────────┐  ┌──────────┐ │
│  │  Kong   │  │  DB  │  │  Redis   │  │   Core   │ │
│  │ (8000)  │  │(9009)│  │ (6379)   │  │          │ │
│  └─────────┘  └──────┘  └────┬─────┘  └──────────┘ │
│                               │                      │
│                               │ Redis DB1            │
│  ┌────────────────────────────┴───────────────────┐ │
│  │         JuiceFS S3 Gateway (9003)             │ │
│  │         - 元数据: Redis DB1                    │ │
│  │         - 数据块: MinIO                        │ │
│  └────────────────────┬─────────────────────────┘ │
│                       │                             │
│  ┌────────────────────┴─────────────────────────┐ │
│  │         MinIO 对象存储 (9000/9002)           │ │
│  │         - 存储 JuiceFS 数据块                 │ │
│  └─────────────────────────────────────────────┘ │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## 🔧 使用示例

### 使用 AWS CLI

```bash
# 配置环境变量
export AWS_ACCESS_KEY_ID=juicefs
export AWS_SECRET_ACCESS_KEY=juicefs123
export AWS_DEFAULT_REGION=us-east-1

# 创建存储桶
aws --endpoint-url http://localhost:9003 s3 mb s3://my-data

# 上传文件
aws --endpoint-url http://localhost:9003 s3 cp document.pdf s3://my-data/

# 列出文件
aws --endpoint-url http://localhost:9003 s3 ls s3://my-data/

# 下载文件
aws --endpoint-url http://localhost:9003 s3 cp s3://my-data/document.pdf downloaded.pdf
```

### 使用 Python boto3

```python
import boto3

s3 = boto3.client(
    's3',
    endpoint_url='http://localhost:9003',
    aws_access_key_id='juicefs',
    aws_secret_access_key='juicefs123'
)

# 创建存储桶
s3.create_bucket(Bucket='my-data')

# 上传文件
s3.upload_file('document.pdf', 'my-data', 'document.pdf')

# 列出对象
response = s3.list_objects_v2(Bucket='my-data')
for obj in response.get('Contents', []):
    print(obj['Key'])

# 下载文件
s3.download_file('my-data', 'document.pdf', 'downloaded.pdf')
```

## 🔐 自定义配置

创建 `.env` 文件来覆盖默认配置:

```bash
# 在 LazyRAG-back 根目录创建 .env 文件
cat > .env << 'EOF'
# JuiceFS S3 Gateway 凭证
JUICEFS_ACCESS_KEY=your-custom-key
JUICEFS_SECRET_KEY=your-custom-secret

# MinIO 后端凭证
JUICEFS_MINIO_USER=your-minio-user
JUICEFS_MINIO_PASSWORD=your-minio-password
EOF

# 重启服务使配置生效
make down
make up
```

## 📁 数据持久化

所有数据存储在 `volumes/` 目录:

```
LazyRAG-back/
├── volumes/
│   ├── db/              # PostgreSQL 数据
│   ├── redis/           # Redis 数据(包含 JuiceFS 元数据)
│   ├── juicefs-minio/   # MinIO 数据(JuiceFS 数据块)
│   └── juicefs-cache/   # JuiceFS 本地缓存
```

## 🛠️ 故障排查

### 1. 检查服务状态

```bash
docker compose ps
```

所有服务应显示 "Up" 状态。

### 2. 查看日志

```bash
# JuiceFS Gateway 日志
docker compose logs -f juicefs-s3-gateway

# MinIO 日志
docker compose logs -f juicefs-minio

# 所有日志
docker compose logs -f
```

### 3. 重启服务

```bash
# 重启特定服务
docker compose restart juicefs-s3-gateway

# 重启所有服务
make down && make up
```

### 4. 清理并重新启动

```bash
# 停止服务并删除所有数据
make clear

# 重新构建并启动
make up-build
```

## 📚 相关文档

- [backend/juicefs-s3-gateway/README.md](backend/juicefs-s3-gateway/README.md) - 详细使用文档
- [backend/juicefs-s3-gateway/test-juicefs.sh](backend/juicefs-s3-gateway/test-juicefs.sh) - 测试脚本
- [JuiceFS 官方文档](https://juicefs.com/docs/zh/community/introduction)

## ⚠️ 注意事项

1. **生产环境**: 请修改默认密码,使用更安全的凭证
2. **数据备份**: 定期备份 `volumes/` 目录
3. **资源限制**: 根据实际负载调整 Docker 资源限制
4. **网络安全**: 生产环境建议使用 HTTPS 和防火墙规则

## 🎯 下一步

1. 运行 `make up-build` 启动所有服务
2. 运行 `./backend/juicefs-s3-gateway/test-juicefs.sh` 验证安装
3. 开始使用 JuiceFS S3 Gateway 存储和管理数据
4. 参考 `backend/juicefs-s3-gateway/README.md` 了解更多用法

---

**集成完成时间**: 2026-03-17  
**集成人员**: AI Assistant  
**集成状态**: ✅ 完成
