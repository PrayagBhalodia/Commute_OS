"""Explicit GPU-only LoRA trainer; never imported by application startup."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

import yaml


def _load_huggingface_dataset_api():
    """Import Hugging Face Datasets without resolving the local datasets package."""
    repository_root = Path(__file__).resolve().parents[1]
    original_path = sys.path[:]
    try:
        sys.path = [
            entry for entry in sys.path
            if Path(entry or ".").resolve() != repository_root
        ]
        module = importlib.import_module("datasets")
    finally:
        sys.path = original_path
    if not hasattr(module, "load_dataset"):
        raise RuntimeError("Install requirements-ml.txt to provide Hugging Face Datasets.")
    return module.load_dataset


def train(config_path: Path) -> None:
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("LoRA training requires a CUDA GPU. Use a Colab GPU runtime or a CUDA workstation.")

    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
    from trl import SFTTrainer

    load_dataset = _load_huggingface_dataset_api()

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    tokenizer = AutoTokenizer.from_pretrained(config["model_name"])
    model = AutoModelForCausalLM.from_pretrained(
        config["model_name"], torch_dtype=torch.bfloat16, device_map="auto"
    )
    data = load_dataset(
        "json",
        data_files={"train": config["train_file"], "validation": config["validation_file"]},
    )

    def render(example):
        return {"text": tokenizer.apply_chat_template(example["messages"], tokenize=False, add_generation_prompt=False)}

    data = data.map(render)
    peft_config = LoraConfig(
        r=config["lora_r"],
        lora_alpha=config["lora_alpha"],
        lora_dropout=config["lora_dropout"],
        target_modules=config["target_modules"],
        task_type="CAUSAL_LM",
    )
    arguments = TrainingArguments(
        output_dir=config["output_dir"],
        num_train_epochs=config["epochs"],
        learning_rate=config["learning_rate"],
        per_device_train_batch_size=config["batch_size"],
        per_device_eval_batch_size=config["batch_size"],
        gradient_accumulation_steps=config["gradient_accumulation_steps"],
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_steps=10,
        bf16=True,
        report_to="none",
        seed=config["seed"],
    )
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=data["train"],
        eval_dataset=data["validation"],
        dataset_text_field="text",
        max_seq_length=config["max_sequence_length"],
        peft_config=peft_config,
        args=arguments,
    )
    trainer.train()
    trainer.model.save_pretrained(config["output_dir"])
    tokenizer.save_pretrained(config["output_dir"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="finetuning/configs/lora_config.yaml")
    args = parser.parse_args()
    train(Path(args.config))


if __name__ == "__main__":
    main()
