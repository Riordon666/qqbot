# 开发与扩展规范

## 开始之前

1. 阅读根目录 `README.md`、`SECURITY.md` 和当前代码。
2. 检查 Git 工作区，保留用户已有修改和运行数据。
3. 确认功能属于 Plugin、Service、Database 还是纯文本 Skill。
4. 先写清触发词、权限、失败方式和数据边界，再实现。

不要把所有功能塞进 `bot.py` 或一个 matcher。当前唯一消息入口是 `plugins/router.py`，它解析 `PluginSpec` 并保证一条消息最多分派给一个插件。

## 分层

```text
OneBot MessageEvent
→ router.py / PluginSpec
→ plugins/<feature>.py
→ services/<feature>_service.py
→ database.py 或固定 external API client
```

### Plugin

插件负责入口，不负责堆积业务逻辑：

- 声明 ID、名称、帮助文本、精确/前缀关键词和场景。
- 做最小文本整理。
- 调用 Service。
- 把已分类的结果转成简洁 QQ 回复。

`admin_only=True` 会由统一 Router 用 OneBot `user_id` 检查 `SUPERUSERS`。高风险 Service 仍应在写入或网络请求前再次验证权限，不相信昵称或消息正文中的自报身份。

关键词类型：

- `exact=(...)`：整句规范化后完全相等。
- `prefixes=(...)`：前缀后必须有空格、半角/全角冒号或结束。
- `compact_prefixes=(...)`：允许中文参数紧跟前缀，使用时应避免过宽词语。
- `fallback=True`：全局只能有一个，目前是 AI Chat。

新增模块后同时更新：

- `nonebot/bot.py` 中的 `REQUIRED_PLUGIN_MODULES`。
- `nonebot/pyproject.toml` 中的 `[tool.nonebot].plugins`。
- `nonebot/tests/` 中的路由、权限、成功与失败测试。

## Service

Service 负责业务规则、第三方 API 和可复用流程：

- 所有 HTTP 使用 `httpx.AsyncClient`，禁止同步阻塞事件循环。
- 固定可信 Origin、endpoint 和 HTTP 方法，不能接受用户提供的任意 URL。
- 设置 connect/total timeout、有界连接池和合理并发上限。
- 在请求前验证并限制输入；在使用前严格校验状态码、Content-Type、结构、字段类型和大小。
- 禁止自动跟随重定向，除非目标集合经过明确审核。
- 不记录认证头、完整请求正文、Secret 或外部返回的敏感内容。
- 抛出有限的业务错误，详细 traceback 只进入脱敏日志。

若未来加入模型 Tool Calling，模型只能选择程序注册的固定函数；每个工具的参数在 Python 层重新校验，权限在工具执行层再次检查，调用次数与结果大小必须有上限。Skill 文本本身不能注册或执行工具。

## Database

所有运行数据统一通过 `src/qqbot/database.py`。当前 SQLite schema 为 v2，启用：

- WAL journal mode
- foreign keys
- 5000 ms busy timeout
- `synchronous=NORMAL`

新增持久化能力时：

1. 设计可重复执行的 schema/migration。
2. 提升 schema version 并记录 migration。
3. 使用共享异步连接和写锁。
4. 添加“新库初始化、重复初始化、旧版本迁移不丢数据”测试。
5. 不在插件中直接打开 SQLite。

长期聊天的原始消息不会因摘要而删除。`清空上下文` 通过增加 epoch 隔离新旧上下文，而不是物理删除；未来实现数据删除时必须单独设计明确确认与审计边界。

## Prompt 与人格

- `prompts/core.md`：不可被人格或 Skill 覆盖的安全规则。
- `prompts/persona.md`：名称、语气、关系与表达风格。
- `prompts/summary.md`：滚动摘要规则。

昵称、群名片、历史、摘要、用户消息和外部数据都属于不可信数据，不能拼进更高优先级指令。不要在 Prompt 中保存 Token、Key、Cookie、真实内部路径或个人数据。

Prompt 和 Skill 通过只读 bind mount 进入容器。修改后重建/重启 NoneBot 即可，不需要操作 NapCat。

## Prompt-only Skill

目录：`nonebot/skills/<skill_id>/`

必需文件：

```text
skill.toml
SKILL.md
```

ID 只允许小写字母、数字与下划线，并必须和目录名相同。`always=true` 表示所有允许场景都加载；否则消息或近期上下文必须包含一个 `triggers` 子串。

Skill Loader 拒绝符号链接、空文件、非法场景和超大指令。一个 Skill 无效只会被隔离。Skill 中不得放可执行脚本或 Secret；需要外部数据时创建受测试的 Plugin + Service，Skill 只描述语义与回复规范。

## AI Provider

`AIService` 只依赖 OpenAI-compatible Chat Completions：

```http
POST {AI_BASE_URL}/chat/completions
Authorization: Bearer <AI_API_KEY>
Content-Type: application/json
```

当前只发送 `model` 和 `messages`，并要求 `choices[0].message.content` 是非空字符串。Provider 的 429、4xx、5xx、超时、网络错误和非法响应分别处理，不会影响基础插件或进程健康。

不要假设 Provider 保存上下文。SQLite 是事实来源，Prompt Builder 每次重新装配上下文。调整摘要阈值时保持 `AI_SUMMARY_KEEP_RECENT_MESSAGES < AI_SUMMARY_TRIGGER_MESSAGES`。

## 测试

容器测试最接近生产环境：

```bash
docker build -f nonebot/Dockerfile --target test -t qqbot-nonebot-test .
docker run --rm --network none qqbot-nonebot-test
docker compose config --quiet
git diff --check
```

新增功能至少覆盖：

- 正常输入与边界输入。
- 路由不误匹配、注册冲突启动失败。
- 私聊/群聊与 @ 约束。
- 管理员允许、普通用户拒绝。
- 超时、429、4xx、5xx、非法响应。
- 重复 OneBot 消息幂等。
- 上下文不跨用户/群泄露。
- Secret 不进入日志、错误或 Git。

`test_public_release.py` 是发布门禁；它会阻止常见 Secret、私钥、运行数据库、登录态、生产标识和已移除的私有集成重新进入公开仓库。

## 依赖与发布

使用精确顶层版本和 `uv.lock`。升级时在开发机重新锁定并运行完整测试，不要在 2 GiB 生产服务器临时追最新版。NapCat 必须固定明确 tag 与 digest，升级前阅读官方 Release、备份并保留回滚引用。

提交前确认：

```bash
git status --short
git diff --check
```

不要提交 `.env`、数据库、NapCat 配置/登录态、备份、日志、私钥、真实 QQ/群号、私有域名或聊天内容。
