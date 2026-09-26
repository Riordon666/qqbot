# 部署指南

本项目的目标部署形态只有两个长期运行的容器：

```text
QQ
  -> Linux QQ + NapCat
  -> OneBot 11 Reverse WebSocket
  -> NoneBot2
  -> 无斜杠插件 / AI / SQLite
```

不需要 Redis、MySQL、PostgreSQL、桌面环境或管理面板。

> [!WARNING]
> NapCat 是非 QQ 官方的客户端接入方案，可能遇到验证码、设备确认、登录失效、功能限制或账号风险处置。请使用能够承受该风险的账号，并遵守 QQ 的服务规则。本项目无法保证账号不会掉线或受到限制。

## 准备条件

- 一台 Linux 服务器；推荐 Ubuntu 22.04 LTS 或 24.04 LTS。
- 推荐至少 2 核 CPU、2 GiB 内存，并配置 Swap 作为 OOM 兜底。
- Git、Docker Engine 和 Docker Compose v2 插件。
- SSH 登录权限。扫码时本地电脑只用于建立 SSH Tunnel，机器人实际运行在服务器。
- 可选：兼容 OpenAI Chat Completions 的 API Base URL、Key 和模型名。没有这些配置时，基础插件仍可运行。

Docker 应从[官方 Ubuntu 安装文档](https://docs.docker.com/engine/install/ubuntu/)安装。不要使用来源不明的 `curl | sh` 一键脚本。

## 最短部署流程

### 1. 下载并初始化

```bash
git clone https://github.com/Riordon666/qqbot.git qqbot
cd qqbot
bash scripts/setup.sh
```

如果当前 SSH 用户不能直接访问 Docker，脚本会通过 `sudo` 请求密码；它不会自动把用户加入等同 root 权限的 `docker` 组。

按照脚本提示填写 QQ 账号和可选管理员 QQ 号。AI 在首次部署后单独配置。初始化脚本会：

- 检查 Docker 与 Compose。
- 创建运行数据目录。
- 从示例生成 `.env`，且不覆盖已有配置。
- 随机生成彼此不同的 OneBot Token 和 WebUI Token。
- 将 `.env` 权限设为 `600`。
- 校验 Compose、构建 NoneBot 并启动容器。

不要把脚本生成的 Token、API Key 或 `.env` 发到聊天、Issue、日志或 Git 仓库。

### 2. 安全打开 NapCat WebUI

Compose 只把 WebUI 绑定到服务器回环地址 `127.0.0.1:6099`。在自己的电脑执行：

```bash
ssh -p <ssh-port> -i <private-key-path> \
  -L 6099:127.0.0.1:6099 <server-user>@<server-host>
```

保持这个 SSH 窗口打开，然后在本地浏览器访问：

```text
http://127.0.0.1:6099/webui
```

在服务器终端运行 `bash scripts/show-webui-token.sh`，将显示的 WebUI Token 填入本地浏览器。随后按 QQ 页面要求完成扫码、验证码或设备确认。不要尝试绕过 QQ 的安全验证。

### 3. 检查 OneBot 反向 WebSocket

初始化脚本会尽量准备连接配置。如果 WebUI 中尚未生成连接，请创建 **OneBot 11 WebSocket Client / Reverse WebSocket**：

- 启用：是
- URL：`ws://nonebot:8080/onebot/v11/ws`
- Access Token：与服务器 `.env` 中的 `ONEBOT_ACCESS_TOKEN` 完全一致
- 自动重连：开启
- 心跳：使用当前 NapCat 的合理默认值
- 上报自身消息：关闭

不同 NapCat 版本的页面名称和配置字段可能变化，应以当前官方说明及 WebUI 为准。不要从公开 Issue 或聊天中粘贴 Access Token。

这里的 `nonebot` 是 Docker Compose 服务名，只在私有 Docker 网络中解析。**不要**把它替换为公网 IP，也不要给 NoneBot 增加宿主机 `8080:8080` 端口映射。

### 4. 验收

在服务器执行：

```bash
docker compose ps
./scripts/status.sh
./scripts/logs.sh all
```

然后在 QQ 中测试：

```text
ping
help
```

`ping` 应回复 `pong`。群聊默认需要真正 @机器人后才进入 AI；基础插件是否要求 @ 以帮助信息和插件配置为准。

容器处于 `running` 或 `healthy` 只说明进程状态，不等于 QQ 已登录。完整验收还必须确认：

- NapCat 已登录 QQ。
- OneBot Reverse WebSocket 已连接 NoneBot。
- QQ 中的真实消息能收到回复。
- `ss -lntup` 中没有公网监听的 6099 或 8080。

## 配置 AI（可选）

AI 默认关闭。可使用交互脚本配置，脚本不会回显 Key：

```bash
bash scripts/set-ai-config.sh
```

主要参数为：

- `AI_BASE_URL`：OpenAI-compatible API 根地址。
- `AI_API_KEY`：API Secret。
- `AI_MODEL`：供应商提供的模型名。
- `AI_PRIVATE_MODE=all|off`。
- `AI_GROUP_MODE=mention|all|off`，推荐保留 `mention`。

更新 AI 配置后只重建 NoneBot，不要重启 NapCat：

```bash
docker compose up -d --no-deps --build nonebot
./scripts/logs.sh nonebot
```

群聊使用 `all` 会处理大量普通消息，可能刷屏、增加费用并污染上下文。公开部署默认应使用 `mention`。

## 网络与安全边界

- NapCat 和 NoneBot 位于同一个私有 Docker bridge 网络。
- NoneBot 的 8080 仅通过 Compose `expose` 提供给容器网络，不发布到宿主机。
- NapCat WebUI 仅为 `127.0.0.1:6099:6099`，只能通过 SSH Tunnel 访问。
- 公网入站通常只需开放实际 SSH 端口；云平台防火墙和服务器防火墙都应核对。
- `.env`、SQLite 数据、NapCat 配置、QQ 登录数据、日志和备份都不得提交 Git。
- 禁止添加 QQ 消息到 Shell、`subprocess`、`eval`、`exec` 或任意代码执行功能。
- 不要使用 `privileged: true`、`chmod -R 777` 或挂载 Docker Socket。

## 日常命令

```bash
# 启动
docker compose up -d

# 停止
docker compose down

# 状态
./scripts/status.sh

# 脱敏日志
./scripts/logs.sh all
./scripts/logs.sh napcat
./scripts/logs.sh nonebot

# 备份
./scripts/backup.sh
```

修改 Python 代码、提示词或本地 Skill 后，优先只重建 NoneBot：

```bash
docker compose up -d --no-deps --build nonebot
```

NapCat 重启可能触发重新验证，因此不要把全栈重启作为普通 NoneBot 更新步骤。

遇到问题请按 [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) 排查。开发和扩展约定见 [`DEVELOPMENT.md`](DEVELOPMENT.md)。
