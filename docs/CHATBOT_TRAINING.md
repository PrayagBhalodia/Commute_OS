# Chatbot Training

Fine-tuning is optional. The working chatbot uses the configured base LLM,
production system prompt, local RAG, allowlisted tools, and deterministic
fallback. Booking, wallet, refund, and reconciliation remain deterministic.

The normalized JSONL schema stores messages plus intent, slots, missing fields,
expected action, optional expected tool, consent requirements, safe execution
state, source, license, and quality metadata. Prepare model text on CPU:

```powershell
python -m finetuning.prepare_chat_template
```

For LoRA, use a CUDA Colab or workstation. The default config uses
`Qwen/Qwen2.5-1.5B-Instruct`, evaluates on the validation split, and writes only
adapter weights.

```powershell
pip install -r requirements-ml.txt
python -m finetuning.train_lora --config finetuning/configs/lora_config.yaml
python -m finetuning.evaluate_model --adapter finetuning/output/commute-os-lora
```

Normal application startup never imports training packages or downloads a
model. The trainer exits with a clear error when CUDA is unavailable.
