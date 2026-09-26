from __future__ import annotations

from importlib.metadata import version

from nonebot import get_bots

from qqbot.config import get_settings
from qqbot.database import database
from qqbot.routing import PluginSpec, RouteContext, registry
from qqbot.runtime import format_uptime


settings = get_settings()


async def render_status(include_database: bool = True) -> str:
    connected_bots = len(get_bots())
    connection_text = (
        f"已连接（{connected_bots} 个账号）" if connected_bots else "尚未连接"
    )
    lines = [
        f"{settings.bot_name}：在线",
        f"运行时间：{format_uptime()}",
        f"NoneBot：{version('nonebot2')}",
        f"NapCat/QQ：{connection_text}",
    ]
    if include_database:
        lines.append(f"SQLite：{'正常' if await database.healthy() else '异常'}")
    return "\n".join(lines)


async def handle_ping(_: RouteContext) -> str:
    return "pong"


async def handle_help(context: RouteContext) -> str:
    lines = ["可用功能（无需输入斜杠）："]
    for spec in registry.specs():
        if spec.hidden:
            continue
        if spec.admin_only and context.qq_id not in settings.superusers:
            continue
        if context.conversation_kind not in spec.contexts:
            continue
        lines.append(f"{spec.usage} - {spec.description}")

    ai_state = "已启用" if settings.ai_enabled and settings.ai_configured else "未配置"
    lines.append(f"AI 状态：{ai_state}")
    return "\n".join(lines)


async def handle_status(_: RouteContext) -> str:
    return await render_status()


registry.register(
    PluginSpec(
        plugin_id="basic.ping",
        name="连通性测试",
        description="检查机器人是否在线",
        usage="ping",
        exact=("ping",),
        handler=handle_ping,
        category="基础",
        order=10,
    )
)
registry.register(
    PluginSpec(
        plugin_id="basic.help",
        name="帮助",
        description="显示当前可用功能",
        usage="help 或 帮助",
        exact=("help", "帮助"),
        handler=handle_help,
        category="基础",
        order=20,
    )
)
registry.register(
    PluginSpec(
        plugin_id="basic.status",
        name="状态",
        description="查看安全运行状态",
        usage="status 或 状态",
        exact=("status", "状态"),
        handler=handle_status,
        category="基础",
        order=30,
    )
)
