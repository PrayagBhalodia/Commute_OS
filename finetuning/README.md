# Optional LoRA Fine-Tuning

The application does not require a fine-tuned model. This directory trains an
adapter from the normalized English/Hinglish messages when a CUDA GPU is
available. It never downloads a model during normal Commute OS startup.

```bash
pip install -r requirements-ml.txt
python -m finetuning.prepare_chat_template
python -m finetuning.train_lora --config finetuning/configs/lora_config.yaml
python -m finetuning.evaluate_model --adapter finetuning/output/commute-os-lora
```

For Colab, select a GPU runtime first. Adapter weights, not a merged base model,
are written to `finetuning/output/`.

## Serving the adapter

Once trained, the app can use the adapter in two ways:

```bash
# 1. In-process (needs requirements-ml.txt in the API environment)
LLM_PROVIDER=local_lora LORA_ADAPTER_PATH=finetuning/output/commute-os-lora \
  uvicorn api.main:app

# 2. Via any OpenAI-compatible local server (vLLM, llama.cpp, Ollama)
LLM_PROVIDER=local LLM_BASE_URL=http://127.0.0.1:8080/v1 uvicorn api.main:app
```

If the ML stack or adapter is missing, the client disables itself and the
deterministic controller keeps working — startup never breaks.
