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
from typing import Any, Callable, Optional

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


def extract_json(text: str) -> Optional[dict[str, Any]]:
    """Public helper: best-effort parse of a JSON object from model text."""
    return _extract_json(text)


# ---------------------------------------------------------------------------
# Function calling (manual loop)
# ---------------------------------------------------------------------------


def _proto_val(v: Any) -> Any:
    """Convert a proto arg value into a plain Python value."""
    try:
        if hasattr(v, "items"):  # MapComposite
            return {k: _proto_val(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)) or (
            hasattr(v, "__iter__") and not isinstance(v, (str, bytes))
        ):
            return [_proto_val(x) for x in v]
    except Exception:  # noqa: BLE001
        pass
    return v


def _function_calls(resp: Any) -> list[Any]:
    """Return the function_call protos present in a response, if any."""
    out: list[Any] = []
    try:
        for cand in resp.candidates:
            for part in cand.content.parts:
                fc = getattr(part, "function_call", None)
                if fc and getattr(fc, "name", ""):
                    out.append(fc)
    except Exception:  # noqa: BLE001
        pass
    return out


def _response_text(resp: Any) -> str:
    """Concatenate text parts without triggering the raising ``.text`` property."""
    chunks: list[str] = []
    try:
        for cand in resp.candidates:
            for part in cand.content.parts:
                t = getattr(part, "text", "")
                if t:
                    chunks.append(t)
    except Exception:  # noqa: BLE001
        pass
    return "".join(chunks).strip()


def generate_with_tools(
    prompt: str,
    *,
    tools: list[Callable[..., Any]],
    system: Optional[str] = None,
    temperature: float = 0.1,
    max_tool_rounds: int = 6,
) -> Optional[dict[str, Any]]:
    """Run a Gemini function-calling loop over the given Python tools.

    ``tools`` is a list of plain Python callables; the SDK derives each
    function-declaration schema from the callable's signature and docstring.
    Automatic function calling is disabled so we drive the loop manually and
    can report which tools the model invoked.

    Returns ``{"text": <final model text>, "tool_calls": [<names>]}`` or
    ``None`` if Gemini is unavailable or anything fails, so callers keep their
    deterministic fallback.
    """
    if not _ensure_configured():
        return None
    try:
        impls: dict[str, Callable[..., Any]] = {fn.__name__: fn for fn in tools}
        model = genai.GenerativeModel(
            gemini_model_name(),
            system_instruction=system,
            tools=tools,
            generation_config={"temperature": temperature},
        )
        chat = model.start_chat(enable_automatic_function_calling=False)
        resp = chat.send_message(prompt)
        tool_calls: list[str] = []

        for _ in range(max_tool_rounds):
            calls = _function_calls(resp)
            if not calls:
                break
            reply_parts = []
            for fc in calls:
                name = fc.name
                args = {k: _proto_val(v) for k, v in fc.args.items()} if getattr(fc, "args", None) else {}
                tool_calls.append(name)
                impl = impls.get(name)
                if impl is None:
                    result: Any = {"error": f"unknown tool {name}"}
                else:
                    try:
                        result = impl(**args)
                    except Exception as exc:  # noqa: BLE001
                        result = {"error": str(exc)}
                reply_parts.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=name,
                            response={"result": result},
                        )
                    )
                )
            resp = chat.send_message(genai.protos.Content(parts=reply_parts))

        text = _response_text(resp)
        if not text:
            return None
        return {"text": text, "tool_calls": tool_calls}
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "gemini_enabled",
    "gemini_model_name",
    "generate_json",
    "generate_text",
    "generate_with_tools",
    "extract_json",
]
