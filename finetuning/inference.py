"""Load a base model plus Commute OS LoRA adapter for explicit inference."""

from __future__ import annotations


def load_adapter(base_model: str, adapter_path: str):
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(adapter_path)
    model = AutoModelForCausalLM.from_pretrained(base_model, device_map="auto")
    return PeftModel.from_pretrained(model, adapter_path), tokenizer


__all__ = ["load_adapter"]
