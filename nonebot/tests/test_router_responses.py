from __future__ import annotations

import os
import subprocess
import sys


ROUTER_SCRIPT = """
import asyncio
import bot
from nonebot.adapters.onebot.v11 import Message, PrivateMessageEvent
from nonebot.exception import FinishedException
from qqbot.plugins.router import dispatch_message
from qqbot.routing import PluginSpec, registry

response = ""
sent = []

async def handler(_):
    return response

registry.register(PluginSpec(
    plugin_id="test.response", name="test", description="test", usage="test",
    exact=("release test",), handler=handler,
))

class Matcher:
    async def finish(self, message):
        sent.append(Message(message))
        raise FinishedException

event = PrivateMessageEvent.model_validate({
    "time": 1, "self_id": 100, "post_type": "message", "message_type": "private",
    "sub_type": "friend", "message_id": 1, "user_id": 1,
    "message": "release test", "raw_message": "release test", "font": 0,
    "sender": {"user_id": 1, "nickname": "test"},
})

async def run():
    global response
    for response in (
        "pong",
        "[CQ:at,qq=all]",
        "[CQ:image,file=file:///example.invalid/private.png]",
        "[CQ:image,file=https://example.invalid/picture.png]",
    ):
        try:
            await dispatch_message(Matcher(), event)
        except FinishedException:
            pass
        assert len(sent[-1]) == 1
        assert sent[-1][0].type == "text"
        assert sent[-1][0].data["text"] == response

asyncio.run(run())
print("ROUTER_TEXT_OK")
"""


def test_router_sends_untrusted_plugin_strings_as_literal_text(tmp_path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "AI_ENABLED": "false",
            "DATABASE_PATH": str(tmp_path / "bot.db"),
            "DRIVER": "~fastapi",
            "ONEBOT_ACCESS_TOKEN": "test-router-token-only",
            "SUPERUSERS": "",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", ROUTER_SCRIPT],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ROUTER_TEXT_OK" in result.stdout
