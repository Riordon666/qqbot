from __future__ import annotations

from qqbot.plugins.basic import render_status
from qqbot.routing import PluginSpec, RouteContext, registry


async def handle_admin_status(_: RouteContext) -> str:
    return "管理员状态：\n" + await render_status()


registry.register(
    PluginSpec(
        plugin_id="admin.status",
        name="管理员状态",
        description="查看管理员运行状态",
        usage="机器人状态",
        exact=("机器人状态", "bot status"),
        handler=handle_admin_status,
        category="管理",
        order=10,
        admin_only=True,
    )
)
