# JuiceFS S3 Gateway 用户操作文档（LazyRAG 集成版）

本文档面向**使用者/运维**，说明在 `LazyRAG` 项目中如何启动、配置、验证与使用 **JuiceFS S3 Gateway**（S3 兼容接口），以及常见问题排查方法。

---

## 1. 组件与端口

本集成包含 3 个关键组件：

- **Redis（元数据）**：JuiceFS 元数据存储（使用 Redis DB=1）
- **MinIO（对象存储后端）**：存储 JuiceFS 数据块
- **JuiceFS S3 Gateway（对外 S3 接口）**：提供 S3 兼容 API

### 1.1 对外端口（宿主机）

- **JuiceFS S3 Gateway（S3 API）**：`http://localhost:9003`
- **MinIO API（后端对象存储）**：`http://localhost:9010`
- **MinIO Console（管理界面）**：`http://localhost:9012`

> 说明：MinIO 使用 `9010/9012` 是为了避开你机器上已有的 `9000/9002` 端口占用。

---

## 2. 前置条件

- 已安装并启动 **Docker Desktop**
- 在项目根目录：`LazyRAG/`

---

## 3. 启动与停止

### 3.1 启动（推荐：构建并启动）

在 `LazyRAG/` 下执行（将本机路径用 `xxx` 代替）：

```bash
cd xxx/LazyRAG
make up-build
```

如果镜像已构建过，也可以直接：

```bash
make up
```

### 3.2 查看服务状态

```bash
docker compose ps
```

你应能看到：
- `juicefs-minio` 为 `healthy`
- `redis` 为 `healthy`
- `juicefs-s3-gateway` 为 `Up`

### 3.3 停止

```bash
make down
```

### 3.4 清理（会删除数据卷）

```bash
make clear
```

---

## 4. 账号与凭证

### 4.1 S3 Gateway 访问凭证

S3 访问密钥来自 `juicefs-s3-gateway` 容器环境变量：

- **Access Key**：`juicefs`
- **Secret Key**：`juicefs123`

对应 `docker-compose.yml` 中：
- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`

### 4.2 MinIO（后端）登录凭证

- **Console**：`http://localhost:9012`
- **用户名**：`minioadmin`
- **密码**：`minioadmin`

---

## 5. 首次初始化（必须做一次）

JuiceFS 第一次使用时需要对文件系统进行 `format`（只需执行一次，后续无需重复）。

在 `LazyRAG/` 下执行（将本机路径用 `xxx` 代替）：

```bash
cd xxx/LazyRAG
docker compose run --rm juicefs-s3-gateway format \
  --storage minio \
  --bucket http://juicefs-minio:9000/juicefs \
  --access-key minioadmin \
  --secret-key minioadmin \
  redis://test:123456@redis:6379/1 \
  lazyrag
```

成功标志：输出里包含 `Volume is formatted`，并显示 `Name: lazyrag`。

---

## 6. 使用方式说明（重要）

### 6.1 默认模式：单桶（Single-bucket）

当前配置下，S3 Gateway 默认是**单桶模式**，会出现一个固定的 Bucket：

- Bucket 名：`lazyrag`

因此：
- 你**不需要**（也通常无法）随意创建新 Bucket
- 你应该把文件上传到 `s3://lazyrag/...`

如果你确实需要多桶模式，请参考本文最后的“可选：启用多桶模式”。

---

## 7. 手动测试（不安装本机 awscli 的方式）

下面的所有 S3 测试都使用 Docker 运行 AWS CLI（不会污染本机 Python/系统环境）。

### 7.1 准备：拉取 AWS CLI 镜像（首次需要）

```bash
docker pull amazon/aws-cli:latest
```

### 7.2 定义一个可复用的 AWS CLI 命令（可选）

```bash
AWS="docker run --rm --network host \
  -e AWS_ACCESS_KEY_ID=juicefs \
  -e AWS_SECRET_ACCESS_KEY=juicefs123 \
  amazon/aws-cli"
```

后续命令中用 `$AWS` 替代完整 docker run。

### 7.3 连接性测试

```bash
curl -I http://localhost:9003
```

出现 `HTTP/1.1 400` 或 `403` 都可能是正常现象（S3 需要签名/请求格式），关键是能收到响应，且 `Server: MinIO`。

### 7.4 列出 Bucket

```bash
$AWS --endpoint-url http://localhost:9003 s3 ls
```

预期输出包含：
- `lazyrag`

### 7.5 上传文件

```bash
echo "hello juicefs $(date)" > /tmp/test-juicefs.txt

docker run --rm --network host \
  -v /tmp/test-juicefs.txt:/tmp/test-juicefs.txt \
  -e AWS_ACCESS_KEY_ID=juicefs \
  -e AWS_SECRET_ACCESS_KEY=juicefs123 \
  amazon/aws-cli \
  --endpoint-url http://localhost:9003 \
  s3 cp /tmp/test-juicefs.txt s3://lazyrag/test.txt
```

### 7.6 列出对象

```bash
$AWS --endpoint-url http://localhost:9003 s3 ls s3://lazyrag/
```

预期能看到：
- `test.txt`

### 7.7 下载并比对内容

```bash
docker run --rm --network host \
  -v /tmp:/tmp \
  -e AWS_ACCESS_KEY_ID=juicefs \
  -e AWS_SECRET_ACCESS_KEY=juicefs123 \
  amazon/aws-cli \
  --endpoint-url http://localhost:9003 \
  s3 cp s3://lazyrag/test.txt /tmp/downloaded-test.txt

diff /tmp/test-juicefs.txt /tmp/downloaded-test.txt
```

`diff` 无输出表示一致。

### 7.8 查询对象元数据

```bash
$AWS --endpoint-url http://localhost:9003 s3api head-object --bucket lazyrag --key test.txt
```

预期返回 JSON（包含 `ContentLength`、`ETag`、`LastModified` 等）。

### 7.9 复制对象（S3 内部 copy）

```bash
$AWS --endpoint-url http://localhost:9003 s3 cp s3://lazyrag/test.txt s3://lazyrag/test-copy.txt
```

### 7.10 子目录上传与递归列表

```bash
echo "subdir file" > /tmp/subdir-test.txt

docker run --rm --network host \
  -v /tmp/subdir-test.txt:/tmp/subdir-test.txt \
  -e AWS_ACCESS_KEY_ID=juicefs \
  -e AWS_SECRET_ACCESS_KEY=juicefs123 \
  amazon/aws-cli \
  --endpoint-url http://localhost:9003 \
  s3 cp /tmp/subdir-test.txt s3://lazyrag/mydir/subfile.txt

$AWS --endpoint-url http://localhost:9003 s3 ls s3://lazyrag/ --recursive
```

### 7.11 清理测试文件

```bash
$AWS --endpoint-url http://localhost:9003 s3 rm s3://lazyrag/test.txt
$AWS --endpoint-url http://localhost:9003 s3 rm s3://lazyrag/test-copy.txt
$AWS --endpoint-url http://localhost:9003 s3 rm s3://lazyrag/mydir/subfile.txt
rm -f /tmp/test-juicefs.txt /tmp/downloaded-test.txt /tmp/subdir-test.txt
```

---

## 8. 数据持久化与目录说明

默认数据落盘位置（项目内）：

- `LazyRAG/volumes/juicefs-minio/`：MinIO 数据（JuiceFS 数据块）
- `LazyRAG/volumes/redis/`：Redis 数据（包含 JuiceFS 元数据 DB1）
- `LazyRAG/volumes/juicefs-cache/`：JuiceFS 本地缓存

---

## 9. 常用运维命令

### 9.1 查看日志

```bash
docker compose logs -f juicefs-s3-gateway
docker compose logs -f juicefs-minio
docker compose logs -f redis
```

### 9.2 重启服务

```bash
docker compose restart juicefs-s3-gateway
docker compose restart juicefs-minio
```

### 9.3 仅启动 JuiceFS 相关服务

```bash
docker compose up -d redis juicefs-minio juicefs-s3-gateway
```

---

## 10. 常见问题（FAQ / Troubleshooting）

### 10.1 `Bind for 0.0.0.0:9000 failed: port is already allocated`

原因：宿主机端口 `9000` 已被其他 MinIO/服务占用。  
解决：本集成已将 MinIO 端口调整为 `9010/9012`，如仍冲突请修改 `docker-compose.yml` 中端口映射并重启。

### 10.2 `WRONGPASS invalid username-password pair`

原因：Redis ACL 用户/密码不匹配。  
解决：
- 确认 `redis-users.acl` 是**文件**而非目录，并包含 `test/123456`
- 重新创建 Redis 容器：

```bash
docker compose stop redis
docker compose rm -f redis
docker compose up -d redis
```

### 10.3 `database is not formatted, please run juicefs format ...`

原因：未做首次初始化。  
解决：执行本文第 5 节的 `format` 命令（只需一次）。

### 10.4 `403` / `400` 访问根路径

原因：S3 API 需要正确签名或请求格式。  
解决：使用本文第 7 节的 AWS CLI（带签名）命令验证即可。

---

## 11. 可选：启用多桶模式（Multi-buckets）

如果你希望支持 `aws s3 mb s3://xxx` 创建多个 Bucket，可将 `docker-compose.yml` 中 `juicefs-s3-gateway` 的 `command` 追加：

```yaml
--multi-buckets
```

修改后重启：

```bash
docker compose up -d juicefs-s3-gateway
```

> 注意：多桶模式会将**顶层目录**映射为 Bucket，属于网关层面的语义变化；建议在团队统一约定后开启。

---

## 12. 关键配置（当前项目内）

当前运行参数（节选自 `docker-compose.yml`）：

- Meta（元数据）：`redis://test:123456@redis:6379/1`
- Gateway 监听：`:9000`（容器内），宿主机映射为 `9003`
- 后端对象存储：`juicefs-minio:9000`（容器内），宿主机映射为 `9010`

