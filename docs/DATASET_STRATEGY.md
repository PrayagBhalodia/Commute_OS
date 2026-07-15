# Dataset Strategy

Commute OS maintains two independent data tracks.

## Runtime RAG data

RAG contains stable journey guidance and attributed policy summaries. It is
retrieved at runtime and does not change model weights. Live fares, schedules,
availability, traffic, and vehicle positions must come from tools or APIs.

## Instruction data

Instruction data teaches conversation flow, slot extraction, tool selection,
consent, wallet explanations, and disruption handling. The supported language
scope is English and Romanized Hinglish. Devanagari and other languages are
intentionally rejected from this build at the user's request.

The build combines a bounded travel subset of Schema-Guided Dialogue, a
travel-filtered sample of Hinglish Everyday Conversations, and deterministic
Commute OS scenarios. Records are normalized, PII-redacted, validated,
deduplicated, grouped by scenario, and then split without group leakage.

```powershell
python -m data_pipeline.scripts.inspect_licenses
python -m data_pipeline.scripts.build_all --dry-run
python -m data_pipeline.scripts.build_all --max-per-source 5000
```

Raw, interim, and processed records are generated artifacts and are ignored by
Git. Scripts, configuration, manifests, and empty directory markers remain
versioned.
