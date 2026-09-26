from __future__ import annotations

from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent

from qqbot.config import get_settings
from qqbot.routing import PluginSpec, RouteContext, registry
from qqbot.services.ai_service import (
    AICooldownError,
    AIDisabledError,
    AIDuplicateMessageError,
    AINotConfiguredError,
    AIRateLimitError,
    AIServiceError,
    AIUnavailableError,
    ai_service,
)


settings = get_settings()


def ai_eligible(context: RouteContext) -> bool:
    event = context.event
    if isinstance(event, PrivateMessageEvent):
        return settings.ai_private_mode == "all"
    if isinstance(event, GroupMessageEvent):
        if settings.ai_group_mode == "off":
            return False
        if settings.ai_group_mode == "all":
            return True
        return bool(event.to_me)
    return False


async def handle_clear_context(context: RouteContext) -> str:
    await ai_service.clear_context(context.conversation_key)
    return "已开始新的会话；旧对话仍安全保存在数据库中。"


async def handle_ai_chat(context: RouteContext) -> str | None:
    if not ai_eligible(context):
        return None

    try:
        return await ai_service.complete(
            context.conversation_key,
            f"user:{context.qq_id}",
            context.text,
            qq_id=context.qq_id,
            nickname=context.nickname,
            conversation_kind=context.conversation_kind,
            scope_id=context.scope_id,
            group_card=context.group_card,
            source_message_id=context.source_message_id,
        )
    except AIDuplicateMessageError:
        return None
    except AIDisabledError:
        return "AI 功能尚未启用。"
    except AINotConfiguredError:
        return "AI 功能尚未完成配置。"
    except AICooldownError as exc:
        return f"请求太快，请 {exc.retry_after} 秒后再试。"
    except AIRateLimitError:
        return "AI 服务当前限流，请稍后再试。"
    except AIUnavailableError:
        return "AI 服务暂时不可用，请稍后再试。"
    except AIServiceError:
        return "AI 请求失败，请稍后再试。"


registry.register(
    PluginSpec(
        plugin_id="ai.clear_context",
        name="重置对话",
        description="保留旧记录并开始新的上下文",
        usage="清空上下文 或 重置对话",
        exact=("清空上下文", "重置对话"),
        handler=handle_clear_context,
        category="AI",
        order=20,
    )
)
registry.register(
    PluginSpec(
        plugin_id="ai.chat",
        name="AI 对话",
        description="直接聊天；群聊默认需要 @机器人",
        usage="直接发送聊天内容",
        handler=handle_ai_chat,
        category="AI",
        order=10,
        fallback=True,
    )
)
