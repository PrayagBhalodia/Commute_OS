"""User memory / preference store — learns from interactions and feedback.

SQLite-backed profile that Agents 1 and 2 consult for personalization.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from api.schemas import UserPreferences


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserMemoryStore:
    """Persistent user preferences and interaction history."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.environ.get(
            "COMMUTE_PROFILES_DB", "data/profiles.db"
        )
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    prefs_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS user_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_user
                    ON user_events(user_id);
                """
            )
            conn.commit()

    def get_preferences(self, user_id: str) -> UserPreferences:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT prefs_json FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return UserPreferences(user_id=user_id)
        data = json.loads(row["prefs_json"])
        data["user_id"] = user_id
        return UserPreferences.model_validate(data)

    def save_preferences(self, prefs: UserPreferences) -> UserPreferences:
        now = _utc_now_iso()
        prefs.updated_at = datetime.now(timezone.utc)
        payload = prefs.model_dump(mode="json")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, prefs_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    prefs_json = excluded.prefs_json,
                    updated_at = excluded.updated_at
                """,
                (prefs.user_id, json.dumps(payload), now),
            )
            conn.commit()
        return prefs

    def record_event(
        self,
        user_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO user_events (user_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, event_type, json.dumps(payload), _utc_now_iso()),
            )
            conn.commit()

    def get_events(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_type, payload_json, created_at
                FROM user_events
                WHERE user_id = ?
                ORDER BY event_id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "event_type": r["event_type"],
                    "payload": json.loads(r["payload_json"]),
                    "created_at": r["created_at"],
                }
            )
        return out

    def apply_feedback(
        self,
        user_id: str,
        *,
        rating: Optional[int] = None,
        liked: Optional[bool] = None,
        preferred_mode: Optional[str] = None,
        avoid_mode: Optional[str] = None,
        comment: Optional[str] = None,
        selected_itinerary_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> UserPreferences:
        """Update preferences from explicit or implicit user feedback."""
        prefs = self.get_preferences(user_id)
        prefs.interaction_count += 1

        if preferred_mode:
            mode = preferred_mode.lower()
            if mode not in prefs.preferred_modes:
                prefs.preferred_modes.insert(0, mode)
            if mode in prefs.avoid_modes:
                prefs.avoid_modes = [m for m in prefs.avoid_modes if m != mode]

        if avoid_mode:
            mode = avoid_mode.lower()
            if mode not in prefs.avoid_modes:
                prefs.avoid_modes.append(mode)
            prefs.preferred_modes = [m for m in prefs.preferred_modes if m != mode]

        if liked is True:
            prefs.prefer_fastest = prefs.prefer_fastest or True
        if liked is False:
            # Slightly shift toward comfort / alternatives
            prefs.prefer_comfort = True

        if rating is not None:
            if rating >= 4:
                prefs.notes.append(f"High rating {rating}/5")
            elif rating <= 2:
                prefs.notes.append(f"Low rating {rating}/5 — explore alternatives")
            # Keep notes bounded
            prefs.notes = prefs.notes[-20:]

        if comment:
            c = comment.lower()
            if "cheap" in c or "budget" in c:
                prefs.prefer_cheapest = True
                prefs.prefer_fastest = False
            if "fast" in c or "quick" in c or "time" in c:
                prefs.prefer_fastest = True
            if "comfort" in c or "business" in c:
                prefs.prefer_comfort = True
            if "flight" in c and ("hate" in c or "avoid" in c):
                if "flight" not in prefs.avoid_modes:
                    prefs.avoid_modes.append("flight")
            prefs.notes.append(f"feedback: {comment[:120]}")
            prefs.notes = prefs.notes[-20:]

        self.record_event(
            user_id,
            "feedback",
            {
                "rating": rating,
                "liked": liked,
                "preferred_mode": preferred_mode,
                "avoid_mode": avoid_mode,
                "comment": comment,
                "selected_itinerary_id": selected_itinerary_id,
                **(metadata or {}),
            },
        )
        return self.save_preferences(prefs)

    def learn_from_selection(
        self,
        user_id: str,
        itinerary_score_profile: dict[str, Any],
    ) -> UserPreferences:
        """Implicit learning when user picks a particular scored option."""
        prefs = self.get_preferences(user_id)
        prefs.interaction_count += 1
        if itinerary_score_profile.get("cheapest"):
            prefs.prefer_cheapest = True
        if itinerary_score_profile.get("fastest"):
            prefs.prefer_fastest = True
        if itinerary_score_profile.get("comfort"):
            prefs.prefer_comfort = True
        modes = itinerary_score_profile.get("modes") or []
        for m in modes:
            if m not in prefs.preferred_modes:
                prefs.preferred_modes.append(m)
        self.record_event(user_id, "selection", itinerary_score_profile)
        return self.save_preferences(prefs)

    def set_home(
        self,
        user_id: str,
        label: str,
        lat: float,
        lng: float,
    ) -> UserPreferences:
        prefs = self.get_preferences(user_id)
        prefs.home_label = label
        prefs.home_lat = lat
        prefs.home_lng = lng
        return self.save_preferences(prefs)
