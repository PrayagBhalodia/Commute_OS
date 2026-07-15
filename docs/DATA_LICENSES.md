# Data Licenses

The machine-readable source of truth is
`data_pipeline/manifest/dataset_manifest.yaml`; `data/dataset_manifest.yaml` is a
compatibility pointer.

| Source | License | Decision | Use |
|---|---|---|---|
| Schema-Guided Dialogue | CC-BY-SA-4.0 | Accepted | Bounded travel dialogue subset; preserve attribution/share-alike |
| Hinglish Everyday Conversations 1M | MIT | Accepted as sampled/filtered | Hinglish tone examples requiring quality review |
| Commute OS synthetic scenarios | Project-generated | Accepted | Domain behavior and exact tool contracts |
| AirDialogue | CC-BY-NC-4.0 | Evaluation only, not downloaded by default | Excluded from training/commercial use |
| Akshar Hinglish Instruct | CC-BY-NC-SA-4.0 | Rejected for training | Noncommercial restriction |
| IRCTC cancellation guidance | Attributed official-source summary | Accepted for RAG summary only | Railway guidance |
| India Code accessibility provision | Attributed official legal summary | Accepted for RAG summary only | Accessibility guidance |

No private conversations are collected. The build redacts phone numbers,
email addresses, payment identifiers, and other configured PII patterns. Large
raw files are ignored by Git. A source with missing or unclear licensing must be
marked evaluation-only or rejected before download.
