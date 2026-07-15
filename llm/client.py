"""OpenAI-compatible chat client with validated tool-call output."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from llm.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


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
        elif provider == "local":
            # A locally served model (vLLM / llama.cpp / Ollama) exposing the
            # OpenAI API — the standard way to serve the Commute OS LoRA
            # adapter. Local servers typically need no API key.
            self.api_key = llm_key or "not-needed"
            self.base_url = (
                os.getenv("LLM_BASE_URL", "").strip() or "http://127.0.0.1:8080/v1"
            )
            self.model = configured_model or "commute-os-lora"
            self.provider = "local"
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
            logger.warning(
                "LLM provider call failed; falling back to deterministic "
                "controller.", exc_info=True,
            )
            return None

    def chat(self, *, messages: list[dict[str, str]]) -> str | None:
        """Plain chat completion (no tools). Returns the text, or None on failure.

        Used by the conversational slot-filling wrapper: the caller supplies its
        own system message, so SYSTEM_PROMPT is not injected here.
        """
        client = self._get_client()
        if client is None:
            return None
        try:
            response = client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                messages=messages,
                timeout=30.0,
            )
            return response.choices[0].message.content or ""
        except Exception:
            logger.warning("LLM chat call failed.", exc_info=True)
            return None


class LocalLoraClient:
    """In-process provider running the Commute OS LoRA adapter directly.

    Enabled with LLM_PROVIDER=local_lora plus LORA_ADAPTER_PATH (adapter
    weights from finetuning/train_lora.py). Requires requirements-ml.txt;
    when the ML stack is unavailable the client disables itself and the
    deterministic controller takes over. The adapter is trained for
    conversational text, not structured tool calls, so tool_calls is always
    empty — tool execution stays with the deterministic layer.
    """

    provider = "local_lora"

    def __init__(self) -> None:
        self.adapter_path = os.getenv("LORA_ADAPTER_PATH", "").strip()
        self.base_model = (
            os.getenv("LORA_BASE_MODEL", "").strip() or "Qwen/Qwen2.5-1.5B-Instruct"
        )
        self.max_new_tokens = int(os.getenv("LORA_MAX_NEW_TOKENS", "256"))
        self._bundle = None
        self._failed = False

    @property
    def enabled(self) -> bool:
        return bool(self.adapter_path) and not self._failed

    def _load(self):
        if self._bundle is None and not self._failed:
            try:
                from finetuning.inference import load_adapter

                self._bundle = load_adapter(self.base_model, self.adapter_path)
                logger.info(
                    "Loaded LoRA adapter %s on %s", self.adapter_path, self.base_model
                )
            except Exception:
                logger.warning(
                    "Local LoRA provider unavailable (install requirements-ml.txt "
                    "and check LORA_ADAPTER_PATH); falling back to deterministic "
                    "controller.", exc_info=True,
                )
                self._failed = True
        return self._bundle

    def respond(
        self,
        *,
        messages: list[dict[str, str]],
        tool_definitions: list[dict[str, Any]],
    ) -> ProviderResponse | None:
        del tool_definitions  # text-only provider
        bundle = self._load()
        if bundle is None:
            return None
        model, tokenizer = bundle
        try:
            import torch

            chat = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
            prompt = tokenizer.apply_chat_template(
                chat, tokenize=False, add_generation_prompt=True
            )
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            with torch.no_grad():
                output = model.generate(
                    **inputs, max_new_tokens=self.max_new_tokens, do_sample=False
                )
            text = tokenizer.decode(
                output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
            )
            return ProviderResponse(text=text.strip(), tool_calls=[])
        except Exception:
            logger.warning("Local LoRA generation failed.", exc_info=True)
            return None


def build_llm_client() -> "OpenAICompatibleClient | LocalLoraClient":
    """Select the conversational provider from LLM_PROVIDER.

    - local_lora  → in-process fine-tuned adapter (needs requirements-ml.txt)
    - local       → OpenAI-compatible local server (vLLM / llama.cpp / Ollama)
    - gemini/auto → hosted providers via API key (existing behavior)
    """
    if os.getenv("LLM_PROVIDER", "").strip().lower() == "local_lora":
        return LocalLoraClient()
    return OpenAICompatibleClient()
