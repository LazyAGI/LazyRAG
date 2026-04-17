# file_watcher

宿主机上的常驻后台进程，负责目录监听、文件扫描、事件上报和文件落地（staging）。

给 code agent 使用的实现约束清单见 `AGENT_IMPLEMENTATION_CHECKLIST.md`。

## 目录结构

```
file_watcher/
  cmd/main.go                  # 程序入口
  internal/
    model.go                   # 所有共享数据结构和枚举常量
    config/config.go           # YAML 配置加载
    api/
      server.go                # HTTP server + 路由 + Bearer 认证
      handler.go               # 所有 HTTP handler
    control/
      client.go                # 控制面 HTTP 客户端接口
      heartbeat.go             # 心跳上报 + 指令拉取循环
    source/
      manager.go               # Source 生命周期管理
      reconcile.go             # 快照 diff + 补偿事件上报
    fs/
      scanner.go               # 全量扫描 + 批量上报
      watcher.go               # 递归 fsnotify + debounce + 自动重建
      staging.go               # 流式文件复制到 staging
      path.go                  # 路径白名单校验
    app/app.go                 # 进程生命周期 + 健康自检
  configs/agent.yaml           # 运行参数配置文件
  Dockerfile
```

---

## 快速启动

### 1. 修改配置

编辑 `configs/agent.yaml`，至少修改以下字段：

```yaml
agent_id: "file-watcher-local-001"   # 唯一标识，自定义
tenant_id: "tenant-demo"
agent_token: "my-secret-token"        # 认证 token，curl 测试时需要用到

# 控制面地址，没有控制面时填任意地址，心跳会失败但进程不会崩溃
control_plane_base_url: "http://127.0.0.1:18080"

security:
  allowed_roots:
    - "/Users"          # 改成你实际要监听的目录前缀
    - "/tmp"

staging:
  enabled: true
  host_root: "/tmp/ragscan-staging"   # staging 落地根目录（宿主机路径）
  container_root: "/data/staging"     # 下游容器内对应路径

snapshot:
  host_root: "/tmp/ragscan-snapshots" # reconcile 快照持久化目录
```

### 2. 启动进程

```bash
cd LazyRAG/backend/file_watcher
go run ./cmd/main.go -config configs/agent.yaml
```

启动成功后日志示例：

```json
{"ts":"...","level":"info","msg":"http server listening","addr":"127.0.0.1:19090"}
{"ts":"...","level":"warn","msg":"register agent failed, will retry via heartbeat","error":"..."}
```

控制面不存在时注册失败是正常的，HTTP API 仍然完全可用。

`file-watcher` 拉取到控制面命令后会执行 ACK 回传，支持控制面命令可靠投递重试。

reconcile 快照落盘后会把快照元信息（`source_id/snapshot_ref/file_count/taken_at`）回报给 control-plane。

---

## 接口测试

设置环境变量方便复用：

```bash
TOKEN="my-secret-token"
BASE="http://127.0.0.1:19090"
```

### 健康检查

```bash
curl $BASE/healthz
# {"status":"ok"}
```

### 浏览目录

```bash
curl -s -X POST $BASE/api/v1/fs/browse \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/tmp"}' | jq .
```

### 获取目录树

```bash
curl -s -X POST $BASE/api/v1/fs/tree \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/tmp", "max_depth": 2, "include_files": false}' | jq .
```

### 校验路径

```bash
curl -s -X POST $BASE/api/v1/fs/validate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/tmp"}' | jq .
```

### 读取文件元数据

```bash
curl -s -X POST $BASE/api/v1/fs/stat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path": "/tmp/test.txt"}' | jq .
```

### 启动 Source（开始监听目录）

先创建测试目录：

```bash
mkdir -p /tmp/test-watch
```

启动 Source：

```bash
curl -s -X POST $BASE/api/v1/sources/start \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "src-001",
    "tenant_id": "tenant-demo",
    "root_path": "/tmp/test-watch"
  }' | jq .
```

启动后会自动执行首次全量扫描，然后开始监听目录变化。

### 验证 watcher 工作

在另一个终端操作文件，观察 file_watcher 日志：

```bash
echo "hello" > /tmp/test-watch/a.txt
echo "world" >> /tmp/test-watch/a.txt
rm /tmp/test-watch/a.txt
mkdir /tmp/test-watch/subdir
```

日志中会出现事件捕获记录（控制面不存在时上报会失败，但事件本身被正确捕获）。

### 手动触发全量扫描

```bash
curl -s -X POST $BASE/api/v1/sources/scan \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_id": "src-001", "mode": "full"}' | jq .
```

触发 reconcile 扫描：

```bash
curl -s -X POST $BASE/api/v1/sources/scan \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_id": "src-001", "mode": "reconcile"}' | jq .
```

### 文件落地（staging）

```bash
echo "test content" > /tmp/test-watch/doc.pdf

curl -s -X POST $BASE/api/v1/fs/stage \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "src-001",
    "document_id": "doc-abc",
    "version_id": "v1",
    "src_path": "/tmp/test-watch/doc.pdf"
  }' | jq .
```

返回示例：

```json
{
  "host_path": "/tmp/ragscan-staging/src-001/doc-abc/v1/source-file.pdf",
  "container_path": "/data/staging/src-001/doc-abc/v1/source-file.pdf",
  "uri": "file:///data/staging/src-001/doc-abc/v1/source-file.pdf",
  "size": 13
}
```

验证文件已复制：

```bash
ls /tmp/ragscan-staging/src-001/doc-abc/v1/
```

### 停止 Source

```bash
curl -s -X POST $BASE/api/v1/sources/stop \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_id": "src-001"}' | jq .
```

---

## 编译与部署

file_watcher 是宿主机常驻进程，直接编译成二进制部署，**不以容器方式运行**（容器内无法可靠监听宿主机文件系统事件）。

### 本地编译

```bash
cd LazyRAG/backend/file_watcher
go build -o file_watcher ./cmd/main.go
```

### CI 环境编译（通过 Docker 提取二进制）

```bash
docker build -t file-watcher-builder .
docker create --name fw-tmp file-watcher-builder
docker cp fw-tmp:/build/file_watcher ./file_watcher
docker rm fw-tmp
```

### 宿主机部署

**macOS（launchd）**

创建 `/Library/LaunchDaemons/com.lazyrag.file-watcher.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.lazyrag.file-watcher</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/file_watcher</string>
    <string>-config</string>
    <string>/etc/lazyrag/agent.yaml</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>/var/log/file_watcher.log</string>
  <key>StandardErrorPath</key>
  <string>/var/log/file_watcher.err</string>
</dict>
</plist>
```

```bash
sudo launchctl load /Library/LaunchDaemons/com.lazyrag.file-watcher.plist
```

**Linux（systemd）**

创建 `/etc/systemd/system/file-watcher.service`：

```ini
[Unit]
Description=LazyRAG File Watcher
After=network.target

[Service]
ExecStart=/usr/local/bin/file_watcher -config /etc/lazyrag/agent.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now file-watcher
```

---

## 配置项说明

| 字段 | 默认值 | 说明 |
|---|---|---|
| `agent_id` | 必填 | Agent 唯一标识 |
| `tenant_id` | 必填 | 租户 ID |
| `agent_token` | 必填 | HTTP API Bearer Token |
| `listen_addr` | `127.0.0.1:19090` | HTTP 监听地址 |
| `control_plane_base_url` | 必填 | 控制面 HTTP 地址 |
| `heartbeat_interval` | `15s` | 心跳上报间隔 |
| `pull_interval` | `10s` | 拉取控制面指令间隔 |
| `reconcile_interval` | `10m` | 周期性 reconcile 间隔 |
| `log_level` | `info` | 日志级别（debug/info/warn/error） |
| `log_dir` | 空（仅 stdout） | 日志文件目录 |
| `staging.enabled` | `true` | 是否启用 staging 文件复制 |
| `staging.host_root` | 必填 | staging 宿主机根目录 |
| `staging.container_root` | 必填 | staging 容器内对应路径 |
| `watch.debounce_window` | `2s` | watcher 事件去抖窗口 |
| `watch.max_batch_size` | `256` | 事件批量上报最大条数 |
| `scan.batch_size` | `500` | 扫描结果批量上报条数 |
| `scan.large_file_threshold_mb` | `100` | 超过此大小的文件跳过 checksum 计算 |
| `security.allowed_roots` | 必填 | 允许访问的目录白名单 |

---

## HTTP API 一览

| 方法 | 路径 | 认证 | 说明 |
|---|---|---|---|
| GET | `/healthz` | 无 | 健康检查 |
| POST | `/api/v1/fs/browse` | Bearer | 浏览目录 |
| POST | `/api/v1/fs/validate` | Bearer | 校验路径合法性 |
| POST | `/api/v1/fs/stat` | Bearer | 读取文件元数据 |
| POST | `/api/v1/fs/stage` | Bearer | 文件落地到 staging |
| POST | `/api/v1/sources/start` | Bearer | 启动 Source（开始监听） |
| POST | `/api/v1/sources/stop` | Bearer | 停止 Source |
| POST | `/api/v1/sources/scan` | Bearer | 手动触发扫描 |
