# QQBot Lite

[![Test](https://github.com/Riordon666/qqbot/actions/workflows/test.yml/badge.svg)](https://github.com/Riordon666/qqbot/actions/workflows/test.yml)

一个面向长期运行和持续开发的轻量 QQ 机器人基础项目：NapCat 提供 QQ/OneBot 11 接入，NoneBot2 负责插件路由，SQLite 保存上下文，OpenAI-compatible API 提供可选 AI 对话。

它不是整合式 Bot 框架，也不会预装几十个社区插件。默认只有可验证的基础能力和清晰的扩展边界，适合 2 核 2 GiB 的小型 Linux 服务器。

## 主要特点

- 两个容器：`napcat` 与 `nonebot`，不依赖 Redis、MySQL 或 PostgreSQL。
- OneBot 11 Reverse WebSocket 只在 Docker 私有网络通信。
- NapCat WebUI 仅绑定 `127.0.0.1:6099`；NoneBot 8080 不发布到宿主机。
- 无斜杠路由：`ping`、`help` 等关键词优先，未命中的消息再进入 AI。
- 插件注册表保证一条消息只由一个功能处理，并在启动时检查关键词冲突。
- OpenAI-compatible Chat Completions，异步请求、超时、限流分类、冷却与并发控制。
- SQLite WAL 长期保存原始对话；滚动摘要控制模型上下文长度，不依赖供应商保存会话。
- QQ 号仅作为本地稳定身份键，回复使用当前昵称；私聊与不同群相互隔离。
- 服务器本地 Prompt-only Skills，可按场景与关键词选择聊天规则，不执行任意代码。
- 非 root NoneBot、只读容器根文件系统、日志脱敏、日志轮转、健康检查与备份脚本。
- AI 默认关闭；没有 API Key 时基础 Bot 仍可正常启动。
- 明确禁止 QQ 消息到 Shell、`subprocess`、`eval`、`exec` 或通用 HTTP 代理。

## 架构

```text
QQ
 └─ Linux QQ + NapCat
      └─ OneBot 11 Reverse WebSocket
           └─ ws://nonebot:8080/onebot/v11/ws
                └─ NoneBot2 单一消息路由器
                    ├─ 精确/前缀关键词 → 独立 Plugin
                    │                      └─ Service → Database / 固定外部 API
                    └─ 未命中消息 → AI Chat Plugin
                                         ├─ 系统提示词 + 可配置人格
                                         ├─ 当前相关本地 Skill
                                         └─ SQLite 原文 + 滚动摘要
```

## 三步部署

支持 Ubuntu 22.04/24.04，`amd64` 或 `arm64`。建议至少 2 核、2 GiB 内存，并准备 Swap 作为 OOM 兜底。

### 1. 克隆并初始化

```bash
git clone https://github.com/Riordon666/qqbot.git
cd qqbot
bash scripts/setup.sh
```

如果当前 SSH 用户没有 Docker Socket 权限，初始化与日常脚本会通过 `sudo` 请求密码；本项目不会自动把用户加入等同 root 权限的 `docker` 组。

脚本会：

- 检查 Docker Engine 与 Compose v2；缺少时先征求确认，再通过 Docker 官方 APT 仓库安装。
- 询问机器人 QQ 号和可选管理员 QQ 号。
- 创建权限为 `600` 的 `.env`，生成相互独立的 OneBot Token 与 WebUI Token。
- 创建 Reverse WebSocket 默认配置、数据目录，校验 Compose、构建并启动服务。
- 已有 `.env`、NapCat 配置和持久数据不会被覆盖。

禁止用 root 权限不经审查地运行网络上一键脚本。本仓库的 Docker 安装脚本使用官方 APT 仓库，不使用 `curl | sh`。

### 2. 建立 WebUI 安全隧道并登录 QQ

在你自己的电脑运行，替换尖括号内容：

```bash
ssh -N -p <SSH端口> -i <私钥路径> \
  -L 6099:127.0.0.1:6099 <SSH用户>@<服务器地址>
```

保持该终端窗口打开。在服务器上查看 WebUI Token：

```bash
bash scripts/show-webui-token.sh
```

然后只在本地浏览器打开：

```text
http://127.0.0.1:6099/webui
```

按 QQ 页面要求扫码、验证码或设备确认。WebUI 实际运行在服务器的 NapCat 容器中；本地电脑只建立加密隧道，关闭浏览器和隧道不会停止机器人。

### 3. 验收

```bash
bash scripts/status.sh
bash scripts/logs.sh all --tail 120
```

在 QQ 中发送：

```text
ping
help
```

`ping` 应回复 `pong`。容器处于 `running`/`healthy` 只代表进程状态；还必须确认 NapCat 已登录、NoneBot 日志出现 OneBot 账号连接，并完成真实 QQ 消息测试。

更完整的部署与端口验收见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 可用功能

默认不需要输入 `/`：

- `ping` → 返回 `pong`。
- `help` 或 `帮助` → 动态列出当前插件。
- `status` 或 `状态` → 返回不含服务器 IP、路径与 Secret 的安全状态。
- `机器人状态` 或 `bot status` → 仅 `SUPERUSERS`。
- `清空上下文` 或 `重置对话` → 开启新的上下文 epoch，旧记录不删除但不再发给模型。
- 其他文字 → AI fallback；私聊默认允许，群聊默认必须 @机器人。

以 `/` 开头的旧式命令不会执行，而会提示直接发送关键词。

## 配置 AI（可选）

AI 默认关闭。请在服务器交互式配置，不要把 Key 发到聊天、Issue 或 Git：

```bash
bash scripts/set-ai-config.sh
docker compose up -d --no-deps --build nonebot
bash scripts/logs.sh nonebot --tail 120
```

脚本隐藏读取 API Key，并原子更新 `.env`。支持的主要变量：

| 变量 | 说明 | 默认值 |
|---|---|---|
| `AI_ENABLED` | 是否启用 AI | `false` |
| `AI_BASE_URL` | OpenAI-compatible 根地址或完整 `/chat/completions` 地址 | 空 |
| `AI_API_KEY` | Provider Secret | 空 |
| `AI_MODEL` | 模型名 | 空 |
| `AI_PRIVATE_MODE` | `all` / `off` | `all` |
| `AI_GROUP_MODE` | `mention` / `all` / `off` | `mention` |
| `AI_TIMEOUT_SECONDS` | 请求总超时 | `45` |
| `AI_COOLDOWN_SECONDS` | 每个 QQ 用户的冷却 | `2` |
| `AI_MAX_CONCURRENCY` | Provider 全局并发 | `5` |
| `AI_MAX_HISTORY_MESSAGES` | 每次最多装载的近期消息 | `24` |
| `AI_MAX_CONTEXT_CHARS` | 发送给模型的上下文字符上限 | `24000` |
| `AI_MAX_REPLY_CHARS` | QQ 回复字符上限 | `3000` |

请求总超时从取得并发名额后开始计时，不包含排队等待。Provider 响应在解压后最多读取 1 MiB；重定向、非 JSON 和不合法结构会返回简洁错误。模型和插件输出作为纯文本发送，不解释其中的 CQ 码。

群聊模式设为 `all` 会读取并回复大量普通消息，容易刷屏、增加费用和污染上下文；公开部署推荐保留 `mention`。

## 长期上下文如何工作

OpenAI-compatible Provider 通常不会替应用可靠保存会话。本项目在每次调用时自行组装：

```text
核心安全提示词
→ 可配置人格
→ 当前场景
→ 当前相关本地 Skills
→ 当前会话滚动摘要（作为资料，不作为系统指令）
→ 摘要后的最近原文
→ 当前用户消息（附当前昵称资料）
```

- 私聊键：`private:<QQ号>`。
- 群聊键：`group:<群号>`。
- QQ 号保存在本地用于身份关联，不主动发给模型；昵称作为不可信展示资料发送。
- 用户消息在调用 Provider 前先写入 SQLite，因此 429、超时或 5xx 不会丢掉该句原文。
- 摘要只推进游标，不删除原始对话；失败时不会破坏当前聊天。
- 同一群共享群会话上下文，不同群和私聊不会互相读取。

数据库统一由 `nonebot/src/qqbot/database.py` 访问，使用 WAL、foreign keys、5 秒 busy timeout 与 `NORMAL` synchronous。插件不得自行散落 `sqlite3.connect(...)`。

## 本地 Skills

Skill 位于 `nonebot/skills/<skill_id>/`：

```text
example_support/
├── skill.toml
└── SKILL.md
```

`skill.toml` 示例：

```toml
id = "example_support"
name = "产品答疑"
description = "根据维护者提供的产品规则回答问题"
enabled = true
always = false
triggers = ["产品", "售后"]
contexts = ["private", "group"]
```

Skill 只提供模型规则，不执行文件中的代码，也不自动获得网络权限。如果功能需要调用外部 API，应实现固定异步 Service 与独立 Plugin：限制 Origin、方法、参数、响应大小和超时，并在 HTTP 之前完成权限检查。不要把 Secret 或通用 URL 写进 Skill。

## 添加插件

执行链固定为：

```text
router / PluginSpec → plugin handler → service → database / fixed API
```

最小插件：

```python
from qqbot.routing import PluginSpec, RouteContext, registry


async def handle_greeting(context: RouteContext) -> str:
    return f"你好，{context.nickname}！"


registry.register(
    PluginSpec(
        plugin_id="example.greeting",
        name="问候",
        description="向当前用户问好",
        usage="你好机器人",
        exact=("你好机器人",),
        handler=handle_greeting,
        category="示例",
    )
)
```

然后把模块同时加入 `nonebot/bot.py` 的 `REQUIRED_PLUGIN_MODULES` 和 `nonebot/pyproject.toml` 的 `[tool.nonebot].plugins`，并增加路由冲突、权限和失败路径测试。不要再建立另一个通吃消息的 `on_message` matcher。

详细规范见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## 目录

```text
qqbot/
├── docker-compose.yml
├── .env.example
├── README.md
├── LICENSE
├── SECURITY.md
├── THIRD_PARTY_NOTICES.md
├── docs/
├── nonebot/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── bot.py
│   ├── prompts/
│   ├── skills/
│   ├── src/qqbot/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── routing.py
│   │   ├── plugins/
│   │   └── services/
│   └── tests/
├── data/nonebot/          # 运行数据，不进 Git
├── napcat/config/         # 敏感配置，不进 Git
├── napcat/qq/             # 敏感登录状态，不进 Git
├── scripts/
└── backups/               # 敏感备份，不进 Git
```

## 端口与安全

| 监听 | 用途 | 默认公网可访问 |
|---|---|---|
| 服务器实际 SSH 端口 | 运维与 SSH Tunnel | 是，应限制来源并保留可用登录方式 |
| `127.0.0.1:6099` | NapCat WebUI | 否，仅回环 |
| `nonebot:8080` | 容器网络内 Reverse WS 与健康端点 | 否，不发布宿主机端口 |

`.env`、数据库、NapCat 配置、QQ 登录状态、日志和备份都被 `.gitignore` 排除。日志助手会脱敏已知 Token、密码摘要、认证头、二维码与 QQ 验证链接，但原始 `docker logs` 仍应视为敏感。

不要：

- 暴露 6099、8080 或额外 OneBot HTTP/WS 端口到公网。
- 提交 `.env`、登录态、数据库、备份、日志、私钥或真实聊天内容。
- 使用 `privileged: true`、`chmod -R 777`、Docker Socket 挂载或任意 URL 代理。
- 添加 QQ → Shell、系统命令、Python 动态执行或无权限写操作。
- 自动追踪 NapCat `latest`；升级前必须备份、阅读 Release、固定 tag+digest 并实测 QQ。

## 日常操作

```bash
# 启动 / 停止
docker compose up -d
docker compose down

# 状态和脱敏日志
bash scripts/status.sh
bash scripts/logs.sh all
bash scripts/logs.sh napcat
bash scripts/logs.sh nonebot

# 备份（默认不含 QQ 登录态）
bash scripts/backup.sh

# 仅更新/重建 NoneBot
bash scripts/update.sh nonebot
```

修改 Python、Prompt 或 Skill 时，只重建 NoneBot：

```bash
docker compose up -d --no-deps --build nonebot
```

NapCat 重启可能触发重新验证，不要把全栈重启当作普通代码更新步骤。恢复流程见 [scripts/restore.md](scripts/restore.md)，常见故障见 [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)。

## 测试

推荐直接使用隔离的测试镜像：

```bash
docker build --target test -f nonebot/Dockerfile -t qqbot-nonebot-test .
docker run --rm --network none qqbot-nonebot-test
ONEBOT_ACCESS_TOKEN=ci-validation-only-onebot NAPCAT_WEBUI_TOKEN=ci-validation-only-webui NAPCAT_ACCOUNT=10000 docker compose config --quiet
git diff --check
```

测试覆盖路由、配置、SQLite、长期上下文、摘要、Skill 选择、Provider 故障、日志脱敏、禁止远程执行和公开仓库清洁门禁。

## 给未来维护者

修改前先阅读本 README、`docs/`、当前代码、Git diff 与测试，不要重新设计一套平行架构。保护用户未提交的文件和运行数据；先调查，再修改，再用实际测试结果验收。任何外部查询能力都应作为独立 Plugin + Service 加入，而不是塞进 AI matcher 或开放通用工具。

## 许可与第三方

本仓库原创代码采用 MIT License，见 [LICENSE](LICENSE)。NapCatQQ、Tencent QQ for Linux、NoneBot2 及其他依赖是独立第三方项目，不因本仓库的 MIT License 被重新授权；详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

NapCat 是非 QQ 官方接入方案，可能遇到登录失效、验证码、设备确认、功能限制或账号风险处置。本项目不能保证账号持续在线或不受限制，请使用能够承受风险的账号并遵守平台规则。
