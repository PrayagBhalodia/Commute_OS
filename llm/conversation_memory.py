"""Thread-safe conversation memory with optional SQLite persistence."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from llm.schemas import AutonomyLevel, ConversationState, ConversationTurn

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Session store with write-through SQLite persistence.

    Without a db_path (and COMMUTE_CHAT_DB unset) it behaves exactly like
    the previous in-process dict — used by tests and ad-hoc tooling. The
    API server passes a path so chat sessions survive restarts.
    """

    def __init__(self, max_turns: int = 16, db_path: str | None = None) -> None:
        self.max_turns = max_turns
        self.db_path = db_path or os.environ.get("COMMUTE_CHAT_DB")
        self._sessions: dict[str, ConversationState] = {}
        self._lock = threading.RLock()
        if self.db_path:
            self._init_db()

    # -- persistence -----------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _load(self, session_id: str) -> ConversationState | None:
        if not self.db_path:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            return ConversationState.model_validate_json(row["state_json"])
        except ValueError:
            logger.warning("Discarding unreadable stored chat session %s", session_id)
            return None

    def persist(self, state: ConversationState) -> None:
        if not self.db_path:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (session_id, user_id, state_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (
                    state.session_id,
                    state.user_id,
                    state.model_dump_json(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

    # -- session API -----------------------------------------------------

    def get_or_create(
        self,
        *,
        session_id: str | None,
        user_id: str,
        autonomy_level: AutonomyLevel | None = None,
    ) -> ConversationState:
        with self._lock:
            sid = session_id or f"chat-{uuid.uuid4().hex[:12]}"
            state = self._sessions.get(sid)
            if state is None:
                state = self._load(sid)
                if state is not None:
                    self._sessions[sid] = state
            if state is None:
                state = ConversationState(
                    session_id=sid,
                    user_id=user_id,
                    autonomy_level=autonomy_level or AutonomyLevel.MANUAL,
                )
                self._sessions[sid] = state
            elif state.user_id != user_id:
                raise ValueError("session_id belongs to a different user")
            elif autonomy_level is not None:
                state.autonomy_level = autonomy_level
            return state

    def get(self, session_id: str) -> ConversationState | None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is None:
                state = self._load(session_id)
                if state is not None:
                    self._sessions[session_id] = state
            return state

    def add_turn(self, state: ConversationState, role: str, content: str) -> None:
        with self._lock:
            state.turns.append(ConversationTurn(role=role, content=content))
            state.turns = state.turns[-self.max_turns :]
            state.updated_at = datetime.now(timezone.utc)
            # handle() mutates state between the user turn and the assistant
            # turn; persisting on every turn captures the final state too.
            self.persist(state)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            removed = self._sessions.pop(session_id, None) is not None
            if self.db_path:
                with self._connect() as conn:
                    cursor = conn.execute(
                        "DELETE FROM chat_sessions WHERE session_id = ?",
                        (session_id,),
                    )
                    conn.commit()
                removed = removed or cursor.rowcount > 0
            return removed
