#!/usr/bin/env python3
"""List every QID in a build_wikidata_api_index.py/build_wikidata_runtime_index.py
SQLite index's entities table, one per line.

Exists so CI workflows can feed the resulting index straight into
build_wikidata_runtime_index.py materialize's --source-qid (repeatable,
one flag per seed) without embedding fragile inline Python in YAML.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def list_qids(database: Path) -> list[str]:
    connection = sqlite3.connect(database)
    try:
        return sorted(row[0] for row in connection.execute("SELECT qid FROM entities"))
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    qids = list_qids(args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(qid + "\n" for qid in qids), encoding="utf-8"
    )
    print(f"seed_qids={len(qids)}")


if __name__ == "__main__":
    main()
