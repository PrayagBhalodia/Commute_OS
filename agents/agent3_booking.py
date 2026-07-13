"""Agent 3 — Booking & Operator Integration Agent.

Receives an already-resolved itinerary and executes multi-mode bookings
via mock operator adapters. Debits the wallet only after operator confirmation.
Deterministic business logic only — no LLM calls.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from agents.agent4_wallet import (
    InsufficientFundsError,
    WalletAgent,
    from_paise,
    to_paise,
)
from api.schemas import (
    BookingConfirmation,
    BookingRequest,
    CancelLegResult,
    LegBookingConfirmation,
    LegOption,
    TransportMode,
)
from tools import mock_cab_api, mock_flight_api, mock_transit_api


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BookingError(Exception):
    """Base error for booking operations."""


class UnsupportedOperatorError(BookingError):
    """Raised when mode/operator is not in the catalog."""


class BookingConsentRequiredError(BookingError):
    """Raised when user_confirmed is false (human-in-the-loop safeguard)."""


class BookingAlreadyExistsError(BookingError):
    """Raised when a successful booking already exists (optional signal)."""


class ExternalOperatorError(BookingError):
    """Raised when a mock/external operator call fails unexpectedly."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_iso(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


DEFAULT_OPERATOR_CATALOG: dict[str, list[str]] = {
    "cab": ["Ola", "Uber"],
    "auto": ["Namma Yatri", "Local Auto"],
    "flight": ["IndiGo", "Air India", "Akasa Air"],
    "train": ["IRCTC"],
    "bus": ["RedBus"],
    "metro": ["Ahmedabad Metro", "Mumbai Metro"],
}


# ---------------------------------------------------------------------------
# BookingAgent
# ---------------------------------------------------------------------------


class BookingAgent:
    """Executes multi-leg itinerary bookings across mock operators.

    Does not rank routes — it only books the itinerary it receives.
    Wallet mutations happen after successful operator confirmation.
    """

    def __init__(
        self,
        wallet_agent: Optional[WalletAgent] = None,
        db_path: Optional[str] = None,
        failure_rate: float = 0.0,
        latency_seconds: float = 0.0,
        force_failure_legs: Optional[set[str]] = None,
    ) -> None:
        """Initialize the booking agent.

        Args:
            wallet_agent: Shared WalletAgent instance. Created if omitted.
            db_path: Path to bookings SQLite DB.
            failure_rate: Default mock operator failure rate (0 for tests).
            latency_seconds: Simulated operator latency (0 for tests).
            force_failure_legs: Leg IDs that must fail when booked (tests).
        """
        self.db_path = db_path or os.environ.get(
            "COMMUTE_BOOKING_DB", "data/bookings.db"
        )
        self.wallet = wallet_agent or WalletAgent()
        self.failure_rate = failure_rate
        self.latency_seconds = latency_seconds
        self.force_failure_legs: set[str] = force_failure_legs or set()
        self.operator_catalog = dict(DEFAULT_OPERATOR_CATALOG)
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        """Create booking tables if they do not exist."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS bookings (
                    trip_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    itinerary_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_charged_paise INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    goal_context_json TEXT,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS booked_legs (
                    trip_id TEXT NOT NULL,
                    leg_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    booking_ref TEXT,
                    status TEXT NOT NULL,
                    amount_charged_paise INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    message TEXT DEFAULT '',
                    PRIMARY KEY (trip_id, leg_id)
                );

                CREATE INDEX IF NOT EXISTS idx_booked_legs_trip
                    ON booked_legs(trip_id);
                """
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def get_operator_catalog(self) -> dict[str, list[str]]:
        """Return the unified operator catalog (JSON-serializable)."""
        return {k: list(v) for k, v in self.operator_catalog.items()}

    def _validate_operator(self, mode: TransportMode | str, operator: str) -> None:
        mode_key = mode.value if isinstance(mode, TransportMode) else str(mode)
        if mode_key not in self.operator_catalog:
            raise UnsupportedOperatorError(f"Unsupported transport mode: {mode_key}")
        allowed = self.operator_catalog[mode_key]
        if operator not in allowed:
            raise UnsupportedOperatorError(
                f"Unsupported operator '{operator}' for mode '{mode_key}'. "
                f"Allowed: {allowed}"
            )

    # ------------------------------------------------------------------
    # Operator routing
    # ------------------------------------------------------------------

    def _route_book(
        self,
        trip_id: str,
        leg: LegOption,
        force_failure: bool = False,
    ) -> dict[str, Any]:
        """Dispatch a booking to the correct mock operator adapter."""
        mode = leg.mode if isinstance(leg.mode, TransportMode) else TransportMode(leg.mode)
        kwargs = {
            "origin": leg.origin,
            "destination": leg.destination,
            "operator": leg.operator,
            "amount": leg.price,
            "service_id": leg.service_id,
            "trip_id": trip_id,
            "leg_id": leg.leg_id,
            "failure_rate": self.failure_rate,
            "latency_seconds": self.latency_seconds,
            "force_failure": force_failure,
        }
        if mode == TransportMode.CAB:
            return mock_cab_api.book_cab(**kwargs)
        if mode == TransportMode.FLIGHT:
            return mock_flight_api.book_flight(**kwargs)
        if mode in (
            TransportMode.TRAIN,
            TransportMode.BUS,
            TransportMode.METRO,
            TransportMode.AUTO,
        ):
            return mock_transit_api.book_transit(mode=mode, **kwargs)
        raise UnsupportedOperatorError(f"No adapter for mode: {mode}")

    def _route_cancel(
        self,
        mode: str,
        operator: str,
        booking_ref: str,
    ) -> dict[str, Any]:
        """Dispatch a cancellation to the correct mock operator adapter."""
        if mode == TransportMode.CAB.value:
            return mock_cab_api.cancel_cab(
                booking_ref=booking_ref,
                operator=operator,
                latency_seconds=self.latency_seconds,
            )
        if mode == TransportMode.FLIGHT.value:
            return mock_flight_api.cancel_flight(
                booking_ref=booking_ref,
                operator=operator,
                latency_seconds=self.latency_seconds,
            )
        if mode in (
            TransportMode.TRAIN.value,
            TransportMode.BUS.value,
            TransportMode.METRO.value,
            TransportMode.AUTO.value,
        ):
            return mock_transit_api.cancel_transit(
                booking_ref=booking_ref,
                mode=mode,
                operator=operator,
                latency_seconds=self.latency_seconds,
            )
        raise UnsupportedOperatorError(f"No cancel adapter for mode: {mode}")

    # ------------------------------------------------------------------
    # Single-leg booking (no wallet debit)
    # ------------------------------------------------------------------

    def book_single_leg(
        self,
        trip_id: str,
        leg: LegOption,
    ) -> LegBookingConfirmation:
        """Book a single leg via the operator adapter (no wallet debit).

        Wallet mutation is owned by the multi-leg book_itinerary workflow.
        """
        self._validate_operator(leg.mode, leg.operator)
        force = leg.leg_id in self.force_failure_legs
        result = self._route_book(trip_id, leg, force_failure=force)
        now = utc_now()
        status = "confirmed" if result.get("success") else "failed"
        return LegBookingConfirmation(
            leg_id=leg.leg_id,
            mode=leg.mode,
            operator=leg.operator,
            booking_ref=result.get("booking_ref"),
            status=status,
            price_charged=float(result.get("amount") or leg.price),
            message=result.get("message") or "",
            created_at=now,
        )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_booking_confirmation(
        self, trip_id: str
    ) -> Optional[BookingConfirmation]:
        with self._connect() as conn:
            booking = conn.execute(
                "SELECT * FROM bookings WHERE trip_id = ?", (trip_id,)
            ).fetchone()
            if booking is None:
                return None
            legs = conn.execute(
                """
                SELECT * FROM booked_legs
                WHERE trip_id = ?
                ORDER BY created_at ASC
                """,
                (trip_id,),
            ).fetchall()

        leg_confirmations = [
            LegBookingConfirmation(
                leg_id=row["leg_id"],
                mode=TransportMode(row["mode"]),
                operator=row["operator"],
                booking_ref=row["booking_ref"],
                status=row["status"],
                price_charged=from_paise(row["amount_charged_paise"]),
                message=row["message"] or "",
                created_at=parse_iso(row["created_at"]),
            )
            for row in legs
        ]
        failed = [lc.leg_id for lc in leg_confirmations if lc.status == "failed"]
        all_confirmed = bool(leg_confirmations) and all(
            lc.status == "confirmed" for lc in leg_confirmations
        )
        return BookingConfirmation(
            trip_id=booking["trip_id"],
            user_id=booking["user_id"],
            itinerary_id=booking["itinerary_id"],
            status=booking["status"],
            leg_confirmations=leg_confirmations,
            all_confirmed=all_confirmed,
            total_charged=from_paise(booking["total_charged_paise"]),
            failed_legs=failed,
            error=booking["error"],
            created_at=parse_iso(booking["created_at"]),
        )

    def _persist_full_booking(
        self,
        confirmation: BookingConfirmation,
        idempotency_key: Optional[str],
        goal_context_json: Optional[str],
    ) -> None:
        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO bookings (
                        trip_id, user_id, itinerary_id, status,
                        total_charged_paise, created_at, updated_at,
                        idempotency_key, goal_context_json, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(trip_id) DO UPDATE SET
                        status = excluded.status,
                        total_charged_paise = excluded.total_charged_paise,
                        updated_at = excluded.updated_at,
                        error = excluded.error
                    """,
                    (
                        confirmation.trip_id,
                        confirmation.user_id,
                        confirmation.itinerary_id,
                        confirmation.status,
                        to_paise(confirmation.total_charged),
                        confirmation.created_at.isoformat()
                        if confirmation.created_at.tzinfo
                        else confirmation.created_at.replace(
                            tzinfo=timezone.utc
                        ).isoformat(),
                        now,
                        idempotency_key,
                        goal_context_json,
                        confirmation.error,
                    ),
                )
                for lc in confirmation.leg_confirmations:
                    conn.execute(
                        """
                        INSERT INTO booked_legs (
                            trip_id, leg_id, mode, operator, booking_ref,
                            status, amount_charged_paise, created_at, message
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(trip_id, leg_id) DO UPDATE SET
                            booking_ref = excluded.booking_ref,
                            status = excluded.status,
                            amount_charged_paise = excluded.amount_charged_paise,
                            message = excluded.message
                        """,
                        (
                            confirmation.trip_id,
                            lc.leg_id,
                            lc.mode.value if isinstance(lc.mode, TransportMode) else lc.mode,
                            lc.operator,
                            lc.booking_ref,
                            lc.status,
                            to_paise(lc.price_charged),
                            lc.created_at.isoformat(),
                            lc.message,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _find_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[BookingConfirmation]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT trip_id FROM bookings WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        return self._load_booking_confirmation(row["trip_id"])

    # ------------------------------------------------------------------
    # Compensation
    # ------------------------------------------------------------------

    def _compensate_confirmed_legs(
        self,
        trip_id: str,
        user_id: str,
        confirmed: list[LegBookingConfirmation],
    ) -> list[LegBookingConfirmation]:
        """Cancel externally booked legs and refund wallet debits."""
        compensated: list[LegBookingConfirmation] = []
        for lc in confirmed:
            if lc.status != "confirmed" or not lc.booking_ref:
                compensated.append(lc)
                continue
            mode = lc.mode.value if isinstance(lc.mode, TransportMode) else str(lc.mode)
            cancel_result = self._route_cancel(mode, lc.operator, lc.booking_ref)
            refund_amount = lc.price_charged
            if refund_amount > 0:
                self.wallet.refund(
                    user_id=user_id,
                    amount=refund_amount,
                    trip_id=trip_id,
                    description=(
                        f"Compensation refund for leg {lc.leg_id} "
                        f"({lc.booking_ref})"
                    ),
                    idempotency_key=f"comp-refund:{trip_id}:{lc.leg_id}:{lc.booking_ref}",
                )
            compensated.append(
                LegBookingConfirmation(
                    leg_id=lc.leg_id,
                    mode=lc.mode,
                    operator=lc.operator,
                    booking_ref=lc.booking_ref,
                    status="cancelled",
                    price_charged=0.0,
                    message=(
                        f"Compensated: {cancel_result.get('message', 'cancelled')}; "
                        f"refunded {refund_amount:.2f} INR"
                    ),
                    created_at=utc_now(),
                )
            )
        return compensated

    # ------------------------------------------------------------------
    # Main booking workflow
    # ------------------------------------------------------------------

    def book_itinerary(self, request: BookingRequest) -> BookingConfirmation:
        """Book all legs of a resolved itinerary with wallet integration.

        Steps:
        1. Require user_confirmed (human-in-the-loop)
        2. Validate itinerary / operators
        3. Pre-check wallet balance
        4. Book legs sequentially
        5. Debit wallet after each successful operator booking
        6. Compensate on failure
        7. Persist and return confirmation
        8. Idempotent on trip_id / idempotency_key
        """
        now = utc_now()

        # --- Step 8: idempotency / existing booking ---
        existing = self.get_booking(request.trip_id)
        if existing is not None and existing.status == "confirmed":
            return existing
        if request.idempotency_key:
            by_key = self._find_by_idempotency_key(request.idempotency_key)
            if by_key is not None and by_key.status == "confirmed":
                return by_key

        # --- Step 1: consent ---
        if not request.user_confirmed:
            raise BookingConsentRequiredError(
                "user_confirmed must be true before booking. "
                "Human-in-the-loop consent is required."
            )

        itinerary = request.itinerary
        goal_json: Optional[str] = None
        if itinerary.goal_context is not None:
            goal_json = itinerary.goal_context.model_dump_json()

        # --- Step 2: validate ---
        if not itinerary.legs:
            raise BookingError("itinerary must contain at least one leg")
        for leg in itinerary.legs:
            if leg.price < 0:
                raise BookingError(f"leg {leg.leg_id} has negative price")
            self._validate_operator(leg.mode, leg.operator)

        estimated_total = sum(leg.price for leg in itinerary.legs)

        # --- Step 3: wallet pre-check ---
        if not self.wallet.has_sufficient_balance(request.user_id, estimated_total):
            balance = self.wallet.get_balance(request.user_id)
            confirmation = BookingConfirmation(
                trip_id=request.trip_id,
                user_id=request.user_id,
                itinerary_id=itinerary.itinerary_id,
                status="failed",
                leg_confirmations=[],
                all_confirmed=False,
                total_charged=0.0,
                failed_legs=[leg.leg_id for leg in itinerary.legs],
                error=(
                    f"Insufficient funds: need {estimated_total:.2f} INR, "
                    f"have {balance.balance:.2f} INR"
                ),
                created_at=now,
            )
            self._persist_full_booking(
                confirmation, request.idempotency_key, goal_json
            )
            return confirmation

        # --- Steps 4–6: sequential book + debit + compensate ---
        confirmed_legs: list[LegBookingConfirmation] = []
        failed_leg_id: Optional[str] = None
        error_msg: Optional[str] = None

        for leg in itinerary.legs:
            force = leg.leg_id in self.force_failure_legs
            try:
                op_result = self._route_book(
                    request.trip_id, leg, force_failure=force
                )
            except Exception as exc:  # noqa: BLE001 — normalize operator errors
                op_result = {
                    "success": False,
                    "booking_ref": None,
                    "amount": leg.price,
                    "message": str(exc),
                }

            if not op_result.get("success"):
                failed_leg_id = leg.leg_id
                error_msg = op_result.get("message") or f"Operator failed for {leg.leg_id}"
                failed_conf = LegBookingConfirmation(
                    leg_id=leg.leg_id,
                    mode=leg.mode,
                    operator=leg.operator,
                    booking_ref=None,
                    status="failed",
                    price_charged=0.0,
                    message=error_msg,
                    created_at=utc_now(),
                )
                # Compensate previous successes
                compensated = self._compensate_confirmed_legs(
                    request.trip_id, request.user_id, confirmed_legs
                )
                final_legs = compensated + [failed_conf]
                confirmation = BookingConfirmation(
                    trip_id=request.trip_id,
                    user_id=request.user_id,
                    itinerary_id=itinerary.itinerary_id,
                    status="failed",
                    leg_confirmations=final_legs,
                    all_confirmed=False,
                    total_charged=0.0,
                    failed_legs=[failed_leg_id],
                    error=error_msg,
                    created_at=now,
                )
                self._persist_full_booking(
                    confirmation, request.idempotency_key, goal_json
                )
                return confirmation

            charged = float(op_result.get("amount") or leg.price)
            booking_ref = op_result.get("booking_ref")
            debit_key = f"{request.trip_id}:{leg.leg_id}:{booking_ref}"

            try:
                self.wallet.debit(
                    user_id=request.user_id,
                    amount=charged,
                    trip_id=request.trip_id,
                    description=(
                        f"Booking debit leg {leg.leg_id} "
                        f"({leg.mode.value if isinstance(leg.mode, TransportMode) else leg.mode}/"
                        f"{leg.operator}) ref={booking_ref}"
                    ),
                    idempotency_key=debit_key,
                )
            except InsufficientFundsError as exc:
                # Cancel external booking that just succeeded
                mode = (
                    leg.mode.value
                    if isinstance(leg.mode, TransportMode)
                    else str(leg.mode)
                )
                if booking_ref:
                    self._route_cancel(mode, leg.operator, booking_ref)
                compensated = self._compensate_confirmed_legs(
                    request.trip_id, request.user_id, confirmed_legs
                )
                failed_conf = LegBookingConfirmation(
                    leg_id=leg.leg_id,
                    mode=leg.mode,
                    operator=leg.operator,
                    booking_ref=booking_ref,
                    status="failed",
                    price_charged=0.0,
                    message=f"Wallet debit failed after operator booking: {exc}",
                    created_at=utc_now(),
                )
                confirmation = BookingConfirmation(
                    trip_id=request.trip_id,
                    user_id=request.user_id,
                    itinerary_id=itinerary.itinerary_id,
                    status="failed",
                    leg_confirmations=compensated + [failed_conf],
                    all_confirmed=False,
                    total_charged=0.0,
                    failed_legs=[leg.leg_id],
                    error=str(exc),
                    created_at=now,
                )
                self._persist_full_booking(
                    confirmation, request.idempotency_key, goal_json
                )
                return confirmation

            confirmed_legs.append(
                LegBookingConfirmation(
                    leg_id=leg.leg_id,
                    mode=leg.mode,
                    operator=leg.operator,
                    booking_ref=booking_ref,
                    status="confirmed",
                    price_charged=charged,
                    message=op_result.get("message") or "Booked",
                    created_at=utc_now(),
                )
            )

        # --- Step 7: all succeeded ---
        total_charged = sum(lc.price_charged for lc in confirmed_legs)
        confirmation = BookingConfirmation(
            trip_id=request.trip_id,
            user_id=request.user_id,
            itinerary_id=itinerary.itinerary_id,
            status="confirmed",
            leg_confirmations=confirmed_legs,
            all_confirmed=True,
            total_charged=total_charged,
            failed_legs=[],
            error=None,
            created_at=now,
        )
        self._persist_full_booking(
            confirmation, request.idempotency_key, goal_json
        )
        return confirmation

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def cancel_leg(self, trip_id: str, leg_id: str) -> CancelLegResult:
        """Cancel a booked leg, call operator cancel, and refund the wallet.

        Idempotent if the leg is already cancelled.
        """
        with self._connect() as conn:
            booking = conn.execute(
                "SELECT * FROM bookings WHERE trip_id = ?", (trip_id,)
            ).fetchone()
            if booking is None:
                raise BookingError(f"No booking found for trip_id={trip_id}")
            leg_row = conn.execute(
                """
                SELECT * FROM booked_legs
                WHERE trip_id = ? AND leg_id = ?
                """,
                (trip_id, leg_id),
            ).fetchone()
            if leg_row is None:
                raise BookingError(
                    f"No leg {leg_id} found for trip_id={trip_id}"
                )

            user_id = booking["user_id"]
            status = leg_row["status"]
            amount_paise = leg_row["amount_charged_paise"]
            booking_ref = leg_row["booking_ref"]
            mode = leg_row["mode"]
            operator = leg_row["operator"]

        if status == "cancelled":
            balance = self.wallet.get_balance(user_id)
            return CancelLegResult(
                trip_id=trip_id,
                leg_id=leg_id,
                status="cancelled",
                refund_amount=0.0,
                wallet_balance_after=balance.balance,
                message="Leg already cancelled (idempotent)",
            )

        if status != "confirmed":
            raise BookingError(
                f"Cannot cancel leg {leg_id} with status '{status}'"
            )

        if booking_ref:
            self._route_cancel(mode, operator, booking_ref)

        refund_amount = from_paise(amount_paise)
        if refund_amount > 0:
            tx = self.wallet.refund(
                user_id=user_id,
                amount=refund_amount,
                trip_id=trip_id,
                description=f"Cancellation refund for leg {leg_id} ({booking_ref})",
                idempotency_key=f"cancel-refund:{trip_id}:{leg_id}:{booking_ref}",
            )
            balance_after = tx.balance_after
        else:
            balance_after = self.wallet.get_balance(user_id).balance

        now = utc_now_iso()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    UPDATE booked_legs
                    SET status = 'cancelled', amount_charged_paise = 0,
                        message = ?
                    WHERE trip_id = ? AND leg_id = ?
                    """,
                    (
                        f"Cancelled; refunded {refund_amount:.2f} INR",
                        trip_id,
                        leg_id,
                    ),
                )
                # Recompute trip status
                rows = conn.execute(
                    "SELECT status FROM booked_legs WHERE trip_id = ?",
                    (trip_id,),
                ).fetchall()
                statuses = [r["status"] for r in rows]
                if all(s == "cancelled" for s in statuses):
                    trip_status = "cancelled"
                elif any(s == "cancelled" for s in statuses) and any(
                    s == "confirmed" for s in statuses
                ):
                    trip_status = "partially_cancelled"
                else:
                    trip_status = booking["status"]

                remaining = conn.execute(
                    """
                    SELECT COALESCE(SUM(amount_charged_paise), 0) AS total
                    FROM booked_legs
                    WHERE trip_id = ? AND status = 'confirmed'
                    """,
                    (trip_id,),
                ).fetchone()["total"]

                conn.execute(
                    """
                    UPDATE bookings
                    SET status = ?, total_charged_paise = ?, updated_at = ?
                    WHERE trip_id = ?
                    """,
                    (trip_status, remaining, now, trip_id),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return CancelLegResult(
            trip_id=trip_id,
            leg_id=leg_id,
            status="cancelled",
            refund_amount=refund_amount,
            wallet_balance_after=balance_after,
            message=f"Leg {leg_id} cancelled; refunded {refund_amount:.2f} INR",
        )

    def get_booking(self, trip_id: str) -> Optional[BookingConfirmation]:
        """Load a persisted booking confirmation by trip_id."""
        return self._load_booking_confirmation(trip_id)

    def list_booked_legs(self, trip_id: str) -> list[LegBookingConfirmation]:
        """List all booked legs for a trip."""
        booking = self.get_booking(trip_id)
        if booking is None:
            return []
        return list(booking.leg_confirmations)
