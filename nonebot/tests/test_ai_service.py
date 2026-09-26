from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from qqbot.config import get_settings
from qqbot.database import Database
from qqbot.services.ai_service import (
    AIDisabledError,
    AIDuplicateMessageError,
    AINotConfiguredError,
    AIRateLimitError,
    AIService,
    AIServiceError,
    AIUnavailableError,
)


@pytest.fixture(autouse=True)
def reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _configure_ai(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prompts = tmp_path / "prompts"
    skills = tmp_path / "skills"
    prompts.mkdir(exist_ok=True)
    skills.mkdir(exist_ok=True)
    prompts.joinpath("core.md").write_text("CORE_RULE", encoding="utf-8")
    prompts.joinpath("persona.md").write_text("PERSONA_RULE", encoding="utf-8")
    prompts.joinpath("summary.md").write_text("SUMMARY_RULE", encoding="utf-8")

    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("AI_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_MODEL", "test-model")
    monkeypatch.setenv("AI_API_KEY", "unit-test-credential")
    monkeypatch.setenv("AI_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("AI_SUMMARY_TRIGGER_MESSAGES", "8")
    monkeypatch.setenv("AI_SUMMARY_KEEP_RECENT_MESSAGES", "2")
    monkeypatch.setenv("AI_SYSTEM_PROMPT_PATH", str(prompts / "core.md"))
    monkeypatch.setenv("AI_PERSONA_PROMPT_PATH", str(prompts / "persona.md"))
    monkeypatch.setenv("AI_SUMMARY_PROMPT_PATH", str(prompts / "summary.md"))
    monkeypatch.setenv("AI_SKILLS_PATH", str(skills))
    get_settings.cache_clear()


async def test_disabled_ai_never_touches_database() -> None:
    service = AIService(settings=get_settings(), db=Database())
    with pytest.raises(AIDisabledError):
        await service.complete("group:1", "user:1", "hello")
    await service.close()


async def test_enabled_but_missing_key_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("AI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("AI_MODEL", "example")
    monkeypatch.delenv("AI_API_KEY", raising=False)
    get_settings.cache_clear()

    service = AIService(settings=get_settings(), db=Database())
    with pytest.raises(AINotConfiguredError):
        await service.complete("group:1", "user:1", "hello")
    await service.close()


async def test_request_contains_identity_and_persistent_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_ai(monkeypatch, tmp_path)
    db = Database()
    await db.connect(tmp_path / "bot.db")
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(
            {
                "url": str(request.url),
                "authorization": request.headers.get("authorization"),
                "json": json.loads(request.content),
            }
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": f"reply-{len(captured)}"}}]},
        )

    service = AIService(settings=get_settings(), db=db)
    service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    first = await service.complete(
        "private:456",
        "user:456",
        "hello",
        qq_id="456",
        nickname="小明",
        conversation_kind="private",
        scope_id="456",
        source_message_id="m1",
    )
    second = await service.complete(
        "private:456",
        "user:456",
        "继续",
        qq_id="456",
        nickname="新昵称",
        conversation_kind="private",
        scope_id="456",
        source_message_id="m2",
    )

    assert first == "reply-1"
    assert second == "reply-2"
    assert captured[0]["url"] == "https://provider.example/v1/chat/completions"
    assert captured[0]["authorization"] == "Bearer unit-test-credential"

    first_body = captured[0]["json"]
    assert isinstance(first_body, dict)
    assert "tools" not in first_body
    first_messages = first_body["messages"]
    assert first_messages[0]["role"] == "system"
    assert "CORE_RULE" in first_messages[0]["content"]
    assert "PERSONA_RULE" in first_messages[0]["content"]
    assert "小明" not in first_messages[0]["content"]
    assert first_messages[-1] == {
        "role": "user",
        "content": "[昵称资料：小明]\nhello",
    }

    second_body = captured[1]["json"]
    assert isinstance(second_body, dict)
    second_messages = second_body["messages"]
    assert {"role": "assistant", "content": "reply-1"} in second_messages
    assert second_messages[-1] == {
        "role": "user",
        "content": "[昵称资料：新昵称]\n继续",
    }
    assert "新昵称" not in second_messages[0]["content"]

    assert await db.get_ai_history("private:456", 10) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "reply-1"},
        {"role": "user", "content": "继续"},
        {"role": "assistant", "content": "reply-2"},
    ]

    await service.close()
    await db.close()


async def test_provider_failure_still_persists_user_sentence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_ai(monkeypatch, tmp_path)
    db = Database()
    await db.connect(tmp_path / "bot.db")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    service = AIService(settings=get_settings(), db=db)
    service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(AIUnavailableError):
        await service.complete(
            "private:1",
            "user:1",
            "这句话不能丢",
            qq_id="1",
            nickname="用户",
            source_message_id="failed-message",
        )

    assert await db.get_ai_history("private:1", 10) == [
        {"role": "user", "content": "这句话不能丢"}
    ]
    await service.close()
    await db.close()


async def test_duplicate_message_does_not_call_provider_twice(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_ai(monkeypatch, tmp_path)
    db = Database()
    await db.connect(tmp_path / "bot.db")
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
        )

    service = AIService(settings=get_settings(), db=db)
    service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    arguments = {
        "qq_id": "1",
        "nickname": "用户",
        "source_message_id": "same-message",
    }
    assert await service.complete("private:1", "user:1", "hello", **arguments) == "ok"
    with pytest.raises(AIDuplicateMessageError):
        await service.complete("private:1", "user:1", "hello", **arguments)
    assert calls == 1
    await service.close()
    await db.close()


async def test_rolling_summary_keeps_raw_messages(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_ai(monkeypatch, tmp_path)
    db = Database()
    await db.connect(tmp_path / "bot.db")
    for number in range(4):
        await db.add_ai_exchange(
            "private:7",
            f"user-{number}",
            f"assistant-{number}",
            keep_messages=2,
        )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["messages"][0]["content"] == "SUMMARY_RULE"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "durable summary"}}]},
        )

    service = AIService(settings=get_settings(), db=db)
    service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await service._summarize_if_needed("private:7")

    summary = await db.get_summary("private:7")
    assert summary is not None
    assert summary["content"] == "durable summary"
    assert await db.message_count("private:7") == 8
    await service.close()
    await db.close()


@pytest.mark.parametrize(
    ("status", "error_type"),
    ((429, AIRateLimitError), (503, AIUnavailableError), (400, AIServiceError)),
)
async def test_provider_errors_are_classified_without_response_body_leaks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: int,
    error_type: type[AIServiceError],
) -> None:
    _configure_ai(monkeypatch, tmp_path)
    db = Database()
    await db.connect(tmp_path / f"bot-{status}.db")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="provider-private-details")

    service = AIService(settings=get_settings(), db=db)
    service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(error_type, match="provider|rate limited") as error:
        await service.complete("private:8", "user:8", "hello", qq_id="8")
    assert "provider-private-details" not in str(error.value)
    await service.close()
    await db.close()


async def test_invalid_provider_schema_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_ai(monkeypatch, tmp_path)
    db = Database()
    await db.connect(tmp_path / "invalid.db")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    service = AIService(settings=get_settings(), db=db)
    service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(AIServiceError, match="Invalid AI response"):
        await service.complete("private:9", "user:9", "hello", qq_id="9")
    await service.close()
    await db.close()


@pytest.mark.parametrize("inflight_kind", ("reply", "summary"))
async def test_reset_waits_for_inflight_work_and_keeps_new_epoch_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    inflight_kind: str,
) -> None:
    _configure_ai(monkeypatch, tmp_path)
    db = Database()
    await db.connect(tmp_path / "reset.db")
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(_: httpx.Request) -> httpx.Response:
        started.set()
        await release.wait()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "old conversation data"}}]},
        )

    service = AIService(settings=get_settings(), db=db)
    service._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    if inflight_kind == "summary":
        for number in range(4):
            await db.add_ai_exchange(
                "private:7", f"user-{number}", f"reply-{number}", keep_messages=2
            )
        await service._schedule_summary("private:7")
        task = None
    else:
        task = asyncio.create_task(
            service.complete("private:7", "user:7", "hello", qq_id="7")
        )
    await asyncio.wait_for(started.wait(), timeout=2)
    reset = asyncio.create_task(service.clear_context("private:7"))
    try:
        await asyncio.sleep(0)
        assert not reset.done(), "reset must wait for the old epoch writer"
        release.set()
        if task is not None:
            await task
        await asyncio.wait_for(reset, timeout=2)
        await service.wait_for_background()
        assert await db.get_ai_history("private:7", 10) == []
        assert await db.get_summary("private:7") is None
        assert await db.message_count("private:7") > 0
    finally:
        release.set()
        await service.close()
        await db.close()


async def test_provider_body_is_bounded_and_stream_is_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_ai(monkeypatch, tmp_path)

    class OversizedStream(httpx.AsyncByteStream):
        consumed = 0
        closed = False

        async def __aiter__(self):
            for _ in range(64):
                self.consumed += 1
                yield b"x" * 65536

        async def aclose(self):
            self.closed = True

    stream = OversizedStream()
    service = AIService(settings=get_settings(), db=Database())
    service._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"content-type": "application/json"}, stream=stream
            )
        )
    )
    try:
        with pytest.raises(AIServiceError, match="size limit"):
            await service._request_chat([{"role": "user", "content": "hello"}])
        assert stream.closed
        assert stream.consumed < 64
    finally:
        await service.close()


async def test_provider_total_deadline_stops_slow_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_ai(monkeypatch, tmp_path)

    class SlowStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            while True:
                await asyncio.sleep(0.005)
                yield b" "

        async def aclose(self):
            self.closed = True

    stream = SlowStream()
    service = AIService(
        settings=replace(get_settings(), ai_timeout_seconds=0.03), db=Database()
    )
    service._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"content-type": "application/json"}, stream=stream
            )
        )
    )
    try:
        with pytest.raises(AIUnavailableError, match="timed out"):
            await asyncio.wait_for(
                service._request_chat([{"role": "user", "content": "hello"}]),
                timeout=2,
            )
        assert stream.closed
    finally:
        await service.close()


@pytest.mark.parametrize(
    ("status", "content_type"),
    ((200, "text/html"), (302, "application/json")),
)
async def test_provider_rejects_redirects_and_non_json_responses(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    status: int,
    content_type: str,
) -> None:
    _configure_ai(monkeypatch, tmp_path)
    service = AIService(settings=get_settings(), db=Database())
    service._client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                status,
                headers={"content-type": content_type},
                json={"choices": [{"message": {"content": "must not be accepted"}}]},
            )
        )
    )
    try:
        with pytest.raises(AIServiceError):
            await service._request_chat([{"role": "user", "content": "hello"}])
    finally:
        await service.close()
