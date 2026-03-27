# JuiceFS S3 Gateway

JuiceFS S3 Gateway 为 JuiceFS 文件系统提供 S3 兼容的访问接口。

## 架构说明

- **juicefs-s3-gateway**: JuiceFS S3 网关服务,提供 S3 API 访问
- **juicefs-minio**: MinIO 对象存储后端,存储实际数据块
- **redis**: 元数据存储(复用 LazyRAG-back 主 Redis 服务的 DB1)

## 端口映射

- `9003`: JuiceFS S3 Gateway API 端口
- `9010`: MinIO API 端口
- `9012`: MinIO Console 端口

## 启动服务

在 LazyRAG-back 根目录下执行:

```bash
# 构建并启动所有服务(包括 JuiceFS)
make up-build

# 或单独启动(如果镜像已构建)
make up

# 查看服务状态
docker compose ps
```

## 访问凭证

### JuiceFS S3 Gateway
- **Endpoint**: `http://localhost:9003`
- **Access Key**: `juicefs` (可通过环境变量 `JUICEFS_ACCESS_KEY` 修改)
- **Secret Key**: `juicefs123` (可通过环境变量 `JUICEFS_SECRET_KEY` 修改)

### MinIO 对象存储
- **Endpoint**: `http://localhost:9010`
- **Console**: `http://localhost:9012`
- **Access Key**: `minioadmin` (可通过环境变量 `JUICEFS_MINIO_USER` 修改)
- **Secret Key**: `minioadmin` (可通过环境变量 `JUICEFS_MINIO_PASSWORD` 修改)

## 使用示例

### 使用 AWS CLI 访问

```bash
# 配置 AWS CLI
aws configure set aws_access_key_id juicefs
aws configure set aws_secret_access_key juicefs123
aws configure set default.region us-east-1

# 创建存储桶
aws --endpoint-url http://localhost:9003 s3 mb s3://my-bucket

# 上传文件
aws --endpoint-url http://localhost:9003 s3 cp file.txt s3://my-bucket/

# 列出文件
aws --endpoint-url http://localhost:9003 s3 ls s3://my-bucket/

# 下载文件
aws --endpoint-url http://localhost:9003 s3 cp s3://my-bucket/file.txt downloaded.txt
```

### 使用 Python boto3

```python
import boto3

# 创建 S3 客户端
s3_client = boto3.client(
    's3',
    endpoint_url='http://localhost:9003',
    aws_access_key_id='juicefs',
    aws_secret_access_key='juicefs123',
    region_name='us-east-1'
)

# 创建存储桶
s3_client.create_bucket(Bucket='my-bucket')

# 上传文件
s3_client.upload_file('file.txt', 'my-bucket', 'file.txt')

# 列出对象
response = s3_client.list_objects_v2(Bucket='my-bucket')
for obj in response.get('Contents', []):
    print(obj['Key'])

# 下载文件
s3_client.download_file('my-bucket', 'file.txt', 'downloaded.txt')
```

## 环境变量配置

在 LazyRAG-back 根目录下创建 `.env` 文件,可覆盖默认配置:

```bash
# JuiceFS S3 Gateway 访问凭证
JUICEFS_ACCESS_KEY=your-access-key
JUICEFS_SECRET_KEY=your-secret-key

# MinIO 后端凭证
JUICEFS_MINIO_USER=your-minio-user
JUICEFS_MINIO_PASSWORD=your-minio-password
```

## 数据持久化

数据存储在以下卷中:
- `./volumes/juicefs-minio`: MinIO 数据存储
- `./volumes/juicefs-cache`: JuiceFS 本地缓存
- Redis DB1: JuiceFS 元数据

## 故障排查

### 查看日志

```bash
# JuiceFS Gateway 日志
docker compose logs -f juicefs-s3-gateway

# MinIO 日志
docker compose logs -f juicefs-minio

# Redis 日志
docker compose logs -f redis
```

### 重启服务

```bash
# 重启 JuiceFS 相关服务
docker compose restart juicefs-s3-gateway juicefs-minio

# 或重启所有服务
make down
make up
```

### 清理数据

```bash
# 停止服务并删除所有数据
make clear

# 仅删除 JuiceFS 数据
rm -rf volumes/juicefs-minio volumes/juicefs-cache
```

## 技术细节

### JuiceFS 文件系统

- **卷名称**: `lazyrag`
- **元数据引擎**: Redis (redis://test:123456@redis:6379/1)
- **对象存储**: MinIO (内部连接)
- **缓存目录**: `/var/jfsCache`

### 架构图

```
┌─────────────────┐
│   S3 Client     │
│  (AWS CLI/SDK)  │
└────────┬────────┘
         │ S3 API (port 9003)
         ▼
┌─────────────────┐
│ JuiceFS Gateway │
└────┬──────────┬─┘
     │          │
     │          └─────────┐
     ▼                    ▼
┌─────────┐        ┌──────────┐
│  Redis  │        │  MinIO   │
│ (Meta)  │        │  (Data)  │
└─────────┘        └──────────┘
```

## 参考资源

- [JuiceFS 官方文档](https://juicefs.com/docs/zh/community/introduction)
- [JuiceFS S3 Gateway](https://juicefs.com/docs/zh/community/s3_gateway)
- [MinIO 文档](https://min.io/docs/minio/linux/index.html)
