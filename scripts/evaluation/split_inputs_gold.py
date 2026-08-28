#!/usr/bin/env python3
"""Physically separate inference inputs from scoring-only gold fields."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

GOLD_KEYS = {
    "gold",
    "gold_fine",
    "gold_bridge",
    "explicit_target",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--combined", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.inputs.parent.mkdir(parents=True, exist_ok=True)
    with (
        arguments.combined.open(encoding="utf-8") as source,
        arguments.inputs.open("w", encoding="utf-8") as inputs,
        arguments.gold.open("w", encoding="utf-8") as gold,
    ):
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            identifier = row.get("id")
            if not identifier:
                raise ValueError(f"line {line_number}: missing id")
            input_row = {
                key: value for key, value in row.items() if key not in GOLD_KEYS
            }
            gold_row = {"id": identifier}
            for key in GOLD_KEYS:
                if key in row:
                    gold_row[key] = row[key]
            if "gold" not in gold_row:
                raise ValueError(f"line {line_number}: missing gold")
            inputs.write(json.dumps(input_row, ensure_ascii=False, sort_keys=True) + "\n")
            gold.write(json.dumps(gold_row, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
