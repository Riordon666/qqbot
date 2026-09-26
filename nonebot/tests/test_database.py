from __future__ import annotations

import sqlite3
import os

from qqbot.database import Database


async def test_database_initializes_v2_wal_and_is_idempotent(tmp_path) -> None:
    db = Database()
    path = tmp_path / "bot.db"

    await db.connect(path)
    await db.connect(path)

    assert await db.healthy()
    assert await db.schema_version() == 2
    assert str(await db.pragma("journal_mode")).lower() == "wal"
    assert int(await db.pragma("busy_timeout")) == 5000
    assert int(await db.pragma("foreign_keys")) == 1
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600

    await db.close()
    assert not await db.healthy()


async def test_every_exchange_is_persisted_and_epoch_reset_keeps_archive(
    tmp_path,
) -> None:
    db = Database()
    await db.connect(tmp_path / "bot.db")

    for number in range(3):
        await db.add_ai_exchange(
            "private:1",
            f"user-{number}",
            f"assistant-{number}",
            keep_messages=2,
        )

    assert await db.message_count("private:1") == 6
    assert len(await db.get_ai_history("private:1", 20)) == 6

    assert await db.clear_ai_history("private:1") == 6
    assert await db.message_count("private:1") == 6
    assert await db.get_ai_history("private:1", 20) == []

    await db.add_ai_exchange("private:1", "new", "new-reply", keep_messages=2)
    assert await db.message_count("private:1") == 8
    assert await db.get_ai_history("private:1", 20) == [
        {"role": "user", "content": "new"},
        {"role": "assistant", "content": "new-reply"},
    ]
    await db.close()


async def test_source_message_is_idempotent_and_identity_updates(tmp_path) -> None:
    db = Database()
    await db.connect(tmp_path / "bot.db")
    await db.upsert_identity("123", "旧昵称")
    await db.upsert_identity("123", "新昵称", group_id="456", group_card="群名片")

    first_id, inserted = await db.add_user_message(
        "group:456",
        "hello",
        "123",
        "新昵称",
        "message-1",
        scope_type="group",
        scope_id="456",
    )
    duplicate_id, duplicate_inserted = await db.add_user_message(
        "group:456",
        "hello",
        "123",
        "新昵称",
        "message-1",
        scope_type="group",
        scope_id="456",
    )
    assert inserted is True
    assert duplicate_inserted is False
    assert duplicate_id == first_id
    assert await db.message_count("group:456") == 1
    await db.close()


async def test_v1_history_migrates_without_loss(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT INTO schema_meta VALUES ('schema_version', '1');
        CREATE TABLE ai_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_key TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO ai_messages(conversation_key, role, content)
        VALUES ('private:9', 'user', 'legacy user');
        INSERT INTO ai_messages(conversation_key, role, content)
        VALUES ('private:9', 'assistant', 'legacy reply');
        """
    )
    connection.commit()
    connection.close()

    db = Database()
    await db.connect(path)
    assert await db.schema_version() == 2
    assert await db.get_ai_history("private:9", 10) == [
        {"role": "user", "content": "legacy user"},
        {"role": "assistant", "content": "legacy reply"},
    ]
    await db.close()


async def test_non_chat_plugin_messages_are_idempotent_but_excluded_from_context(
    tmp_path,
) -> None:
    db = Database()
    await db.connect(tmp_path / "bot.db")

    user_id, inserted = await db.add_user_message(
        "group:456",
        "lookup current weather",
        "123",
        "test-user",
        "lookup-message-1",
        scope_type="group",
        scope_id="456",
        route_plugin="example_lookup",
        include_in_context=False,
    )
    await db.add_assistant_message(
        "group:456",
        "verified external facts",
        user_id,
        route_plugin="example_lookup",
        include_in_context=False,
    )
    duplicate_id, duplicate_inserted = await db.add_user_message(
        "group:456",
        "lookup current weather",
        "123",
        "test-user",
        "lookup-message-1",
        route_plugin="example_lookup",
        include_in_context=False,
    )

    assert inserted is True
    assert duplicate_inserted is False
    assert duplicate_id == user_id
    assert await db.message_count("group:456") == 2
    assert await db.get_context_messages("group:456", 20) == []
    await db.close()
