# 依赖锁定基线

本文记录公开仓库的可复现依赖基线，不代表任何具体服务器的运行状态。实际构建以
[`docker-compose.yml`](../docker-compose.yml)、[`nonebot/pyproject.toml`](../nonebot/pyproject.toml)
和 [`nonebot/uv.lock`](../nonebot/uv.lock) 为准。

基线日期：2026-09-04

| 组件 | 锁定版本或基线 |
|---|---|
| QQBot | 0.1.0 |
| Python | 3.12.14，`python:3.12-slim-bookworm` |
| Python 基础镜像 digest | `sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579` |
| uv | 0.12.7 |
| hatchling | 1.32.0 |
| NoneBot2 | 2.5.0 |
| nonebot-adapter-onebot | 2.4.6 |
| aiosqlite | 0.22.1 |
| httpx | 0.28.1 |
| pydantic（传递依赖） | 2.13.5 |
| pytest | 9.1.1 |
| pytest-asyncio | 1.4.0 |
| SQLite schema | 2 |
| NapCat | 4.18.19 |
| NapCat 镜像 | `mlikiowa/napcat-docker:v4.18.19` |
| NapCat 镜像 digest | `sha256:1336a777f9a4f1f8cb89fef42f7548deacd3645919a067a50df5b66b5e77390e` |

## 锁定策略

- Python 顶层依赖在 `pyproject.toml` 中使用精确版本，并通过 `uv.lock` 锁定传递依赖。
- Docker 构建使用带 digest 的 Python 基础镜像。
- NapCat 使用明确版本和完整 digest，禁止默认追踪 `latest`。
- Docker Engine 与 Docker Compose 是宿主机前置条件，不由本仓库锁定具体版本；应使用 Docker 官方仍受支持的稳定版本和 Compose v2 插件。
- Linux QQ 随 NapCat 镜像提供，不在本仓库单独安装或声明一个未经验证的版本。

## 升级规则

升级依赖时应在独立分支完成，并同时更新版本声明、锁文件和本文。合并前至少执行：

```bash
docker build --target test -f nonebot/Dockerfile -t qqbot-nonebot-test .
docker run --rm --network none qqbot-nonebot-test
docker compose config --quiet
```

升级 NapCat 前还应：

1. 阅读官方 Release 和已知问题。
2. 备份 NapCat 配置；需要备份 QQ 登录状态时，应先停止 NapCat 并把备份作为敏感文件保存。
3. 显式填写新 tag 和完整 digest。
4. 验证扫码或快速登录、OneBot 反向 WebSocket、`ping` 和 `help`。
5. 保留原镜像引用，确认稳定后再清理。

NapCat 是非 QQ 官方项目。即使依赖版本完全锁定，QQ 仍可能要求验证码、设备确认或重新登录，也可能执行账号风险处置。版本锁定用于提高可复现性，不能消除平台风险。

## 官方来源

- [NapCatQQ](https://github.com/NapNeko/NapCatQQ)
- [NapCat-Docker](https://github.com/NapNeko/NapCat-Docker)
- [NoneBot2](https://nonebot.dev/)
- [OneBot V11 适配器](https://onebot.adapters.nonebot.dev/)
- [Docker Engine for Ubuntu](https://docs.docker.com/engine/install/ubuntu/)
- [uv](https://docs.astral.sh/uv/)
