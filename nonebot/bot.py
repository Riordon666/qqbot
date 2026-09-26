from __future__ import annotations

import os

import nonebot
from nonebot.adapters.onebot.v11 import Adapter

from qqbot.config import get_settings
from qqbot.database import database
from qqbot.health import setup_health_route
from qqbot.logging_config import configure_logging
from qqbot.services.ai_service import ai_service


os.umask(0o077)

settings = get_settings()

# These values accept user-friendly CSV in our Settings layer. Remove the raw
# names before NoneBot's JSON-only environment parser sees them; the normalized
# sets are passed explicitly to nonebot.init below.
for parsed_environment_name in ("COMMAND_START", "SUPERUSERS"):
    os.environ.pop(parsed_environment_name, None)
configure_logging(settings.log_level)

nonebot.init(
    driver=os.getenv("DRIVER", "~fastapi"),
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "8080")),
    superusers=set(settings.superusers),
    nickname=set(settings.bot_nickname),
    command_start=set(settings.command_start),
)

driver = nonebot.get_driver()
driver.register_adapter(Adapter)
setup_health_route(driver)


@driver.on_startup
async def startup() -> None:
    await database.connect(settings.database_path)
    nonebot.logger.info("QQBot database initialized")


@driver.on_shutdown
async def shutdown() -> None:
    await ai_service.close()
    await database.close()
    nonebot.logger.info("QQBot shutdown complete")


REQUIRED_PLUGIN_MODULES = (
    "qqbot.plugins.basic",
    "qqbot.plugins.admin",
    "qqbot.plugins.ai_chat",
    "qqbot.plugins.router",
)
loaded_plugin_modules = {
    plugin.module_name
    for module_name in REQUIRED_PLUGIN_MODULES
    if (plugin := nonebot.load_plugin(module_name)) is not None
}
missing_plugin_modules = set(REQUIRED_PLUGIN_MODULES) - loaded_plugin_modules
if missing_plugin_modules:
    missing = ", ".join(sorted(missing_plugin_modules))
    raise RuntimeError(f"Required QQBot plugins failed to load: {missing}")


if __name__ == "__main__":
    nonebot.run()
