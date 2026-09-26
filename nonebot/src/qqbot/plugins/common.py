from __future__ import annotations

from dataclasses import dataclass

from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from qqbot.config import get_settings


settings = get_settings()


@dataclass(frozen=True, slots=True)
class EventIdentity:
    qq_id: str
    nickname: str
    group_card: str | None

    @property
    def display_name(self) -> str:
        return self.nickname or self.qq_id


async def group_access(event: MessageEvent) -> bool:
    if isinstance(event, GroupMessageEvent):
        return settings.group_allowed(event.group_id)
    return True


def identity_from_event(event: MessageEvent) -> EventIdentity:
    sender = getattr(event, "sender", None)
    nickname = str(getattr(sender, "nickname", "") or "").strip()
    group_card = str(getattr(sender, "card", "") or "").strip() or None
    qq_id = str(event.user_id)
    return EventIdentity(
        qq_id=qq_id,
        nickname=nickname or qq_id,
        group_card=group_card,
    )


def conversation_scope(event: MessageEvent) -> tuple[str, str, str]:
    if isinstance(event, GroupMessageEvent):
        scope_id = str(event.group_id)
        return f"group:{scope_id}", "group", scope_id
    scope_id = str(event.user_id)
    return f"private:{scope_id}", "private", scope_id


def conversation_keys(event: MessageEvent) -> tuple[str, str]:
    conversation_key, _, _ = conversation_scope(event)
    return conversation_key, f"user:{event.user_id}"
