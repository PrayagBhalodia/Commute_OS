"""Render normalized messages with a selected model's chat template."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_pipeline.scripts.common import read_jsonl, write_jsonl


def prepare(input_path: Path, output_path: Path, model_name: str | None = None) -> int:
    tokenizer = None
    if model_name:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_name)
    output = []
    for record in read_jsonl(input_path):
        messages = record["messages"]
        if tokenizer:
            text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
        else:
            text = "\n".join(f"<{message['role']}> {message['content']}" for message in messages)
        output.append({"id": record["id"], "text": text, "language": record["language"], "source": record["source"]})
    write_jsonl(output_path, output)
    return len(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data_pipeline/processed/chatbot_train.jsonl")
    parser.add_argument("--output", default="data_pipeline/processed/chat_template_train.jsonl")
    parser.add_argument("--model", default=None, help="Optional; downloads tokenizer only when explicitly supplied")
    args = parser.parse_args()
    count = prepare(Path(args.input), Path(args.output), args.model)
    print(json.dumps({"prepared": count, "output": args.output}, indent=2))


if __name__ == "__main__":
    main()
