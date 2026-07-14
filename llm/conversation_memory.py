"""Thread-safe compact in-process conversation memory."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from llm.schemas import AutonomyLevel, ConversationState, ConversationTurn


class ConversationMemory:
    def __init__(self, max_turns: int = 16) -> None:
        self.max_turns = max_turns
        self._sessions: dict[str, ConversationState] = {}
        self._lock = threading.RLock()

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
            return self._sessions.get(session_id)

    def add_turn(self, state: ConversationState, role: str, content: str) -> None:
        with self._lock:
            state.turns.append(ConversationTurn(role=role, content=content))
            state.turns = state.turns[-self.max_turns :]
            state.updated_at = datetime.now(timezone.utc)

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None
