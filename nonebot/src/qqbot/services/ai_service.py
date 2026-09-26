from __future__ import annotations

import asyncio
import contextlib
import json
import math
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import httpx
from nonebot import logger

from qqbot.config import Settings, get_settings
from qqbot.database import Database, database
from qqbot.services.prompt_service import PromptBuilder
from qqbot.services.skill_service import LocalSkillRegistry


class AIServiceError(RuntimeError):
    """Base error safe for plugin-level handling."""


class AIDisabledError(AIServiceError):
    pass


class AINotConfiguredError(AIServiceError):
    pass


class AIRateLimitError(AIServiceError):
    pass


class AIUnavailableError(AIServiceError):
    pass


class AIDuplicateMessageError(AIServiceError):
    pass


class AICooldownError(AIServiceError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("AI request is cooling down")
        self.retry_after = retry_after


def _read_summary_prompt(path: Path) -> str:
    fallback = (
        "把提供的旧摘要和对话压缩成准确的中文长期摘要。"
        "保留人物、偏好、决定和未完成事项；不编造，不记录秘密。"
    )
    try:
        if path.is_symlink() or not path.is_file():
            return fallback
        if path.stat().st_size > 64 * 1024:
            return fallback
        return path.read_text(encoding="utf-8").strip() or fallback
    except (OSError, UnicodeError):
        return fallback


class AIService:
    """Persistent OpenAI-compatible chat service.

    The provider remains stateless from the bot's point of view. Every request
    is rebuilt from SQLite history, a rolling summary and matching local Skills.
    """

    _SKILL_ROUTING_MESSAGES = 6
    _SKILL_ROUTING_MESSAGE_CHARS = 1000
    _MAX_RESPONSE_BYTES = 1024 * 1024

    def __init__(
        self,
        settings: Settings | None = None,
        db: Database | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.database = db or database
        self.prompt_builder = PromptBuilder(self.settings)
        self.skill_registry = LocalSkillRegistry(self.settings.ai_skills_path)
        self._summary_prompt = _read_summary_prompt(
            self.settings.ai_summary_prompt_path
        )
        self._client: httpx.AsyncClient | None = None
        self._semaphore = asyncio.Semaphore(self.settings.ai_max_concurrency)
        self._cooldown_lock = asyncio.Lock()
        self._last_request: OrderedDict[str, float] = OrderedDict()
        self._conversation_locks: dict[str, asyncio.Lock] = {}
        self._summary_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=64)
        self._summary_pending: set[str] = set()
        self._summary_pending_lock = asyncio.Lock()
        self._summary_worker_task: asyncio.Task[None] | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            timeout = httpx.Timeout(
                self.settings.ai_timeout_seconds,
                connect=min(10, self.settings.ai_timeout_seconds),
            )
            self._client = httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=False,
                limits=httpx.Limits(
                    max_connections=self.settings.ai_max_concurrency,
                    max_keepalive_connections=self.settings.ai_max_concurrency,
                ),
            )
        return self._client

    def _conversation_lock(self, conversation_key: str) -> asyncio.Lock:
        lock = self._conversation_locks.get(conversation_key)
        if lock is None:
            lock = asyncio.Lock()
            self._conversation_locks[conversation_key] = lock
        return lock

    async def close(self) -> None:
        if self._summary_worker_task is not None:
            self._summary_worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._summary_worker_task
            self._summary_worker_task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _enforce_cooldown(self, user_key: str) -> None:
        if self.settings.ai_cooldown_seconds <= 0:
            return
        now = time.monotonic()
        async with self._cooldown_lock:
            previous = self._last_request.get(user_key)
            if previous is not None:
                remaining = self.settings.ai_cooldown_seconds - (now - previous)
                if remaining > 0:
                    raise AICooldownError(math.ceil(remaining))
            self._last_request[user_key] = now
            self._last_request.move_to_end(user_key)
            while len(self._last_request) > 4096:
                self._last_request.popitem(last=False)

    async def _request_chat(self, messages: list[dict[str, str]]) -> str:
        payload: dict[str, Any] = {
            "model": self.settings.ai_model,
            "messages": messages,
        }
        headers = {
            "authorization": f"Bearer {self.settings.ai_api_key}",
            "content-type": "application/json",
        }

        async with self._semaphore:
            try:
                # httpx bounds each socket operation, not the entire request.
                # Also bound decoded response bytes before parsing JSON.
                async with asyncio.timeout(self.settings.ai_timeout_seconds):
                    async with self._get_client().stream(
                        "POST",
                        self.settings.ai_chat_completions_url,
                        json=payload,
                        headers=headers,
                    ) as response:
                        if response.status_code == 429:
                            logger.warning("AI provider returned rate limit")
                            raise AIRateLimitError("AI provider rate limited")
                        if response.status_code >= 500:
                            logger.warning(
                                "AI provider returned HTTP {}", response.status_code
                            )
                            raise AIUnavailableError("AI provider unavailable")
                        if not 200 <= response.status_code < 300:
                            logger.warning(
                                "AI provider rejected request with HTTP {}",
                                response.status_code,
                            )
                            raise AIServiceError("AI provider rejected request")
                        content_type = response.headers.get("content-type", "")
                        media_type = content_type.split(";", 1)[0].strip().lower()
                        if media_type != "application/json" and not (
                            media_type.startswith("application/")
                            and media_type.endswith("+json")
                        ):
                            raise AIServiceError("Invalid AI response content type")
                        body = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            if len(body) + len(chunk) > self._MAX_RESPONSE_BYTES:
                                raise AIServiceError("AI response exceeds size limit")
                            body.extend(chunk)
            except (TimeoutError, httpx.TimeoutException) as exc:
                logger.warning("AI request timed out")
                raise AIUnavailableError("AI request timed out") from exc
            except httpx.RequestError as exc:
                logger.warning(
                    "AI provider connection failed: {}",
                    type(exc).__name__,
                )
                raise AIUnavailableError("AI provider unavailable") from exc

        try:
            data = json.loads(body)
            message = data["choices"][0]["message"]
            content = message["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            logger.warning("AI provider returned an invalid response schema")
            raise AIServiceError("Invalid AI response") from exc
        if not isinstance(content, str) or not content.strip():
            raise AIServiceError("AI provider returned an empty response")
        return content.strip()

    @classmethod
    def _skill_routing_text(
        cls,
        content: str,
        history: list[dict[str, Any]],
    ) -> str:
        parts: list[str] = []
        for message in history[-cls._SKILL_ROUTING_MESSAGES :]:
            if str(message.get("role", "")) not in {"user", "assistant"}:
                continue
            text = str(message.get("content", "")).strip()
            if text:
                parts.append(text[: cls._SKILL_ROUTING_MESSAGE_CHARS])
        if not parts or parts[-1] != content:
            parts.append(content[: cls._SKILL_ROUTING_MESSAGE_CHARS])
        return "\n".join(parts)

    async def complete(
        self,
        conversation_key: str,
        user_key: str,
        prompt: str,
        *,
        qq_id: str | None = None,
        nickname: str | None = None,
        conversation_kind: str | None = None,
        scope_id: str | None = None,
        group_card: str | None = None,
        source_message_id: str | None = None,
    ) -> str:
        if not self.settings.ai_enabled:
            raise AIDisabledError("AI is disabled")
        if not self.settings.ai_configured:
            raise AINotConfiguredError("AI is not configured")
        content = prompt.strip()
        if not content:
            raise AIServiceError("Prompt is empty")

        inferred_kind, _, inferred_scope = conversation_key.partition(":")
        safe_kind = (
            conversation_kind
            if conversation_kind in {"private", "group"}
            else inferred_kind
        )
        if safe_kind not in {"private", "group"}:
            safe_kind = "private"
        safe_scope = scope_id or inferred_scope or conversation_key
        safe_qq_id = qq_id or user_key.removeprefix("user:") or safe_scope
        safe_nickname = (nickname or safe_qq_id).strip() or safe_qq_id

        async with self._conversation_lock(conversation_key):
            await self.database.upsert_identity(
                safe_qq_id,
                safe_nickname,
                group_id=safe_scope if safe_kind == "group" else None,
                group_card=group_card,
            )
            user_message_id, inserted = await self.database.add_user_message(
                conversation_key=conversation_key,
                content=content,
                qq_id=safe_qq_id,
                nickname=safe_nickname,
                source_message_id=source_message_id,
                scope_type=safe_kind,
                scope_id=safe_scope,
            )
            if not inserted:
                raise AIDuplicateMessageError("Duplicate OneBot message")

            await self._enforce_cooldown(user_key)
            summary = await self.database.get_summary(conversation_key)
            through_id = int(summary["through_message_id"]) if summary else 0
            history = await self.database.get_context_messages(
                conversation_key,
                self.settings.ai_max_history_messages,
                after_message_id=through_id,
                up_to_message_id=user_message_id,
            )
            skills_text = self.skill_registry.render_for_message(
                self._skill_routing_text(content, history),
                safe_kind,
                self.settings.ai_skills_max_total_chars,
            )
            messages = self.prompt_builder.build(
                context_kind=safe_kind,
                nickname=safe_nickname,
                summary=str(summary["content"]) if summary else "",
                history=history,
                skills_text=skills_text,
            )
            reply = await self._request_chat(messages)
            if len(reply) > self.settings.ai_max_reply_chars:
                reply = reply[: self.settings.ai_max_reply_chars].rstrip() + "…"

            await self.database.add_assistant_message(
                conversation_key=conversation_key,
                content=reply,
                parent_message_id=user_message_id,
                route_plugin="ai_chat",
            )
            await self._schedule_summary(conversation_key)
            return reply

    async def clear_context(self, conversation_key: str) -> int:
        # Finish in-flight replies and summaries in their original epoch before
        # acknowledging a reset, so old content cannot leak into the new one.
        async with self._conversation_lock(conversation_key):
            return await self.database.advance_conversation_epoch(conversation_key)

    async def _schedule_summary(self, conversation_key: str) -> None:
        async with self._summary_pending_lock:
            if conversation_key in self._summary_pending:
                return
            try:
                self._summary_queue.put_nowait(conversation_key)
            except asyncio.QueueFull:
                logger.warning("AI summary queue is full; summary deferred")
                return
            self._summary_pending.add(conversation_key)
            if (
                self._summary_worker_task is None
                or self._summary_worker_task.done()
            ):
                self._summary_worker_task = asyncio.create_task(
                    self._summary_worker(),
                    name="qqbot-ai-summary-worker",
                )

    async def _summary_worker(self) -> None:
        while True:
            conversation_key = await self._summary_queue.get()
            try:
                async with self._conversation_lock(conversation_key):
                    await self._summarize_if_needed(conversation_key)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "AI summary deferred after {}",
                    type(exc).__name__,
                )
            finally:
                async with self._summary_pending_lock:
                    self._summary_pending.discard(conversation_key)
                self._summary_queue.task_done()

    async def _summarize_if_needed(self, conversation_key: str) -> None:
        previous, batch = await self.database.get_summary_batch(
            conversation_key,
            self.settings.ai_summary_trigger_messages,
            self.settings.ai_summary_keep_recent_messages,
        )
        if not batch:
            return

        transcript_lines: list[str] = []
        for message in batch:
            label = (
                "机器人"
                if message["role"] == "assistant"
                else str(message.get("speaker_nickname") or "用户")
            )
            transcript_lines.append(f"{label}：{message['content']}")

        previous_text = str(previous["content"]) if previous else "（无旧摘要）"
        summary_request = (
            "旧摘要：\n"
            f"{previous_text}\n\n"
            "需要合并的新对话：\n"
            + "\n".join(transcript_lines)
        )
        summary_text = await self._request_chat(
            [
                {"role": "system", "content": self._summary_prompt},
                {"role": "user", "content": summary_request},
            ]
        )
        if len(summary_text) > self.settings.ai_summary_max_chars:
            summary_text = (
                summary_text[: self.settings.ai_summary_max_chars].rstrip() + "…"
            )
        await self.database.save_summary(
            conversation_key=conversation_key,
            through_message_id=int(batch[-1]["id"]),
            content=summary_text,
            model=self.settings.ai_model,
            prompt_version=self.prompt_builder.prompt_version,
        )

    async def wait_for_background(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(self._summary_queue.join(), timeout=timeout)


ai_service = AIService()
