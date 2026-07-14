"""OpenAI-compatible chat client with validated tool-call output."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from llm.prompts import SYSTEM_PROMPT


@dataclass
class ProviderToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class ProviderResponse:
    text: str = ""
    tool_calls: list[ProviderToolCall] = field(default_factory=list)


class OpenAICompatibleClient:
    def __init__(self) -> None:
        provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        configured_model = os.getenv("LLM_MODEL", "").strip()
        llm_key = os.getenv("LLM_API_KEY", "").strip()
        use_gemini = provider == "gemini" or (
            provider == "auto"
            and (bool(gemini_key) or configured_model.lower().startswith("gemini"))
        )
        if use_gemini:
            self.api_key = gemini_key or llm_key
            self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
            self.model = os.getenv("GEMINI_MODEL", "").strip() or configured_model or "gemini-2.5-flash"
            self.provider = "gemini"
        else:
            self.api_key = llm_key
            self.base_url = os.getenv("LLM_BASE_URL", "").strip() or None
            self.model = os.getenv("LLM_MODEL", "").strip() or "gpt-4.1-mini"
            self.provider = "openai_compatible"
        self.temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if not self.enabled:
            return None
        if self._client is None:
            from openai import OpenAI

            kwargs: dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def respond(
        self,
        *,
        messages: list[dict[str, str]],
        tool_definitions: list[dict[str, Any]],
    ) -> ProviderResponse | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            response = client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
                tools=tool_definitions,
                tool_choice="auto",
                timeout=30.0,
            )
            message = response.choices[0].message
            calls: list[ProviderToolCall] = []
            for call in message.tool_calls or []:
                import json

                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except (TypeError, json.JSONDecodeError):
                    arguments = {}
                if isinstance(arguments, dict):
                    calls.append(
                        ProviderToolCall(
                            name=call.function.name,
                            arguments=arguments,
                        )
                    )
            return ProviderResponse(text=message.content or "", tool_calls=calls)
        except Exception:
            return None
