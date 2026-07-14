"""Smoke tests for the Gemini + Nominatim integrations.

These never hit the network: they exercise the offline fallbacks and, for the
LLM path, monkeypatch the Gemini helpers so the wiring is verified deterministically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import agents.agent1_intent as intent_mod
import tools.llm as llm
import tools.maps_api as maps
from agents.agent1_intent import IntentAgent
from agents.user_memory import UserMemoryStore
from tools import mock_cab_api, mock_flight_api, mock_transit_api


# ---------------------------------------------------------------------------
# tools.llm — disabled-by-default behaviour
# ---------------------------------------------------------------------------


def test_gemini_disabled_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert llm.gemini_enabled() is False
    # Helpers return None (never raise) when Gemini is unavailable.
    assert llm.generate_json("hello") is None
    assert llm.generate_text("hello") is None


def test_gemini_model_name_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert llm.gemini_model_name() == "gemini-3.5-flash"
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    assert llm.gemini_model_name() == "gemini-2.5-flash"


def test_extract_json_handles_fenced_and_noise() -> None:
    assert llm._extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm._extract_json('noise {"b": 2} trailing') == {"b": 2}
    assert llm._extract_json("not json at all") is None


# ---------------------------------------------------------------------------
# tools.maps_api — Nominatim toggle + offline fallbacks
# ---------------------------------------------------------------------------


def test_nominatim_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DMOS_USE_NOMINATIM", "0")
    assert maps.nominatim_enabled() is False
    monkeypatch.setenv("DMOS_USE_NOMINATIM", "1")
    assert maps.nominatim_enabled() is True


def test_geocode_catalog_hit_is_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    # Even with Nominatim off, a curated India place resolves offline.
    monkeypatch.setenv("DMOS_USE_NOMINATIM", "0")
    place = maps.geocode("Ahmedabad")
    assert place is not None
    assert place["source"] == "catalog"
    assert "lat" in place and "lng" in place


def test_geocode_unknown_returns_none_when_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DMOS_USE_NOMINATIM", "0")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    assert maps.geocode("zzzz nonexistent place 90909") is None


def test_reverse_geocode_nearest_catalog_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DMOS_USE_NOMINATIM", "0")
    # Coordinates near Ahmedabad resolve to the nearest catalog place offline.
    res = maps.reverse_geocode(23.0225, 72.5714)
    assert res["source"] in ("nearest_catalog", "coordinates")
    assert res["lat"] == 23.0225


def test_nominatim_search_swallows_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    # A raising HTTP client must not propagate; helper returns None.
    class _Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr(maps.httpx, "Client", _Boom)
    maps._geo_cache.clear()
    assert maps._nominatim_search("somewhere unique 12345") is None


# ---------------------------------------------------------------------------
# Agent 1 — LLM enrichment wiring (mocked Gemini)
# ---------------------------------------------------------------------------


def test_intent_works_with_llm_disabled(tmp_path: Path) -> None:
    agent = IntentAgent(memory=UserMemoryStore(db_path=str(tmp_path / "p.db")))
    result = agent.parse_intent("u1", "Interview tomorrow at Jio Institute with one suitcase")
    assert result.goal_context.metadata["llm_used"] is False
    assert "jio" in (result.goal_context.destination_name or "").lower()


def test_intent_llm_fills_missing_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force the enrichment path and stub Gemini's tool-calling extraction.
    # The destination must be grounded in the user's own wording or the
    # hallucination guard discards it.
    monkeypatch.setattr(intent_mod, "gemini_enabled", lambda: True)
    monkeypatch.setattr(
        intent_mod,
        "generate_with_tools",
        lambda *a, **k: {
            "text": '{"destination": "cousins house", "purpose": "meeting"}',
            "tool_calls": [],
        },
    )
    agent = IntentAgent(memory=UserMemoryStore(db_path=str(tmp_path / "p.db")))
    result = agent.parse_intent(
        "u2", "please help me get to my cousins house across town early"
    )
    assert (result.goal_context.destination_name or "").lower() == "cousins house"
    assert result.goal_context.metadata["llm_used"] is True
    assert "gemini" in result.goal_context.metadata["parsed_by"]


def test_intent_llm_does_not_override_rule_hits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # When rules already found a destination, the LLM must not clobber it.
    monkeypatch.setattr(intent_mod, "gemini_enabled", lambda: True)
    monkeypatch.setattr(
        intent_mod,
        "generate_with_tools",
        lambda *a, **k: {
            "text": '{"destination": "Somewhere Else"}',
            "tool_calls": [],
        },
    )
    agent = IntentAgent(memory=UserMemoryStore(db_path=str(tmp_path / "p.db")))
    result = agent.parse_intent("u3", "Interview at Jio Institute tomorrow")
    assert "jio" in (result.goal_context.destination_name or "").lower()


# ---------------------------------------------------------------------------
# Distance-aware fare models (the "Rajkot ₹350" bug)
# ---------------------------------------------------------------------------

_KW = dict(failure_rate=0.0, latency_seconds=0.0)


def test_cab_fare_scales_with_distance() -> None:
    short = mock_cab_api.get_cab_quotes("A", "B", distance_km=5, **_KW)[0]["amount"]
    long = mock_cab_api.get_cab_quotes("A", "B", distance_km=280, **_KW)[0]["amount"]
    # A ~280 km trip must cost far more than a 5 km hop (and than the old flat 350).
    assert long > short
    assert long > 3000
    assert short < long


def test_cab_known_corridor_overrides_distance() -> None:
    # Curated corridors keep their fixed fare regardless of distance hint.
    q = mock_cab_api.get_cab_quotes(
        "Ahmedabad", "Ahmedabad Airport", distance_km=999, **_KW
    )
    assert q[0]["amount"] == 450.0


def test_cab_without_distance_uses_flat_fallback() -> None:
    q = mock_cab_api.get_cab_quotes("Nowhere", "Elsewhere", **_KW)
    assert q[0]["amount"] == 350.0  # legacy behaviour preserved


def test_flight_fare_scales_with_distance() -> None:
    near = mock_flight_api.get_flight_quotes("X", "Y", distance_km=300, **_KW)[0]["amount"]
    far = mock_flight_api.get_flight_quotes("X", "Y", distance_km=1500, **_KW)[0]["amount"]
    assert far > near
    assert near >= 2500  # minimum sector fare


def test_transit_fare_scales_and_varies_by_mode() -> None:
    train = mock_transit_api.get_transit_quotes("X", "Y", mode="train", distance_km=500, **_KW)
    bus = mock_transit_api.get_transit_quotes("X", "Y", mode="bus", distance_km=500, **_KW)
    assert train[0]["amount"] > 150
    assert bus[0]["amount"] > 100
    # Same distance, different per-km model → different fares.
    assert train[0]["amount"] != bus[0]["amount"]
