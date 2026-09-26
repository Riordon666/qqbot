from __future__ import annotations

import os
import subprocess
import sys


BOOTSTRAP_SCRIPT = """
import nonebot
import bot

required = {
    "qqbot.plugins.admin",
    "qqbot.plugins.ai_chat",
    "qqbot.plugins.basic",
    "qqbot.plugins.router",
}
loaded = {plugin.module_name for plugin in nonebot.get_loaded_plugins()}
assert required <= loaded
assert not any(module.startswith("src.qqbot.") for module in loaded)
assert "/healthz" in {
    getattr(route, "path", None)
    for route in nonebot.get_app().routes
}
assert "/onebot/v11/ws" in {
    getattr(route, "path", None)
    for route in nonebot.get_app().routes
}
print("BOOTSTRAP_OK")
"""


def test_bootstrap_plugins_routes_and_secret_redaction(tmp_path) -> None:
    onebot_sentinel = "onebot-sentinel-do-not-log-12345678"
    ai_sentinel = "ai-sentinel-do-not-log-12345678"
    env = os.environ.copy()
    env.update(
        {
            "AI_API_KEY": ai_sentinel,
            "AI_ENABLED": "false",
            "AI_PRIVATE_MODE": "all",
            "AI_GROUP_MODE": "mention",
            "COMMAND_START": "/",
            "DATABASE_PATH": str(tmp_path / "bot.db"),
            "DRIVER": "~fastapi",
            "LOG_LEVEL": "DEBUG",
            "ONEBOT_ACCESS_TOKEN": onebot_sentinel,
            "SUPERUSERS": "",
        }
    )

    result = subprocess.run(
        [sys.executable, "-c", BOOTSTRAP_SCRIPT],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = result.stdout + result.stderr

    assert result.returncode == 0, output
    assert "BOOTSTRAP_OK" in output
    assert "Duplicated prefix rule" not in output
    assert onebot_sentinel not in output
    assert ai_sentinel not in output
