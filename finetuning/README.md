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
