from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, TypeVar


T = TypeVar("T")


def _tokens(name: str) -> list[str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return []

    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name} must be a JSON array or comma-separated list") from exc
        if not isinstance(parsed, list):
            raise ValueError(f"{name} must be a JSON array or comma-separated list")
        return [str(item).strip() for item in parsed if str(item).strip()]

    return [item.strip() for item in raw.split(",") if item.strip()]


def _set(name: str, cast: Callable[[str], T]) -> frozenset[T]:
    values: set[T] = set()
    for item in _tokens(name):
        try:
            values.add(cast(item))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} contains an invalid value") from exc
    return frozenset(values)


def _boolean(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    try:
        value = default if raw is None or not raw.strip() else int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _choice(name: str, default: str, allowed: frozenset[str]) -> str:
    raw = os.getenv(name, default).strip().lower() or default
    if raw not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ValueError(f"{name} must be one of: {choices}")
    return raw


@dataclass(frozen=True, slots=True)
class Settings:
    bot_name: str
    bot_nickname: frozenset[str]
    superusers: frozenset[str]
    command_start: frozenset[str]
    bot_timezone: str | None
    allowed_groups: frozenset[int]
    blocked_groups: frozenset[int]
    log_level: str
    database_path: Path

    ai_enabled: bool
    ai_private_mode: str
    ai_group_mode: str
    ai_base_url: str
    ai_api_key: str = field(repr=False)
    ai_model: str
    ai_timeout_seconds: int
    ai_max_history_messages: int
    ai_max_context_chars: int
    ai_max_reply_chars: int
    ai_cooldown_seconds: int
    ai_max_concurrency: int
    ai_summary_trigger_messages: int
    ai_summary_keep_recent_messages: int
    ai_summary_max_chars: int
    ai_skills_max_total_chars: int
    ai_system_prompt_path: Path
    ai_persona_prompt_path: Path
    ai_summary_prompt_path: Path
    ai_skills_path: Path

    @property
    def ai_configured(self) -> bool:
        return bool(self.ai_base_url and self.ai_api_key and self.ai_model)

    @property
    def private_ai_enabled(self) -> bool:
        return self.ai_private_mode == "all"

    @property
    def ai_chat_completions_url(self) -> str:
        if self.ai_base_url.endswith("/chat/completions"):
            return self.ai_base_url
        return f"{self.ai_base_url}/chat/completions"

    def group_allowed(self, group_id: int) -> bool:
        if group_id in self.blocked_groups:
            return False
        return not self.allowed_groups or group_id in self.allowed_groups


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    command_start = _set("COMMAND_START", str) or frozenset({"/"})
    bot_name = os.getenv("BOT_NAME", "QQBot").strip() or "QQBot"
    timezone = os.getenv("BOT_TIMEZONE", "").strip() or None
    if "AI_PRIVATE_MODE" in os.environ:
        private_mode_default = "all"
    elif "PRIVATE_AI_ENABLED" in os.environ:
        private_mode_default = (
            "all" if _boolean("PRIVATE_AI_ENABLED", False) else "off"
        )
    else:
        private_mode_default = "all"

    settings = Settings(
        bot_name=bot_name,
        bot_nickname=_set("BOT_NICKNAME", str),
        superusers=_set("SUPERUSERS", str),
        command_start=command_start,
        bot_timezone=timezone,
        allowed_groups=_set("ALLOWED_GROUPS", int),
        blocked_groups=_set("BLOCKED_GROUPS", int),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        database_path=Path(os.getenv("DATABASE_PATH", "/app/data/bot.db")),
        ai_enabled=_boolean("AI_ENABLED", False),
        ai_private_mode=_choice(
            "AI_PRIVATE_MODE",
            private_mode_default,
            frozenset({"all", "off"}),
        ),
        ai_group_mode=_choice(
            "AI_GROUP_MODE",
            "mention",
            frozenset({"mention", "all", "off"}),
        ),
        ai_base_url=os.getenv("AI_BASE_URL", "").strip().rstrip("/"),
        ai_api_key=os.getenv("AI_API_KEY", "").strip(),
        ai_model=os.getenv("AI_MODEL", "").strip(),
        ai_timeout_seconds=_integer("AI_TIMEOUT_SECONDS", 45, 5, 180),
        ai_max_history_messages=_integer("AI_MAX_HISTORY_MESSAGES", 24, 4, 200),
        ai_max_context_chars=_integer(
            "AI_MAX_CONTEXT_CHARS", 24000, 2000, 200000
        ),
        ai_max_reply_chars=_integer("AI_MAX_REPLY_CHARS", 3000, 100, 12000),
        ai_cooldown_seconds=_integer("AI_COOLDOWN_SECONDS", 2, 0, 3600),
        ai_max_concurrency=_integer("AI_MAX_CONCURRENCY", 5, 1, 20),
        ai_summary_trigger_messages=_integer(
            "AI_SUMMARY_TRIGGER_MESSAGES", 24, 8, 200
        ),
        ai_summary_keep_recent_messages=_integer(
            "AI_SUMMARY_KEEP_RECENT_MESSAGES", 8, 2, 50
        ),
        ai_summary_max_chars=_integer(
            "AI_SUMMARY_MAX_CHARS", 3000, 500, 12000
        ),
        ai_skills_max_total_chars=_integer(
            "AI_SKILLS_MAX_TOTAL_CHARS", 12000, 1000, 64000
        ),
        ai_system_prompt_path=Path(
            os.getenv("AI_SYSTEM_PROMPT_PATH", "/app/prompts/core.md")
        ),
        ai_persona_prompt_path=Path(
            os.getenv("AI_PERSONA_PROMPT_PATH", "/app/prompts/persona.md")
        ),
        ai_summary_prompt_path=Path(
            os.getenv("AI_SUMMARY_PROMPT_PATH", "/app/prompts/summary.md")
        ),
        ai_skills_path=Path(os.getenv("AI_SKILLS_PATH", "/app/skills")),
    )
    if settings.ai_summary_keep_recent_messages >= settings.ai_summary_trigger_messages:
        raise ValueError(
            "AI_SUMMARY_KEEP_RECENT_MESSAGES must be smaller than "
            "AI_SUMMARY_TRIGGER_MESSAGES"
        )
    return settings
