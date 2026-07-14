"""Gemini LLM helper for DMOS.

Optional Google Gemini integration through Google's OpenAI-compatible endpoint.
When GEMINI_API_KEY (or GOOGLE_API_KEY) is configured, agents can call Gemini
for richer natural-language understanding and planning.

Every helper degrades gracefully: if the key is missing, the SDK is not
installed, or the API errors/times out, the functions return ``None`` and the
caller falls back to its deterministic offline behaviour. This keeps the
prototype fully functional with zero configuration while allowing a live LLM
to enrich results when available.

Model selection:
    The model id is read from the GEMINI_MODEL env var and defaults to
    ``gemini-2.5-flash``. Override it without any
    code change if your account exposes a different Flash revision.
"""

from __future__ import annotations

import json
import os
import inspect
import re
from typing import Any, Callable, Optional

from openai import OpenAI

_DEFAULT_MODEL = "gemini-2.5-flash"
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def _api_key() -> str:
    """Gemini API key from either GEMINI_API_KEY or GOOGLE_API_KEY."""
    return (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or (
            os.environ.get("LLM_API_KEY")
            if os.environ.get("LLM_MODEL", "").lower().startswith("gemini")
            else ""
        )
        or ""
    ).strip()


def gemini_model_name() -> str:
    """Configured Gemini model id, defaulting to a Flash model."""
    return (
        os.environ.get("GEMINI_MODEL")
        or (
            os.environ.get("LLM_MODEL")
            if os.environ.get("LLM_MODEL", "").lower().startswith("gemini")
            else ""
        )
        or _DEFAULT_MODEL
    ).strip()


def gemini_enabled() -> bool:
    """True when a Gemini API key is present."""
    return bool(_api_key())


def _client() -> OpenAI | None:
    if not gemini_enabled():
        return None
    return OpenAI(api_key=_api_key(), base_url=_BASE_URL)


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
    client = _client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=gemini_model_name(),
            messages=[
                *([{"role": "system", "content": system}] if system else []),
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
            timeout=30.0,
        )
        return _extract_json(response.choices[0].message.content or "")
    except Exception:  # noqa: BLE001
        return None


def generate_text(
    prompt: str,
    *,
    system: Optional[str] = None,
    temperature: float = 0.4,
) -> Optional[str]:
    """Call Gemini and return plain text, or ``None`` on any failure."""
    client = _client()
    if client is None:
        return None
    try:
        response = client.chat.completions.create(
            model=gemini_model_name(),
            messages=[
                *([{"role": "system", "content": system}] if system else []),
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            timeout=30.0,
        )
        text = (response.choices[0].message.content or "").strip()
        return text or None
    except Exception:  # noqa: BLE001
        return None


def extract_json(text: str) -> Optional[dict[str, Any]]:
    """Public helper: best-effort parse of a JSON object from model text."""
    return _extract_json(text)


# ---------------------------------------------------------------------------
# Function calling (manual loop)
# ---------------------------------------------------------------------------


def _tool_definition(fn: Callable[..., Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, parameter in inspect.signature(fn).parameters.items():
        annotation = parameter.annotation
        json_type = "number" if annotation in {int, float} else "boolean" if annotation is bool else "string"
        properties[name] = {"type": json_type}
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": inspect.getdoc(fn) or fn.__name__,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


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
    client = _client()
    if client is None:
        return None
    try:
        impls: dict[str, Callable[..., Any]] = {fn.__name__: fn for fn in tools}
        definitions = [_tool_definition(fn) for fn in tools]
        messages: list[dict[str, Any]] = [
            *([{"role": "system", "content": system}] if system else []),
            {"role": "user", "content": prompt},
        ]
        tool_calls: list[str] = []
        for _ in range(max_tool_rounds):
            response = client.chat.completions.create(
                model=gemini_model_name(),
                messages=messages,
                tools=definitions,
                tool_choice="auto",
                temperature=temperature,
                timeout=30.0,
            )
            message = response.choices[0].message
            calls = message.tool_calls or []
            if not calls:
                text = (message.content or "").strip()
                return {"text": text, "tool_calls": tool_calls} if text else None
            messages.append(message.model_dump(exclude_none=True))
            for call in calls:
                name = call.function.name
                args = json.loads(call.function.arguments or "{}")
                tool_calls.append(name)
                impl = impls.get(name)
                if impl is None:
                    result: Any = {"error": f"unknown tool {name}"}
                else:
                    try:
                        result = impl(**args)
                    except Exception as exc:  # noqa: BLE001
                        result = {"error": str(exc)}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps({"result": result}, default=str),
                    }
                )
        return None
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
