"""Chat sessions must survive a server restart (SQLite-backed memory)."""

from __future__ import annotations

from pathlib import Path

import pytest

from llm.conversation_memory import ConversationMemory


def test_session_survives_restart(tmp_path: Path) -> None:
    db = str(tmp_path / "chat.db")

    first = ConversationMemory(db_path=db)
    state = first.get_or_create(session_id=None, user_id="u1")
    state.constraints.origin = "Ahmedabad"
    state.constraints.destination = "Jio Institute"
    state.status = "waiting_for_start_date"
    first.add_turn(state, "user", "I need to reach Jio Institute from Ahmedabad")
    first.add_turn(state, "assistant", "What date would you like to start?")

    # Simulate a restart: a fresh memory over the same DB file.
    second = ConversationMemory(db_path=db)
    restored = second.get(state.session_id)
    assert restored is not None
    assert restored.status == "waiting_for_start_date"
    assert restored.constraints.origin == "Ahmedabad"
    assert restored.constraints.destination == "Jio Institute"
    assert [turn.role for turn in restored.turns] == ["user", "assistant"]


def test_restored_session_still_enforces_user_binding(tmp_path: Path) -> None:
    db = str(tmp_path / "chat.db")
    first = ConversationMemory(db_path=db)
    state = first.get_or_create(session_id=None, user_id="u1")
    first.add_turn(state, "user", "hello")

    second = ConversationMemory(db_path=db)
    with pytest.raises(ValueError):
        second.get_or_create(session_id=state.session_id, user_id="someone-else")


def test_delete_removes_persisted_session(tmp_path: Path) -> None:
    db = str(tmp_path / "chat.db")
    first = ConversationMemory(db_path=db)
    state = first.get_or_create(session_id=None, user_id="u1")
    first.add_turn(state, "user", "hello")

    second = ConversationMemory(db_path=db)
    assert second.delete(state.session_id) is True
    assert second.get(state.session_id) is None


def test_memory_without_db_path_stays_in_process(tmp_path: Path) -> None:
    memory = ConversationMemory()
    state = memory.get_or_create(session_id=None, user_id="u1")
    memory.add_turn(state, "user", "hello")
    assert memory.db_path is None
    assert memory.get(state.session_id) is state
