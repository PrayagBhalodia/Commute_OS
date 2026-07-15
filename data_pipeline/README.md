# Commute OS Datasets

This directory contains manifests and reproducible scripts, not a vendored
copy of large external datasets. Raw, interim, and generated processed files
are ignored by Git.

Only English and Hinglish are retained. The default build downloads small,
licensed subsets and generates domain-specific examples deterministically.

```powershell
python -m data_pipeline.scripts.inspect_licenses
python -m data_pipeline.scripts.build_all --dry-run
python -m data_pipeline.scripts.build_all --max-per-source 5000
```

External records retain their source and license. Do not redistribute a built
mixture without complying with every included license, especially the
share-alike requirement inherited from Schema-Guided Dialogue.
