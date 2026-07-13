"""Tests for Agent 4 — Wallet & Payments Agent."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agents.agent4_wallet import (
    InsufficientFundsError,
    InvalidAmountError,
    WalletAgent,
    from_paise,
    to_paise,
)


def test_init_db_creates_tables(tmp_wallet_db: str) -> None:
    agent = WalletAgent(db_path=tmp_wallet_db)
    assert Path(tmp_wallet_db).exists()
    with sqlite3.connect(tmp_wallet_db) as conn:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "wallets" in tables
    assert "transactions" in tables
    # Re-init is safe
    agent.init_db()


def test_new_wallet_starts_at_zero(wallet: WalletAgent) -> None:
    state = wallet.get_balance("user-new")
    assert state.user_id == "user-new"
    assert state.balance == 0.0
    assert state.currency == "INR"


def test_topup_creates_wallet_and_updates_balance(wallet: WalletAgent) -> None:
    state = wallet.topup("user-1", 1000.0, trip_id="trip-a")
    assert state.balance == 1000.0
    assert wallet.get_balance("user-1").balance == 1000.0


def test_topup_creates_ledger_transaction(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 500.0, trip_id="trip-a", description="Initial top-up")
    ledger = wallet.get_ledger("user-1")
    assert len(ledger) == 1
    tx = ledger[0]
    assert tx.type == "topup"
    assert tx.amount == 500.0
    assert tx.balance_after == 500.0
    assert tx.trip_id == "trip-a"
    assert tx.description == "Initial top-up"


def test_topup_rejects_non_positive(wallet: WalletAgent) -> None:
    with pytest.raises(InvalidAmountError):
        wallet.topup("user-1", 0.0, trip_id="t")
    with pytest.raises(InvalidAmountError):
        wallet.topup("user-1", -10.0, trip_id="t")


def test_debit_decreases_balance_and_ledger(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 1000.0, trip_id="trip-a")
    tx = wallet.debit(
        "user-1", 250.0, trip_id="trip-a", description="Cab debit"
    )
    assert tx.type == "debit"
    assert tx.amount == 250.0
    assert tx.balance_after == 750.0
    assert wallet.get_balance("user-1").balance == 750.0
    ledger = wallet.get_ledger("user-1")
    assert len(ledger) == 2
    assert ledger[-1].type == "debit"


def test_debit_insufficient_funds_raises_and_no_mutation(
    wallet: WalletAgent,
) -> None:
    wallet.topup("user-1", 100.0, trip_id="trip-a")
    with pytest.raises(InsufficientFundsError):
        wallet.debit("user-1", 200.0, trip_id="trip-a", description="Too much")
    assert wallet.get_balance("user-1").balance == 100.0
    ledger = wallet.get_ledger("user-1")
    assert len(ledger) == 1  # only topup
    assert all(tx.type != "debit" for tx in ledger)


def test_debit_rejects_non_positive(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 100.0, trip_id="t")
    with pytest.raises(InvalidAmountError):
        wallet.debit("user-1", 0.0, trip_id="t", description="x")


def test_refund_increases_balance_and_ledger(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 500.0, trip_id="trip-a")
    wallet.debit("user-1", 200.0, trip_id="trip-a", description="Debit")
    tx = wallet.refund(
        "user-1", 200.0, trip_id="trip-a", description="Cancel refund"
    )
    assert tx.type == "refund"
    assert tx.amount == 200.0
    assert tx.balance_after == 500.0
    assert wallet.get_balance("user-1").balance == 500.0


def test_reconcile_cheaper_creates_refund(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 5000.0, trip_id="trip-r")
    wallet.debit("user-1", 3000.0, trip_id="trip-r", description="Original")
    result = wallet.reconcile(
        trip_id="trip-r",
        user_id="user-1",
        original_total=3000.0,
        revised_total=2500.0,
    )
    assert result.action == "refund"
    assert result.difference == pytest.approx(-500.0)
    assert result.transaction is not None
    assert result.transaction.type == "refund"
    assert result.transaction.amount == 500.0
    assert result.wallet_balance_after == 2500.0


def test_reconcile_more_expensive_with_funds(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 5000.0, trip_id="trip-r")
    wallet.debit("user-1", 2000.0, trip_id="trip-r", description="Original")
    result = wallet.reconcile(
        trip_id="trip-r",
        user_id="user-1",
        original_total=2000.0,
        revised_total=2800.0,
    )
    assert result.action == "charge_more"
    assert result.difference == pytest.approx(800.0)
    assert result.transaction is not None
    assert result.transaction.type == "debit"
    assert result.transaction.amount == 800.0
    assert result.wallet_balance_after == 2200.0


def test_reconcile_more_expensive_insufficient_returns_top_up_required(
    wallet: WalletAgent,
) -> None:
    wallet.topup("user-1", 1000.0, trip_id="trip-r")
    wallet.debit("user-1", 900.0, trip_id="trip-r", description="Original")
    # balance = 100; need 500 more
    result = wallet.reconcile(
        trip_id="trip-r",
        user_id="user-1",
        original_total=900.0,
        revised_total=1400.0,
    )
    assert result.action == "top_up_required"
    assert result.transaction is None
    assert result.wallet_balance_after == 100.0
    assert result.difference == pytest.approx(500.0)


def test_reconcile_equal_totals_no_action(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 1000.0, trip_id="trip-r")
    result = wallet.reconcile(
        trip_id="trip-r",
        user_id="user-1",
        original_total=500.0,
        revised_total=500.0,
    )
    assert result.action == "no_action"
    assert result.difference == 0.0
    assert result.transaction is None
    assert len(wallet.get_ledger("user-1", trip_id="trip-r")) == 1  # only topup


def test_ledger_filter_by_trip_id(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 1000.0, trip_id="trip-a")
    wallet.topup("user-1", 200.0, trip_id="trip-b")
    wallet.debit("user-1", 100.0, trip_id="trip-a", description="A debit")
    all_ledger = wallet.get_ledger("user-1")
    trip_a = wallet.get_ledger("user-1", trip_id="trip-a")
    assert len(all_ledger) == 3
    assert len(trip_a) == 2
    assert all(tx.trip_id == "trip-a" for tx in trip_a)
    # oldest to newest
    assert trip_a[0].timestamp <= trip_a[1].timestamp


def test_idempotent_topup(wallet: WalletAgent) -> None:
    s1 = wallet.topup(
        "user-1", 1000.0, trip_id="t", idempotency_key="top-1"
    )
    s2 = wallet.topup(
        "user-1", 1000.0, trip_id="t", idempotency_key="top-1"
    )
    assert s1.balance == s2.balance == 1000.0
    assert len(wallet.get_ledger("user-1")) == 1


def test_idempotent_debit(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 1000.0, trip_id="t")
    t1 = wallet.debit(
        "user-1", 300.0, trip_id="t", description="d", idempotency_key="deb-1"
    )
    t2 = wallet.debit(
        "user-1", 300.0, trip_id="t", description="d", idempotency_key="deb-1"
    )
    assert t1.transaction_id == t2.transaction_id
    assert wallet.get_balance("user-1").balance == 700.0
    debits = [tx for tx in wallet.get_ledger("user-1") if tx.type == "debit"]
    assert len(debits) == 1


def test_idempotent_refund(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 1000.0, trip_id="t")
    wallet.debit("user-1", 400.0, trip_id="t", description="d")
    r1 = wallet.refund(
        "user-1", 400.0, trip_id="t", description="r", idempotency_key="ref-1"
    )
    r2 = wallet.refund(
        "user-1", 400.0, trip_id="t", description="r", idempotency_key="ref-1"
    )
    assert r1.transaction_id == r2.transaction_id
    assert wallet.get_balance("user-1").balance == 1000.0


def test_idempotent_reconcile(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 5000.0, trip_id="trip-r")
    wallet.debit("user-1", 3000.0, trip_id="trip-r", description="orig")
    r1 = wallet.reconcile("trip-r", "user-1", 3000.0, 2500.0)
    r2 = wallet.reconcile("trip-r", "user-1", 3000.0, 2500.0)
    assert r1.action == r2.action == "refund"
    assert r1.transaction is not None and r2.transaction is not None
    assert r1.transaction.transaction_id == r2.transaction.transaction_id
    assert wallet.get_balance("user-1").balance == 2500.0


def test_has_sufficient_balance(wallet: WalletAgent) -> None:
    wallet.topup("user-1", 100.0, trip_id="t")
    assert wallet.has_sufficient_balance("user-1", 100.0) is True
    assert wallet.has_sufficient_balance("user-1", 100.01) is False
    assert wallet.has_sufficient_balance("user-1", 50.0) is True


def test_paise_arithmetic_precision() -> None:
    assert to_paise(10.55) == 1055
    assert from_paise(1055) == 10.55
    assert to_paise(0.01) == 1
