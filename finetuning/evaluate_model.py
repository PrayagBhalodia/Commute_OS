"""Basic adapter smoke evaluation over held-out normalized prompts."""

from __future__ import annotations

import argparse
import json

from data_pipeline.scripts.common import PROCESSED_DIR, read_jsonl
from finetuning.inference import load_adapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    model, tokenizer = load_adapter(args.base_model, args.adapter)
    cases = read_jsonl(PROCESSED_DIR / "chatbot_test.jsonl")[: args.limit]
    generated = 0
    for case in cases:
        prompt = tokenizer.apply_chat_template(case["messages"][:-1], tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        output = model.generate(**inputs, max_new_tokens=128)
        generated += bool(tokenizer.decode(output[0], skip_special_tokens=True).strip())
    print(json.dumps({"cases": len(cases), "non_empty_generations": generated}, indent=2))


if __name__ == "__main__":
    main()
