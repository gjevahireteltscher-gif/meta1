#!/usr/bin/env python3
"""Merge canonical external relation evidence and re-hash a finite snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        shutil.rmtree(args.output)
    shutil.copytree(args.snapshot, args.output)
    rows = []
    with args.evidence.open(encoding="utf-8") as source:
        rows.extend(json.loads(line) for line in source if line.strip())
    unique = {
        (row["relation"], row["source"], row["target"], row["provenance"]): row
        for row in rows
    }
    rendered = "".join(canonical(unique[key]) for key in sorted(unique))
    (args.output / "evidence.jsonl").write_text(rendered, encoding="utf-8")
    graph = hashlib.sha256()
    for name in (
        "entities.jsonl",
        "aliases.jsonl",
        "claims.jsonl",
        "rules.json",
        "evidence.jsonl",
    ):
        contents = (args.output / name).read_bytes()
        graph.update(name.encode() + b"\0" + contents)
    manifest_path = args.output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["graph_sha256"] = graph.hexdigest()
    manifest["external_evidence"] = {
        "records": len(unique),
        "schema_version": "canonical-context-evidence-1",
    }
    manifest_path.write_text(canonical(manifest), encoding="utf-8")
    print(manifest["graph_sha256"])


if __name__ == "__main__":
    main()
