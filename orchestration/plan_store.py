"""SQLite-backed store for journey plans.

Replaces the previous in-memory dict so in-flight plans survive server
restarts. Rows are keyed by trip_id and hold the full PlanResponse as
JSON; a small in-process cache keeps hot reads cheap.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from api.schemas import PlanResponse

logger = logging.getLogger(__name__)


class PlanStore:
    """Persistent trip_id → PlanResponse mapping with a read-through cache."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.environ.get(
            "COMMUTE_PLANS_DB", "data/plans.db"
        )
        self._cache: dict[str, PlanResponse] = {}
        self._lock = threading.Lock()
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    trip_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def put(self, plan: PlanResponse) -> None:
        payload = plan.model_dump_json()
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO plans (trip_id, user_id, plan_json, updated_at)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(trip_id) DO UPDATE SET"
                "   user_id = excluded.user_id,"
                "   plan_json = excluded.plan_json,"
                "   updated_at = excluded.updated_at",
                (plan.trip_id, plan.user_id, payload, now),
            )
            conn.commit()
        self._cache[plan.trip_id] = plan

    def get(self, trip_id: str) -> Optional[PlanResponse]:
        cached = self._cache.get(trip_id)
        if cached is not None:
            return cached
        with self._connect() as conn:
            row = conn.execute(
                "SELECT plan_json FROM plans WHERE trip_id = ?", (trip_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            plan = PlanResponse.model_validate_json(row["plan_json"])
        except ValueError:
            # A schema change between releases can invalidate stored rows;
            # treat them as absent rather than failing the request.
            logger.warning("Discarding unreadable stored plan %s", trip_id)
            return None
        self._cache[trip_id] = plan
        return plan
