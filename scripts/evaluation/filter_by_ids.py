#!/usr/bin/env python3
"""Filter a JSONL file down to the rows whose "id" appears in an id list
file (one id per line). Used to build the paired before/after comparison
subset for the LLM promotion-evidence pilot (see evaluation/README.md) --
scoring only the exact rows a proposer judged, rather than diluting the
effect across the full corpus.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_ids(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def filter_jsonl(rows: list[dict], ids: set[str]) -> list[dict]:
    return [row for row in rows if row.get("id") in ids]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    ids = read_ids(arguments.ids)
    rows: list[dict] = []
    with arguments.input.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                rows.append(json.loads(line))
    filtered = filter_jsonl(rows, ids)

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8") as handle:
        for row in filtered:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"kept {len(filtered)}/{len(rows)} rows")


if __name__ == "__main__":
    main()
