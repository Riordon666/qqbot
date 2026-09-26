from __future__ import annotations

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent, MessageSegment
from nonebot.matcher import Matcher

from qqbot.config import get_settings
from qqbot.plugins.common import conversation_scope, identity_from_event
from qqbot.routing import RouteContext, can_dispatch, normalize_text, registry


settings = get_settings()
registry.validate()

message_router = on_message(priority=1, block=True)


@message_router.handle()
async def dispatch_message(matcher: Matcher, event: MessageEvent) -> None:
    if event.user_id == event.self_id:
        return
    if isinstance(event, GroupMessageEvent) and not settings.group_allowed(event.group_id):
        return

    text = event.get_plaintext().strip()
    normalized = normalize_text(text)
    if not normalized:
        return

    if normalized.startswith("/"):
        await matcher.finish("以后无需输入斜杠，请直接发送关键词；发送 help 查看帮助。")

    match = registry.resolve(text)
    if match is None:
        return

    identity = identity_from_event(event)
    conversation_key, conversation_kind, scope_id = conversation_scope(event)
    if not can_dispatch(
        match.spec,
        conversation_kind,
        to_me=bool(event.to_me),
    ):
        return
    context = RouteContext(
        event=event,
        text=match.text,
        normalized_text=match.normalized_text,
        argument=match.argument,
        qq_id=identity.qq_id,
        nickname=identity.display_name,
        group_card=identity.group_card,
        conversation_key=conversation_key,
        conversation_kind=conversation_kind,
        scope_id=scope_id,
        source_message_id=str(event.message_id),
    )

    if match.spec.admin_only and context.qq_id not in settings.superusers:
        await matcher.finish("你没有使用该功能的权限。")

    try:
        response = await match.spec.handler(context)
    except Exception:
        logger.exception("Plugin {} failed", match.spec.plugin_id)
        await matcher.finish("该功能暂时不可用，请稍后再试。")

    if response:
        # Plugin strings (including model output) are plain text, never CQ
        # instructions such as mentions, local files or remote media fetches.
        await matcher.finish(MessageSegment.text(response))
