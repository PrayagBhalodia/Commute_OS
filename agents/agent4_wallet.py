"""Agent 4 — Wallet & Payments Agent.

Simulated financial system of record for DMOS. Uses integer paise arithmetic
and SQLite with BEGIN IMMEDIATE for balance-changing operations.
Does not integrate real payment gateways.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from api.schemas import ReconciliationResult, WalletState, WalletTransaction


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class WalletError(Exception):
    """Base error for wallet operations."""


class InsufficientFundsError(WalletError):
    """Raised when a debit would exceed the available balance."""


class InvalidAmountError(WalletError):
    """Raised when an amount is zero, negative, or otherwise invalid."""


class WalletTransactionError(WalletError):
    """Raised when a ledger transaction cannot be completed."""


# ---------------------------------------------------------------------------
# Money helpers (paise = 1/100 INR)
# ---------------------------------------------------------------------------


def to_paise(amount: float) -> int:
    """Convert INR float to integer paise with banker's-safe rounding."""
    if amount is None:
        raise InvalidAmountError("amount is required")
    return int(round(float(amount) * 100))


def from_paise(paise: int) -> float:
    """Convert integer paise to INR float for API responses."""
    return paise / 100.0


def utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return utc_now().isoformat()


def parse_iso(ts: str) -> datetime:
    """Parse an ISO timestamp, ensuring timezone awareness."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# WalletAgent
# ---------------------------------------------------------------------------


class WalletAgent:
    """Financial system of record for the DMOS prototype.

    Responsibilities:
    - Wallet account lifecycle
    - Top-up, debit, refund
    - Reroute cost reconciliation
    - Append-only transaction ledger
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """Initialize the agent.

        Args:
            db_path: Path to the SQLite wallet database. Defaults to
                COMMUTE_WALLET_DB env var or data/wallet.db.
        """
        self.db_path = db_path or os.environ.get("COMMUTE_WALLET_DB", "data/wallet.db")
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        """Open a new SQLite connection for a single operation."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        """Create the database directory and tables if they do not exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS wallets (
                    user_id TEXT PRIMARY KEY,
                    balance_paise INTEGER NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    trip_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    amount_paise INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    balance_after_paise INTEGER NOT NULL,
                    idempotency_key TEXT UNIQUE NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tx_user
                    ON transactions(user_id);
                CREATE INDEX IF NOT EXISTS idx_tx_trip
                    ON transactions(trip_id);
                """
            )
            conn.commit()

    def _row_to_wallet_state(self, row: sqlite3.Row) -> WalletState:
        return WalletState(
            user_id=row["user_id"],
            balance=from_paise(row["balance_paise"]),
            currency=row["currency"],
            updated_at=parse_iso(row["updated_at"]),
        )

    def _row_to_transaction(self, row: sqlite3.Row) -> WalletTransaction:
        return WalletTransaction(
            transaction_id=row["transaction_id"],
            trip_id=row["trip_id"],
            user_id=row["user_id"],
            type=row["type"],
            amount=from_paise(row["amount_paise"]),
            description=row["description"],
            timestamp=parse_iso(row["timestamp"]),
            balance_after=from_paise(row["balance_after_paise"]),
            idempotency_key=row["idempotency_key"],
        )

    def _get_by_idempotency(
        self, conn: sqlite3.Connection, idempotency_key: str
    ) -> Optional[sqlite3.Row]:
        return conn.execute(
            "SELECT * FROM transactions WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()

    def _ensure_wallet_row(
        self, conn: sqlite3.Connection, user_id: str, now: str
    ) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM wallets WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO wallets (user_id, balance_paise, currency, updated_at)
                VALUES (?, 0, 'INR', ?)
                """,
                (user_id, now),
            )
            row = conn.execute(
                "SELECT * FROM wallets WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row

    def topup(
        self,
        user_id: str,
        amount: float,
        trip_id: str,
        description: str = "Wallet top-up",
        idempotency_key: Optional[str] = None,
    ) -> WalletState:
        """Credit the wallet and write a topup ledger entry.

        Duplicate idempotency keys return the existing wallet state without
        double-crediting.
        """
        amount_paise = to_paise(amount)
        if amount_paise <= 0:
            raise InvalidAmountError("top-up amount must be greater than zero")

        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if idempotency_key:
                    existing = self._get_by_idempotency(conn, idempotency_key)
                    if existing is not None:
                        wallet = conn.execute(
                            "SELECT * FROM wallets WHERE user_id = ?",
                            (user_id,),
                        ).fetchone()
                        if wallet is None:
                            raise WalletTransactionError(
                                "idempotent top-up found but wallet missing"
                            )
                        conn.commit()
                        return self._row_to_wallet_state(wallet)

                wallet = self._ensure_wallet_row(conn, user_id, now)
                new_balance = wallet["balance_paise"] + amount_paise
                conn.execute(
                    """
                    UPDATE wallets
                    SET balance_paise = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (new_balance, now, user_id),
                )
                conn.execute(
                    """
                    INSERT INTO transactions (
                        transaction_id, trip_id, user_id, type, amount_paise,
                        description, timestamp, balance_after_paise, idempotency_key
                    ) VALUES (?, ?, ?, 'topup', ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        trip_id,
                        user_id,
                        amount_paise,
                        description,
                        now,
                        new_balance,
                        idempotency_key,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return self.get_balance(user_id)

    def get_balance(self, user_id: str) -> WalletState:
        """Return the current wallet state. Creates a zero-balance wallet if missing."""
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                wallet = self._ensure_wallet_row(conn, user_id, now)
                conn.commit()
                return self._row_to_wallet_state(wallet)
            except Exception:
                conn.rollback()
                raise

    def has_sufficient_balance(self, user_id: str, amount: float) -> bool:
        """Return True if the wallet can cover the given amount."""
        amount_paise = to_paise(amount)
        if amount_paise < 0:
            raise InvalidAmountError("amount must not be negative")
        state = self.get_balance(user_id)
        return to_paise(state.balance) >= amount_paise

    def debit(
        self,
        user_id: str,
        amount: float,
        trip_id: str,
        description: str,
        idempotency_key: Optional[str] = None,
    ) -> WalletTransaction:
        """Atomically debit the wallet if funds are sufficient.

        Raises InsufficientFundsError without mutating state when funds
        are insufficient. Supports idempotent retries.
        """
        amount_paise = to_paise(amount)
        if amount_paise <= 0:
            raise InvalidAmountError("debit amount must be greater than zero")

        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if idempotency_key:
                    existing = self._get_by_idempotency(conn, idempotency_key)
                    if existing is not None:
                        conn.commit()
                        return self._row_to_transaction(existing)

                wallet = self._ensure_wallet_row(conn, user_id, now)
                if wallet["balance_paise"] < amount_paise:
                    conn.rollback()
                    raise InsufficientFundsError(
                        f"Insufficient funds for user {user_id}: "
                        f"need {from_paise(amount_paise):.2f} INR, "
                        f"have {from_paise(wallet['balance_paise']):.2f} INR"
                    )

                new_balance = wallet["balance_paise"] - amount_paise
                tx_id = str(uuid.uuid4())
                conn.execute(
                    """
                    UPDATE wallets
                    SET balance_paise = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (new_balance, now, user_id),
                )
                conn.execute(
                    """
                    INSERT INTO transactions (
                        transaction_id, trip_id, user_id, type, amount_paise,
                        description, timestamp, balance_after_paise, idempotency_key
                    ) VALUES (?, ?, ?, 'debit', ?, ?, ?, ?, ?)
                    """,
                    (
                        tx_id,
                        trip_id,
                        user_id,
                        amount_paise,
                        description,
                        now,
                        new_balance,
                        idempotency_key,
                    ),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM transactions WHERE transaction_id = ?",
                    (tx_id,),
                ).fetchone()
                return self._row_to_transaction(row)
            except InsufficientFundsError:
                raise
            except Exception:
                conn.rollback()
                raise

    def refund(
        self,
        user_id: str,
        amount: float,
        trip_id: str,
        description: str,
        idempotency_key: Optional[str] = None,
    ) -> WalletTransaction:
        """Credit a refund to the wallet and write a ledger entry."""
        amount_paise = to_paise(amount)
        if amount_paise <= 0:
            raise InvalidAmountError("refund amount must be greater than zero")

        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if idempotency_key:
                    existing = self._get_by_idempotency(conn, idempotency_key)
                    if existing is not None:
                        conn.commit()
                        return self._row_to_transaction(existing)

                wallet = self._ensure_wallet_row(conn, user_id, now)
                new_balance = wallet["balance_paise"] + amount_paise
                tx_id = str(uuid.uuid4())
                conn.execute(
                    """
                    UPDATE wallets
                    SET balance_paise = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (new_balance, now, user_id),
                )
                conn.execute(
                    """
                    INSERT INTO transactions (
                        transaction_id, trip_id, user_id, type, amount_paise,
                        description, timestamp, balance_after_paise, idempotency_key
                    ) VALUES (?, ?, ?, 'refund', ?, ?, ?, ?, ?)
                    """,
                    (
                        tx_id,
                        trip_id,
                        user_id,
                        amount_paise,
                        description,
                        now,
                        new_balance,
                        idempotency_key,
                    ),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM transactions WHERE transaction_id = ?",
                    (tx_id,),
                ).fetchone()
                return self._row_to_transaction(row)
            except Exception:
                conn.rollback()
                raise

    def reconcile(
        self,
        trip_id: str,
        user_id: str,
        original_total: float,
        revised_total: float,
    ) -> ReconciliationResult:
        """Reconcile original vs revised itinerary totals after rerouting.

        difference = revised_total - original_total

        - negative → refund
        - positive → charge_more or top_up_required
        - zero → no_action

        Safe against accidental duplicate execution via deterministic
        idempotency keys scoped to the trip and totals.
        """
        if original_total < 0 or revised_total < 0:
            raise InvalidAmountError("totals must not be negative")

        original_paise = to_paise(original_total)
        revised_paise = to_paise(revised_total)
        diff_paise = revised_paise - original_paise
        difference = from_paise(diff_paise)

        # Deterministic key so re-running the same reconciliation is safe.
        idem_key = (
            f"reconcile:{trip_id}:{user_id}:{original_paise}:{revised_paise}"
        )

        if diff_paise == 0:
            balance = self.get_balance(user_id)
            return ReconciliationResult(
                trip_id=trip_id,
                user_id=user_id,
                original_total=from_paise(original_paise),
                revised_total=from_paise(revised_paise),
                difference=0.0,
                action="no_action",
                wallet_balance_after=balance.balance,
                transaction=None,
                message="No price change; no wallet action required",
            )

        if diff_paise < 0:
            refund_amount = from_paise(abs(diff_paise))
            tx = self.refund(
                user_id=user_id,
                amount=refund_amount,
                trip_id=trip_id,
                description=(
                    f"Reroute reconciliation refund: original "
                    f"{from_paise(original_paise):.2f} → revised "
                    f"{from_paise(revised_paise):.2f}"
                ),
                idempotency_key=idem_key,
            )
            return ReconciliationResult(
                trip_id=trip_id,
                user_id=user_id,
                original_total=from_paise(original_paise),
                revised_total=from_paise(revised_paise),
                difference=difference,
                action="refund",
                wallet_balance_after=tx.balance_after,
                transaction=tx,
                message=f"Refunded {refund_amount:.2f} INR due to cheaper revised journey",
            )

        # revised is more expensive
        extra = from_paise(diff_paise)
        if self.has_sufficient_balance(user_id, extra):
            tx = self.debit(
                user_id=user_id,
                amount=extra,
                trip_id=trip_id,
                description=(
                    f"Reroute reconciliation charge: original "
                    f"{from_paise(original_paise):.2f} → revised "
                    f"{from_paise(revised_paise):.2f}"
                ),
                idempotency_key=idem_key,
            )
            return ReconciliationResult(
                trip_id=trip_id,
                user_id=user_id,
                original_total=from_paise(original_paise),
                revised_total=from_paise(revised_paise),
                difference=difference,
                action="charge_more",
                wallet_balance_after=tx.balance_after,
                transaction=tx,
                message=f"Charged additional {extra:.2f} INR for revised journey",
            )

        balance = self.get_balance(user_id)
        return ReconciliationResult(
            trip_id=trip_id,
            user_id=user_id,
            original_total=from_paise(original_paise),
            revised_total=from_paise(revised_paise),
            difference=difference,
            action="top_up_required",
            wallet_balance_after=balance.balance,
            transaction=None,
            message=(
                f"Additional {extra:.2f} INR required; wallet balance "
                f"{balance.balance:.2f} INR is insufficient"
            ),
        )

    def get_ledger(
        self,
        user_id: str,
        trip_id: Optional[str] = None,
    ) -> list[WalletTransaction]:
        """Return ledger entries ordered oldest to newest."""
        with self._connect() as conn:
            if trip_id is not None:
                rows = conn.execute(
                    """
                    SELECT * FROM transactions
                    WHERE user_id = ? AND trip_id = ?
                    ORDER BY timestamp ASC, transaction_id ASC
                    """,
                    (user_id, trip_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM transactions
                    WHERE user_id = ?
                    ORDER BY timestamp ASC, transaction_id ASC
                    """,
                    (user_id,),
                ).fetchall()
        return [self._row_to_transaction(r) for r in rows]
