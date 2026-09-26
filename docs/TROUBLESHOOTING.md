# 故障排查

先执行：

```bash
bash scripts/status.sh
bash scripts/logs.sh all --tail 200
```

日志助手会尽力脱敏，但仍不要把整份生产日志直接贴到公开 Issue。只保留必要时间段，并人工检查 QQ 号、群号、消息、二维码、验证链接和 Secret。

## 容器 Up，但 QQ 不回复

容器运行不等于 QQ 已登录。依次确认：

1. `docker compose ps` 中 NoneBot 健康、NapCat 运行。
2. NapCat WebUI 显示账号已登录，而不是等待二维码/验证码。
3. NoneBot 日志出现 OneBot 账号 connected。
4. NapCat Reverse WebSocket Client 已启用，地址为 `ws://nonebot:8080/onebot/v11/ws`。
5. 两边 Token 完全一致，且没有多余空格。
6. 在 QQ 中发送真实 `ping`，应收到 `pong`。

不要为普通 NoneBot 故障先重启 NapCat；这可能触发 QQ 再次验证。

## 无法打开 WebUI

服务器只监听 `127.0.0.1:6099` 是预期安全行为。保持本地 SSH Tunnel 运行：

```bash
ssh -N -p <SSH端口> -i <私钥路径> \
  -L 6099:127.0.0.1:6099 <SSH用户>@<服务器地址>
```

本地访问 `http://127.0.0.1:6099/webui`。若本地 6099 被占用，可把命令左侧改成其他端口，例如 `16099:127.0.0.1:6099`，再访问 `http://127.0.0.1:16099/webui`。

检查端口时，`ss -lntup` 应看到服务器回环地址，而不是 `0.0.0.0:6099` 或 `[::]:6099`。

## Reverse WebSocket 连接失败

- URL 必须使用 Compose 服务名 `nonebot`，不能使用 `127.0.0.1`；容器内的回环地址只指向 NapCat 自己。
- NoneBot 8080 只需要 `expose`，不需要映射到宿主机。
- Token 来自 `.env` 的 `ONEBOT_ACCESS_TOKEN`。不要在命令历史或公开日志中输出它。
- 修改连接配置后优先在 WebUI 保存并启用；字段名以当前 NapCat 官方文档为准。
- `docker compose exec napcat` 并不是必要步骤，也不要随意安装网络工具污染容器。

## AI 回复“未配置”

AI 默认关闭。运行：

```bash
bash scripts/set-ai-config.sh
docker compose up -d --no-deps --build nonebot
```

确认 `AI_ENABLED=true`、Base URL、模型名和 Key 均已设置。不要用 `docker compose config` 的完整输出向别人求助，因为展开后的环境可能含 Secret。

## AI 暂时不可用、限流或请求失败

- 401/403 通常是 Key、权限或 Base URL 问题。
- 404 常见于 Base URL 路径或模型名错误。
- 429 是 Provider 限流；降低并发/频率或等待配额恢复。
- 5xx、DNS、连接失败和超时属于 Provider/网络故障。
- 400/422 可能表示目标并非兼容的 Chat Completions 接口，或响应格式不兼容。

机器人不会把 Provider 响应正文原样发给 QQ。查看脱敏 NoneBot 日志定位状态码；不要使用会输出 Authorization 的 `curl -v`。

## “请求太快”

`AI_COOLDOWN_SECONDS` 按 QQ 用户分别计算，不同用户互不共享冷却。可以在 `.env` 调整为 `0` 到 `3600` 秒；`0` 表示关闭应用层冷却。`AI_MAX_CONCURRENCY` 是所有会话共享的 Provider 并发上限。

同一个群会话会串行处理以保持上下文写入顺序；多人同时说话时请求会排队，而不是共用同一个用户冷却。

## 数据库或权限错误

确认：

```bash
ls -ld data/nonebot napcat/config napcat/qq
docker compose config --quiet
```

首次部署脚本会写入 `APP_UID`/`APP_GID` 并准备目录。不要用 `chmod -R 777`。如果迁移了目录，应根据 `.env` 中的运行 UID/GID 修复所有权，并保留 `.env` 权限 `600`。

SQLite 正在运行时不要直接复制 `bot.db`；使用 `scripts/backup.sh` 的 SQLite backup API。

## 内存不足

```bash
free -h
docker stats --no-stream
df -h /
```

优先检查日志增长、异常重启、重复容器和无关服务。Compose 已限制日志轮转；2 GiB 服务器应配置 Swap 作为 OOM 兜底，但 Swap 不是实际内存。一次只构建一个镜像。

## NapCat 掉线或被要求验证

NapCat 是非 QQ 官方接入方案，登录态可能因平台安全策略、客户端版本或设备识别失效。出现 KickedOffline、二维码循环、设备确认、功能限制或 PacketBackend 错误时：

1. 保留并脱敏完整时间段日志。
2. 查看已锁定 NapCat/QQ 版本。
3. 对照 NapCat 官方 Releases 与 Issues。
4. 按 QQ 官方页面完成人工验证，不绕过安全检查。
5. 不要随机反复升级、降级或重装。

## 更新失败

`scripts/update.sh nonebot` 会在更新前备份并保留旧本地镜像标签。NapCat 更新要求明确 tag+digest，并保留一致性冷备与旧镜像引用。不要在未核对备份的情况下删除旧镜像或备份。

完整恢复流程见 `scripts/restore.md`。恢复前先校验 SHA-256，在停止写入后操作，并把当前状态移动到单独目录而不是直接覆盖删除。
