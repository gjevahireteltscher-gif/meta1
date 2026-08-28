#!/usr/bin/env python3
"""Select a frozen, independently annotated 300-instance ConMeC test set."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


GOLD_FIELDS = {"gold", "gold_fine", "gold_bridge"}
SEED = "metonymy-independent-300-v1"


def jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def rank(identifier: str) -> str:
    return hashlib.sha256(f"{SEED}\0{identifier}".encode()).hexdigest()


def select(rows: list[dict], per_stratum: int) -> list[dict]:
    strata: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        strata[(row["category"], row["gold"])].append(row)
    selected = []
    for key in sorted(strata):
        candidates = sorted(strata[key], key=lambda row: rank(row["id"]))
        if len(candidates) < per_stratum:
            raise ValueError(
                f"stratum {key} has {len(candidates)} rows, "
                f"needs {per_stratum}"
            )
        selected.extend(candidates[:per_stratum])
    return sorted(selected, key=lambda row: row["id"])


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--combined", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--selection-manifest", type=Path)
    parser.add_argument("--per-stratum", type=int, default=25)
    arguments = parser.parse_args()
    rows = jsonl(arguments.combined)
    by_id = {row["id"]: row for row in rows}
    if arguments.selection_manifest:
        frozen = json.loads(
            arguments.selection_manifest.read_text(encoding="utf-8")
        )
        selected = [by_id[identifier] for identifier in frozen["selected_ids"]]
    else:
        selected = select(rows, arguments.per_stratum)
    output = arguments.output_dir
    output.mkdir(parents=True, exist_ok=True)
    inputs = [
        {key: value for key, value in row.items() if key not in GOLD_FIELDS}
        for row in selected
    ]
    gold = [
        {
            "id": row["id"],
            "gold": row["gold"],
            "gold_fine": row["gold_fine"],
            "gold_bridge": row["gold_bridge"],
        }
        for row in selected
    ]
    write_jsonl(output / "inputs.jsonl", inputs)
    write_jsonl(output / "gold.jsonl", gold)
    strata = Counter((row["category"], row["gold"]) for row in selected)
    manifest = {
        "schema_version": "independent-conmec-300-v1",
        "source": "ConMeC",
        "source_sha256": selected[0]["source_sha256"],
        "license": selected[0]["license"],
        "selection_seed": SEED,
        "selection_policy": (
            "25 hash-ranked instances per category×gold stratum; "
            "labels were created by ConMeC annotators, independently of this system"
        ),
        "instances": len(selected),
        "strata": {
            f"{category}:{gold_label}": count
            for (category, gold_label), count in sorted(strata.items())
        },
        "selected_ids": [row["id"] for row in selected],
        "selected_content_sha256": {
            row["id"]: row["content_sha256"] for row in selected
        },
        "corpus_text_redistributed": False,
    }
    (output / "selection-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"instances": len(selected), "strata": len(strata)}))


if __name__ == "__main__":
    main()
