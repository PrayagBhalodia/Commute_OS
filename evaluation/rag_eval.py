"""Compatibility wrapper around the RAG evaluation command."""

from __future__ import annotations

import json

from rag.evaluation import evaluate


def main() -> None:
    print(json.dumps(evaluate(), indent=2))


if __name__ == "__main__":
    main()
