# OTA Agent 客户端

Go 语言编写的 OTA（Over-The-Air）更新客户端代理。

## 功能特性

- ✅ **多文件支持**: 支持同时更新多个文件
- ✅ **守护进程模式**: 默认以守护进程模式运行，定期检查更新
- ✅ **进程监控与保活**: 在守护进程模式下，自动监控 `restart_cmd` 指定的进程，进程异常退出时自动重启
- ✅ **原子替换**: 使用原子操作替换文件，确保更新安全
- ✅ **SHA256 校验**: 自动验证文件完整性
- ✅ **自动回滚**: 更新失败时自动回滚到备份版本
- ✅ **结构化日志**: 提供详细的日志输出
- ✅ **重试机制**: 网络请求支持自动重试
- ✅ **进度显示**: 下载文件时显示进度

## 编译

```bash
go build -o ota-agent main.go
```

## 使用方法

### 守护进程模式（默认）

```bash
./ota-agent \
  -config-url="http://server.com/ota/app1/version.yaml" \
  -version-file="/var/lib/ota-agent/version" \
  -agent-id="server-001" \
  -start-cmd="/usr/bin/myapp" \
  -check-interval=5m \
  -daemon=true
```

### 单次运行模式

```bash
./ota-agent \
  -config-url="http://server.com/ota/app1/version.yaml" \
  -version-file="/var/lib/ota-agent/version" \
  -agent-id="server-001" \
  -daemon=false
```

## 命令行参数

- `-config-url`: 配置文件 URL（必需）
- `-version-file`: 本地版本文件路径（默认: `version`）
- `-agent-id`: Agent 标识符（可选，通过 X-Agent-ID header 发送给服务器）
- `-start-cmd`: 本地启动命令（用于首次进程启动，守护进程模式下）
- `-timeout`: HTTP 请求超时时间（默认: 30s）
- `-max-retries`: HTTP 请求最大重试次数（默认: 3）
- `-check-interval`: 守护进程模式下的检查间隔（默认: 5m）
- `-daemon`: 是否以守护进程运行（默认: true）

## 配置文件格式

客户端从服务器获取 YAML 格式的配置文件：

```yaml
version: "1.0.0"
files:
  - name: "app1"
    url: "http://server.com/ota/app1/files/app1"
    sha256: "abc123..."
    target: "/usr/bin/app1"
    version: "1.0.0"
    restart: false
  - name: "lib1"
    url: "http://server.com/ota/app1/files/lib1.so"
    sha256: "def456..."
    target: "/usr/lib/lib1.so"
    version: "1.0.0"
    restart: false
restart_cmd: "systemctl restart app1"
```

## 工作流程

1. **获取配置**: 从服务器获取版本配置文件
2. **版本比较**: 比较本地版本和远程版本
3. **文件更新**: 对每个需要更新的文件：
   - 下载到临时位置
   - 验证 SHA256 校验和
   - 原子替换目标文件
   - 更新文件版本记录
4. **全局重启**: 所有文件更新完成后执行重启命令
   - **守护进程模式**: 
     - 如果远程配置有 `restart_cmd`，优先使用远程命令
     - 如果远程配置没有 `restart_cmd`，使用本地 `-start-cmd` 参数
     - 启动进程管理器来监控和保活该进程
   - **单次运行模式**: 直接执行重启命令一次
5. **版本记录**: 更新主版本文件

## 进程监控与保活

在守护进程模式下，OTA Agent 会：

- **首次启动**: 启动 OTA Agent 时，即使没有更新，也会使用 `-start-cmd` 参数指定的命令启动进程
- **更新后启动**: 更新完成后，优先使用远程配置的 `restart_cmd`，如果远程没有则使用本地 `-start-cmd`
- **状态监控**: 持续监控进程运行状态
- **自动重启**: 进程异常退出时，自动重启（默认延迟 3 秒）
- **优雅关闭**: 收到退出信号时，先发送 SIGTERM 给管理的进程，等待 5 秒后强制终止
- **重启计数**: 记录进程重启次数，可用于监控和告警
- **智能管理**: 如果进程已在运行且命令未变化，不会重复启动

### 启动命令优先级

1. **首次启动（无更新）**: 使用本地 `-start-cmd` 参数
2. **更新后**: 
   - 优先使用远程配置的 `restart_cmd`
   - 如果远程配置没有 `restart_cmd`，使用本地 `-start-cmd` 参数

### 进程监控示例

**场景 1: 首次启动**

```bash
./ota-agent \
  -config-url="http://server.com/ota/app1/version.yaml" \
  -start-cmd="/usr/bin/myapp" \
  -daemon=true
```

首次启动时，即使没有更新，也会使用 `-start-cmd` 启动 `/usr/bin/myapp` 进程。

**场景 2: 更新后使用远程命令**

远程配置文件：
```yaml
version: "1.0.1"
files:
  - name: "app1"
    url: "http://server.com/ota/app1/files/app1"
    sha256: "..."
    target: "/usr/bin/app1"
restart_cmd: "/usr/bin/app1 --new-flag"
```

更新后，会使用远程配置的 `restart_cmd`（`/usr/bin/app1 --new-flag`）替换本地启动的进程。

**场景 3: 更新后远程没有 restart_cmd**

如果远程配置没有 `restart_cmd`，更新后会继续使用本地 `-start-cmd` 指定的命令。

### 容错机制

- **网络故障容错**: 如果获取远程配置失败（网络问题、服务器不可用等），OTA Agent 仍会使用 `-start-cmd` 启动进程，确保服务可用性
- **配置错误容错**: 如果远程配置格式错误或验证失败，OTA Agent 仍会使用 `-start-cmd` 启动进程
- **持续运行**: 即使首次检查失败，守护进程仍会继续运行，并在下次检查间隔时重试

### 注意事项

- 进程监控仅在**守护进程模式**下启用
- 单次运行模式下，不会启动进程管理器
- 如果启动命令在更新过程中发生变化，旧的进程会被停止，新的进程会被启动
- 进程的标准输出和标准错误会重定向到 OTA Agent 的输出
- `-start-cmd` 参数是可选的，如果不指定，首次启动时不会启动进程
- 即使获取远程配置失败，只要配置了 `-start-cmd`，进程仍会正常启动

## 部署

### 作为 systemd 服务

创建 `/etc/systemd/system/ota-agent.service`:

```ini
[Unit]
Description=OTA Agent Daemon
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/ota-agent \
  -config-url="http://server.com/ota/app1/version.yaml" \
  -version-file="/var/lib/ota-agent/app1/version" \
  -agent-id="server-001" \
  -start-cmd="/usr/bin/myapp" \
  -check-interval=5m \
  -daemon=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable ota-agent
sudo systemctl start ota-agent
```

## 日志

守护进程模式下，日志输出到标准输出。建议重定向到日志文件：

```bash
./ota-agent -config-url="..." > /var/log/ota-agent.log 2>&1
```

或使用 systemd 的 journalctl：

```bash
journalctl -u ota-agent -f
```

## 许可证

MIT

