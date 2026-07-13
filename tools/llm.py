"""Gemini LLM helper for DMOS.

Optional Google Gemini integration. When GEMINI_API_KEY (or GOOGLE_API_KEY)
is configured *and* the google-generativeai SDK is installed, agents can call
Gemini for richer natural-language understanding and planning.

Every helper degrades gracefully: if the key is missing, the SDK is not
installed, or the API errors/times out, the functions return ``None`` and the
caller falls back to its deterministic offline behaviour. This keeps the
prototype fully functional with zero configuration while allowing a live LLM
to enrich results when available.

Model selection:
    The model id is read from the GEMINI_MODEL env var and defaults to
    ``gemini-3.5-flash``. Override it (e.g. ``gemini-2.5-flash``) without any
    code change if your account exposes a different Flash revision.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

try:  # pragma: no cover - import guard
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None  # type: ignore

_DEFAULT_MODEL = "gemini-3.5-flash"
_configured = False


def _api_key() -> str:
    """Gemini API key from either GEMINI_API_KEY or GOOGLE_API_KEY."""
    return (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    ).strip()


def gemini_model_name() -> str:
    """Configured model id (env override), defaulting to gemini-3.5-flash."""
    return os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL


def gemini_enabled() -> bool:
    """True when a key is present and the SDK is importable."""
    return bool(_api_key()) and genai is not None


def _ensure_configured() -> bool:
    """Configure the SDK once; return False if Gemini is unavailable."""
    global _configured
    if not gemini_enabled():
        return False
    if not _configured:
        try:
            genai.configure(api_key=_api_key())
            _configured = True
        except Exception:  # noqa: BLE001
            return False
    return True


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """Best-effort parse of a JSON object out of a model response."""
    text = (text or "").strip()
    if not text:
        return None
    # Strip ```json fences if present.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    # Fall back to the first {...} block.
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def generate_json(
    prompt: str,
    *,
    system: Optional[str] = None,
    temperature: float = 0.2,
) -> Optional[dict[str, Any]]:
    """Call Gemini and parse a JSON object from the reply.

    Returns ``None`` if Gemini is disabled or anything fails, so callers can
    treat the result as an optional enrichment.
    """
    if not _ensure_configured():
        return None
    try:
        model = genai.GenerativeModel(
            gemini_model_name(),
            system_instruction=system,
            generation_config={
                "temperature": temperature,
                "response_mime_type": "application/json",
            },
        )
        resp = model.generate_content(prompt)
        return _extract_json(getattr(resp, "text", "") or "")
    except Exception:  # noqa: BLE001
        return None


def generate_text(
    prompt: str,
    *,
    system: Optional[str] = None,
    temperature: float = 0.4,
) -> Optional[str]:
    """Call Gemini and return plain text, or ``None`` on any failure."""
    if not _ensure_configured():
        return None
    try:
        model = genai.GenerativeModel(
            gemini_model_name(),
            system_instruction=system,
            generation_config={"temperature": temperature},
        )
        resp = model.generate_content(prompt)
        text = (getattr(resp, "text", "") or "").strip()
        return text or None
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "gemini_enabled",
    "gemini_model_name",
    "generate_json",
    "generate_text",
]
