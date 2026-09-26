from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import aiosqlite


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO schema_meta(key, value)
VALUES ('schema_version', '1')
ON CONFLICT(key) DO NOTHING;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_migrations(version) VALUES (1);

CREATE TABLE IF NOT EXISTS group_settings (
    group_id INTEGER PRIMARY KEY,
    config_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    config_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_key TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation
ON ai_messages(conversation_key, id DESC);

CREATE TABLE IF NOT EXISTS ai_users (
    qq_id TEXT PRIMARY KEY,
    current_nickname TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_group_members (
    group_id TEXT NOT NULL,
    qq_id TEXT NOT NULL,
    current_nickname TEXT NOT NULL,
    current_group_card TEXT,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(group_id, qq_id),
    FOREIGN KEY(qq_id) REFERENCES ai_users(qq_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_conversations (
    conversation_key TEXT PRIMARY KEY,
    scope_type TEXT NOT NULL CHECK(scope_type IN ('private', 'group')),
    scope_id TEXT NOT NULL,
    active_epoch INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_key TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    speaker_qq_id TEXT,
    speaker_nickname TEXT,
    content TEXT NOT NULL,
    source_message_id TEXT,
    parent_message_id INTEGER,
    route_plugin TEXT NOT NULL DEFAULT 'ai_chat',
    include_in_context INTEGER NOT NULL DEFAULT 1
        CHECK(include_in_context IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(conversation_key)
        REFERENCES ai_conversations(conversation_key) ON DELETE CASCADE,
    FOREIGN KEY(parent_message_id)
        REFERENCES ai_conversation_messages(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_conversation_context
ON ai_conversation_messages(conversation_key, epoch, include_in_context, id DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_conversation_source
ON ai_conversation_messages(conversation_key, source_message_id)
WHERE source_message_id IS NOT NULL AND role = 'user';

CREATE TABLE IF NOT EXISTS ai_conversation_summaries (
    conversation_key TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    through_message_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    model TEXT,
    prompt_version TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(conversation_key, epoch),
    FOREIGN KEY(conversation_key)
        REFERENCES ai_conversations(conversation_key) ON DELETE CASCADE
);
"""


def _scope_from_key(conversation_key: str) -> tuple[str, str]:
    scope_type, separator, scope_id = conversation_key.partition(":")
    if separator and scope_type in {"private", "group"} and scope_id:
        return scope_type, scope_id
    return "private", conversation_key


class Database:
    def __init__(self) -> None:
        self._connection: aiosqlite.Connection | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._path: Path | None = None

    @property
    def path(self) -> Path | None:
        return self._path

    async def connect(self, path: Path) -> None:
        async with self._lifecycle_lock:
            if self._connection is not None:
                return

            path.parent.mkdir(parents=True, exist_ok=True)
            connection = await aiosqlite.connect(path, timeout=5.0)
            connection.row_factory = aiosqlite.Row
            try:
                await connection.execute("PRAGMA foreign_keys = ON")
                await connection.execute("PRAGMA busy_timeout = 5000")
                await connection.execute("PRAGMA synchronous = NORMAL")
                await connection.execute("PRAGMA journal_mode = WAL")
                await connection.executescript(_SCHEMA)
                await self._migrate_legacy_history(connection)
                await connection.commit()
                for database_file in (
                    path,
                    Path(f"{path}-wal"),
                    Path(f"{path}-shm"),
                ):
                    if database_file.exists():
                        database_file.chmod(0o600)
            except Exception:
                await connection.close()
                raise

            self._connection = connection
            self._path = path

    async def _migrate_legacy_history(
        self,
        connection: aiosqlite.Connection,
    ) -> None:
        cursor = await connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version = 2"
        )
        already_applied = await cursor.fetchone()
        await cursor.close()
        if already_applied:
            return

        await connection.execute("BEGIN IMMEDIATE")
        try:
            await connection.execute(
                """
                INSERT OR IGNORE INTO ai_conversations(
                    conversation_key, scope_type, scope_id
                )
                SELECT DISTINCT
                    conversation_key,
                    CASE
                        WHEN conversation_key LIKE 'group:%' THEN 'group'
                        ELSE 'private'
                    END,
                    substr(conversation_key, instr(conversation_key, ':') + 1)
                FROM ai_messages
                """
            )
            await connection.execute(
                """
                INSERT INTO ai_conversation_messages(
                    conversation_key,
                    epoch,
                    role,
                    content,
                    route_plugin,
                    include_in_context,
                    created_at
                )
                SELECT
                    conversation_key,
                    1,
                    CASE WHEN role = 'user' THEN 'user' ELSE 'assistant' END,
                    content,
                    'legacy',
                    1,
                    created_at
                FROM ai_messages
                ORDER BY id
                """
            )
            await connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (2)"
            )
            await connection.execute(
                """
                INSERT INTO schema_meta(key, value)
                VALUES ('schema_version', '2')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )
            await connection.commit()
        except Exception:
            await connection.rollback()
            raise

    async def close(self) -> None:
        async with self._lifecycle_lock:
            if self._connection is None:
                return
            await self._connection.commit()
            await self._connection.close()
            self._connection = None
            self._path = None

    def _require_connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database is not initialized")
        return self._connection

    async def healthy(self) -> bool:
        if self._connection is None:
            return False
        try:
            cursor = await self._connection.execute("SELECT 1")
            row = await cursor.fetchone()
            await cursor.close()
            return bool(row and row[0] == 1)
        except aiosqlite.Error:
            return False

    async def _ensure_conversation_locked(
        self,
        connection: aiosqlite.Connection,
        conversation_key: str,
        scope_type: str | None = None,
        scope_id: str | None = None,
    ) -> int:
        inferred_type, inferred_id = _scope_from_key(conversation_key)
        await connection.execute(
            """
            INSERT INTO ai_conversations(
                conversation_key, scope_type, scope_id
            )
            VALUES (?, ?, ?)
            ON CONFLICT(conversation_key) DO UPDATE SET
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                conversation_key,
                scope_type or inferred_type,
                scope_id or inferred_id,
            ),
        )
        cursor = await connection.execute(
            """
            SELECT active_epoch
            FROM ai_conversations
            WHERE conversation_key = ?
            """,
            (conversation_key,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            raise RuntimeError("Conversation could not be initialized")
        return int(row["active_epoch"])

    async def upsert_identity(
        self,
        qq_id: str,
        nickname: str,
        group_id: str | None = None,
        group_card: str | None = None,
    ) -> None:
        connection = self._require_connection()
        safe_nickname = nickname.strip() or qq_id
        async with self._write_lock:
            try:
                await connection.execute(
                    """
                    INSERT INTO ai_users(qq_id, current_nickname)
                    VALUES (?, ?)
                    ON CONFLICT(qq_id) DO UPDATE SET
                        current_nickname = excluded.current_nickname,
                        last_seen_at = CURRENT_TIMESTAMP
                    """,
                    (qq_id, safe_nickname),
                )
                if group_id is not None:
                    await connection.execute(
                        """
                        INSERT INTO ai_group_members(
                            group_id,
                            qq_id,
                            current_nickname,
                            current_group_card
                        )
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(group_id, qq_id) DO UPDATE SET
                            current_nickname = excluded.current_nickname,
                            current_group_card = excluded.current_group_card,
                            last_seen_at = CURRENT_TIMESTAMP
                        """,
                        (group_id, qq_id, safe_nickname, group_card),
                    )
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise

    async def add_user_message(
        self,
        conversation_key: str,
        content: str,
        qq_id: str,
        nickname: str,
        source_message_id: str | None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        route_plugin: str = "ai_chat",
        include_in_context: bool = True,
    ) -> tuple[int, bool]:
        connection = self._require_connection()
        async with self._write_lock:
            try:
                epoch = await self._ensure_conversation_locked(
                    connection,
                    conversation_key,
                    scope_type,
                    scope_id,
                )
                cursor = await connection.execute(
                    """
                    INSERT OR IGNORE INTO ai_conversation_messages(
                        conversation_key,
                        epoch,
                        role,
                        speaker_qq_id,
                        speaker_nickname,
                        content,
                        source_message_id,
                        route_plugin,
                        include_in_context
                    )
                    VALUES (?, ?, 'user', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conversation_key,
                        epoch,
                        qq_id,
                        nickname.strip() or qq_id,
                        content,
                        source_message_id,
                        route_plugin,
                        1 if include_in_context else 0,
                    ),
                )
                inserted = cursor.rowcount == 1
                message_id = int(cursor.lastrowid or 0)
                await cursor.close()
                if not inserted and source_message_id is not None:
                    cursor = await connection.execute(
                        """
                        SELECT id
                        FROM ai_conversation_messages
                        WHERE conversation_key = ?
                          AND source_message_id = ?
                          AND role = 'user'
                        """,
                        (conversation_key, source_message_id),
                    )
                    row = await cursor.fetchone()
                    await cursor.close()
                    if row is None:
                        raise RuntimeError("Duplicate message could not be resolved")
                    message_id = int(row["id"])
                await connection.commit()
                return message_id, inserted
            except Exception:
                await connection.rollback()
                raise

    async def add_assistant_message(
        self,
        conversation_key: str,
        content: str,
        parent_message_id: int,
        route_plugin: str = "ai_chat",
        include_in_context: bool = True,
    ) -> int:
        connection = self._require_connection()
        async with self._write_lock:
            try:
                epoch = await self._ensure_conversation_locked(
                    connection,
                    conversation_key,
                )
                cursor = await connection.execute(
                    """
                    INSERT INTO ai_conversation_messages(
                        conversation_key,
                        epoch,
                        role,
                        content,
                        parent_message_id,
                        route_plugin,
                        include_in_context
                    )
                    VALUES (?, ?, 'assistant', ?, ?, ?, ?)
                    """,
                    (
                        conversation_key,
                        epoch,
                        content,
                        parent_message_id,
                        route_plugin,
                        1 if include_in_context else 0,
                    ),
                )
                message_id = int(cursor.lastrowid)
                await cursor.close()
                await connection.commit()
                return message_id
            except Exception:
                await connection.rollback()
                raise

    async def get_summary(
        self,
        conversation_key: str,
    ) -> dict[str, Any] | None:
        connection = self._require_connection()
        cursor = await connection.execute(
            """
            SELECT
                s.epoch,
                s.through_message_id,
                s.content,
                s.model,
                s.prompt_version
            FROM ai_conversation_summaries AS s
            JOIN ai_conversations AS c
              ON c.conversation_key = s.conversation_key
             AND c.active_epoch = s.epoch
            WHERE s.conversation_key = ?
            """,
            (conversation_key,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return dict(row) if row else None

    async def get_context_messages(
        self,
        conversation_key: str,
        limit: int,
        after_message_id: int = 0,
        up_to_message_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        connection = self._require_connection()
        cursor = await connection.execute(
            """
            SELECT
                m.id,
                m.role,
                m.content,
                m.speaker_qq_id,
                m.speaker_nickname,
                m.route_plugin
            FROM ai_conversation_messages AS m
            JOIN ai_conversations AS c
              ON c.conversation_key = m.conversation_key
             AND c.active_epoch = m.epoch
            WHERE m.conversation_key = ?
              AND m.include_in_context = 1
              AND m.id > ?
              AND (? IS NULL OR m.id <= ?)
            ORDER BY m.id DESC
            LIMIT ?
            """,
            (
                conversation_key,
                after_message_id,
                up_to_message_id,
                up_to_message_id,
                limit,
            ),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(row) for row in reversed(rows)]

    async def get_summary_batch(
        self,
        conversation_key: str,
        trigger_messages: int,
        keep_recent_messages: int,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        summary = await self.get_summary(conversation_key)
        through_id = int(summary["through_message_id"]) if summary else 0
        connection = self._require_connection()
        cursor = await connection.execute(
            """
            SELECT
                m.id,
                m.role,
                m.content,
                m.speaker_nickname
            FROM ai_conversation_messages AS m
            JOIN ai_conversations AS c
              ON c.conversation_key = m.conversation_key
             AND c.active_epoch = m.epoch
            WHERE m.conversation_key = ?
              AND m.include_in_context = 1
              AND m.id > ?
            ORDER BY m.id
            LIMIT ?
            """,
            (
                conversation_key,
                through_id,
                trigger_messages + keep_recent_messages,
            ),
        )
        rows = [dict(row) for row in await cursor.fetchall()]
        await cursor.close()
        if len(rows) < trigger_messages:
            return summary, []
        cutoff = max(1, len(rows) - keep_recent_messages)
        return summary, rows[:cutoff]

    async def save_summary(
        self,
        conversation_key: str,
        through_message_id: int,
        content: str,
        model: str,
        prompt_version: str,
    ) -> None:
        connection = self._require_connection()
        async with self._write_lock:
            try:
                cursor = await connection.execute(
                    """
                    SELECT active_epoch
                    FROM ai_conversations
                    WHERE conversation_key = ?
                    """,
                    (conversation_key,),
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None:
                    return
                epoch = int(row["active_epoch"])
                await connection.execute(
                    """
                    INSERT INTO ai_conversation_summaries(
                        conversation_key,
                        epoch,
                        through_message_id,
                        content,
                        model,
                        prompt_version
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(conversation_key, epoch) DO UPDATE SET
                        through_message_id = excluded.through_message_id,
                        content = excluded.content,
                        model = excluded.model,
                        prompt_version = excluded.prompt_version,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE excluded.through_message_id >
                          ai_conversation_summaries.through_message_id
                    """,
                    (
                        conversation_key,
                        epoch,
                        through_message_id,
                        content,
                        model,
                        prompt_version,
                    ),
                )
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise

    async def advance_conversation_epoch(self, conversation_key: str) -> int:
        connection = self._require_connection()
        async with self._write_lock:
            try:
                epoch = await self._ensure_conversation_locked(
                    connection,
                    conversation_key,
                )
                cursor = await connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM ai_conversation_messages
                    WHERE conversation_key = ? AND epoch = ?
                    """,
                    (conversation_key, epoch),
                )
                row = await cursor.fetchone()
                await cursor.close()
                previous_count = int(row["count"]) if row else 0
                await connection.execute(
                    """
                    UPDATE ai_conversations
                    SET active_epoch = active_epoch + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE conversation_key = ?
                    """,
                    (conversation_key,),
                )
                await connection.commit()
                return previous_count
            except Exception:
                await connection.rollback()
                raise

    async def clear_ai_history(self, conversation_key: str) -> int:
        return await self.advance_conversation_epoch(conversation_key)

    async def get_ai_history(
        self,
        conversation_key: str,
        limit: int,
    ) -> list[dict[str, str]]:
        rows = await self.get_context_messages(conversation_key, limit)
        return [
            {"role": str(row["role"]), "content": str(row["content"])}
            for row in rows
        ]

    async def add_ai_exchange(
        self,
        conversation_key: str,
        user_content: str,
        assistant_content: str,
        keep_messages: int,
    ) -> None:
        if keep_messages <= 0:
            return
        scope_type, scope_id = _scope_from_key(conversation_key)
        message_id, _ = await self.add_user_message(
            conversation_key=conversation_key,
            content=user_content,
            qq_id=scope_id,
            nickname=scope_id,
            source_message_id=None,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        await self.add_assistant_message(
            conversation_key,
            assistant_content,
            message_id,
        )

    async def message_count(self, conversation_key: str) -> int:
        connection = self._require_connection()
        cursor = await connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM ai_conversation_messages
            WHERE conversation_key = ?
            """,
            (conversation_key,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return int(row["count"]) if row else 0

    async def schema_version(self) -> int:
        connection = self._require_connection()
        cursor = await connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        )
        row = await cursor.fetchone()
        await cursor.close()
        return int(row["value"]) if row else 0

    async def pragma(self, name: str) -> Any:
        if name not in {"journal_mode", "busy_timeout", "foreign_keys", "synchronous"}:
            raise ValueError("Unsupported pragma")
        connection = self._require_connection()
        cursor = await connection.execute(f"PRAGMA {name}")
        row = await cursor.fetchone()
        await cursor.close()
        return row[0] if row else None


database = Database()
