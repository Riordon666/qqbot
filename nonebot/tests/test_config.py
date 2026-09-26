from __future__ import annotations

import pytest

from qqbot.config import get_settings


_ENV_NAMES = (
    "BOT_NAME",
    "BOT_NICKNAME",
    "SUPERUSERS",
    "COMMAND_START",
    "BOT_TIMEZONE",
    "ALLOWED_GROUPS",
    "BLOCKED_GROUPS",
    "LOG_LEVEL",
    "DATABASE_PATH",
    "AI_ENABLED",
    "PRIVATE_AI_ENABLED",
    "AI_PRIVATE_MODE",
    "AI_GROUP_MODE",
    "AI_BASE_URL",
    "AI_API_KEY",
    "AI_MODEL",
    "AI_TIMEOUT_SECONDS",
    "AI_MAX_HISTORY_MESSAGES",
    "AI_MAX_CONTEXT_CHARS",
    "AI_MAX_REPLY_CHARS",
    "AI_COOLDOWN_SECONDS",
    "AI_MAX_CONCURRENCY",
    "AI_SUMMARY_TRIGGER_MESSAGES",
    "AI_SUMMARY_KEEP_RECENT_MESSAGES",
    "AI_SUMMARY_MAX_CHARS",
    "AI_SKILLS_MAX_TOTAL_CHARS",
    "AI_SYSTEM_PROMPT_PATH",
    "AI_PERSONA_PROMPT_PATH",
    "AI_SUMMARY_PROMPT_PATH",
    "AI_SKILLS_PATH",
)


@pytest.fixture(autouse=True)
def clear_settings(monkeypatch: pytest.MonkeyPatch):
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_keep_ai_disabled_but_chat_ready() -> None:
    settings = get_settings()
    assert settings.command_start == frozenset({"/"})
    assert settings.ai_enabled is False
    assert settings.ai_configured is False
    assert settings.ai_private_mode == "all"
    assert settings.ai_group_mode == "mention"
    assert settings.allowed_groups == frozenset()


def test_lists_and_group_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_NICKNAME", '["小助手", "QQBot"]')
    monkeypatch.setenv("SUPERUSERS", "10001,10002")
    monkeypatch.setenv("ALLOWED_GROUPS", "20001,20002")
    monkeypatch.setenv("BLOCKED_GROUPS", "20002")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.bot_nickname == frozenset({"小助手", "QQBot"})
    assert settings.superusers == frozenset({"10001", "10002"})
    assert settings.group_allowed(20001)
    assert not settings.group_allowed(20002)
    assert not settings.group_allowed(29999)


def test_invalid_modes_and_summary_window_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_GROUP_MODE", "everywhere")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="AI_GROUP_MODE"):
        get_settings()

    monkeypatch.setenv("AI_GROUP_MODE", "mention")
    monkeypatch.setenv("AI_SUMMARY_TRIGGER_MESSAGES", "8")
    monkeypatch.setenv("AI_SUMMARY_KEEP_RECENT_MESSAGES", "8")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="must be smaller"):
        get_settings()


def test_invalid_integer_list_fails_without_echoing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOWED_GROUPS", "not-a-number")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="ALLOWED_GROUPS contains an invalid value"):
        get_settings()


def test_secret_values_are_not_in_settings_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_secret = "ai-secret-sentinel-12345678"
    monkeypatch.setenv("AI_API_KEY", ai_secret)
    get_settings.cache_clear()

    rendered = repr(get_settings())
    assert ai_secret not in rendered
