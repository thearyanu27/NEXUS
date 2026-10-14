"""Local SQLite storage for separate NEXUS conversations."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path


class ConversationMemoryError(RuntimeError):
    """Raised when the local conversation database cannot be used."""


class ConversationMemory:
    """Store chat sessions and complete message histories on this computer."""

    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA foreign_keys=ON")
                with db:
                    self._create_schema(db)
                    self._migrate_single_chat(db)
                    self._create_message_schema(db)
                    self._title_imported_chats(db)
                    db.execute("""
                        CREATE INDEX IF NOT EXISTS messages_by_conversation
                        ON messages(conversation_id, id)
                    """)
        except (OSError, sqlite3.Error) as exc:
            raise ConversationMemoryError(
                f"Could not open local chat storage at {self.path}: {exc}"
            ) from exc

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def _create_schema(db: sqlite3.Connection) -> None:
        db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

    @staticmethod
    def _create_message_schema(db: sqlite3.Connection) -> None:
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

    @staticmethod
    def _migrate_single_chat(db: sqlite3.Connection) -> None:
        """Move the previous one-transcript schema into a named chat session."""
        columns = {row["name"] for row in db.execute("PRAGMA table_info(messages)")}
        if "position" not in columns or "conversation_id" in columns:
            return
        legacy_id = str(uuid.uuid4())
        db.execute(
            "INSERT INTO conversations(id, title) VALUES (?, ?)",
            (legacy_id, "Previous conversation"),
        )
        db.execute("ALTER TABLE messages RENAME TO messages_legacy")
        ConversationMemory._create_message_schema(db)
        db.execute("""
            INSERT INTO messages(conversation_id, role, content)
            SELECT ?, role, content FROM messages_legacy ORDER BY position
        """, (legacy_id,))
        db.execute("DROP TABLE messages_legacy")

    @staticmethod
    def _title_imported_chats(db: sqlite3.Connection) -> None:
        db.execute("""
            UPDATE conversations
            SET title = (
                SELECT substr(replace(content, char(10), ' '), 1, 48)
                FROM messages
                WHERE messages.conversation_id = conversations.id AND role = 'user'
                ORDER BY id LIMIT 1
            )
            WHERE title = 'Previous conversation'
                AND EXISTS (
                    SELECT 1 FROM messages
                    WHERE messages.conversation_id = conversations.id AND role = 'user'
                )
        """)

    @staticmethod
    def _friendly_error(action: str, exc: sqlite3.Error) -> ConversationMemoryError:
        return ConversationMemoryError(f"Could not {action} local chat history: {exc}")

    def list_conversations(self) -> list[dict[str, str | int]]:
        try:
            with closing(self._connect()) as db:
                rows = db.execute("""
                    SELECT c.id, c.title, c.updated_at, COUNT(m.id) AS message_count
                    FROM conversations AS c
                    LEFT JOIN messages AS m ON m.conversation_id = c.id
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC, c.created_at DESC, c.rowid DESC
                """).fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise self._friendly_error("list", exc) from exc

    def create_conversation(self) -> str:
        chat_id = str(uuid.uuid4())
        try:
            with closing(self._connect()) as db:
                with db:
                    db.execute(
                        "INSERT INTO conversations(id, title) VALUES (?, 'New chat')",
                        (chat_id,),
                    )
            return chat_id
        except sqlite3.Error as exc:
            raise self._friendly_error("create", exc) from exc

    def load(self, chat_id: str) -> list[dict[str, str]]:
        try:
            with closing(self._connect()) as db:
                rows = db.execute(
                    "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
                    (chat_id,),
                ).fetchall()
            return [{"role": row["role"], "content": row["content"]} for row in rows]
        except sqlite3.Error as exc:
            raise self._friendly_error("read", exc) from exc

    def title(self, chat_id: str) -> str:
        try:
            with closing(self._connect()) as db:
                row = db.execute(
                    "SELECT title FROM conversations WHERE id = ?", (chat_id,)
                ).fetchone()
            if row is None:
                raise ConversationMemoryError("That saved conversation no longer exists.")
            return str(row["title"])
        except sqlite3.Error as exc:
            raise self._friendly_error("read", exc) from exc

    def save(self, chat_id: str, messages: Sequence[Mapping[str, str]]) -> None:
        """Replace one transcript and update its title atomically after a full turn."""
        try:
            first_user = next((m["content"].strip() for m in messages if m["role"] == "user"), "")
            title = first_user.replace("\n", " ").strip()[:48] or "New chat"
            with closing(self._connect()) as db:
                with db:
                    existing = db.execute(
                        "SELECT title FROM conversations WHERE id = ?", (chat_id,)
                    ).fetchone()
                    if existing is None:
                        raise ConversationMemoryError("That saved conversation no longer exists.")
                    if existing["title"] != "New chat":
                        title = str(existing["title"])
                    db.execute("DELETE FROM messages WHERE conversation_id = ?", (chat_id,))
                    db.executemany(
                        "INSERT INTO messages(conversation_id, role, content) VALUES (?, ?, ?)",
                        [(chat_id, item["role"], item["content"]) for item in messages],
                    )
                    db.execute("""
                        UPDATE conversations
                        SET title = ?, updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')
                        WHERE id = ?
                    """, (title, chat_id))
        except ConversationMemoryError:
            raise
        except (KeyError, sqlite3.Error) as exc:
            raise self._friendly_error("save", exc) from exc

    def clear(self, chat_id: str) -> None:
        try:
            with closing(self._connect()) as db:
                db.execute("PRAGMA secure_delete=ON")
                with db:
                    db.execute("DELETE FROM messages WHERE conversation_id = ?", (chat_id,))
                    db.execute(
                        "UPDATE conversations SET title = 'New chat', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (chat_id,),
                    )
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error as exc:
            raise self._friendly_error("clear", exc) from exc

    def delete(self, chat_id: str) -> None:
        try:
            with closing(self._connect()) as db:
                with db:
                    db.execute("DELETE FROM conversations WHERE id = ?", (chat_id,))
        except sqlite3.Error as exc:
            raise self._friendly_error("delete", exc) from exc
