#!/usr/bin/env python3
"""Run the fixed five-condition evaluation and emit reproducible reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from analyze_false_paths import analyze
from score_predictions import ABLATIONS, read_jsonl, score, validate


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_revision(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--metadata", type=Path)
    arguments = parser.parse_args()

    dataset = read_jsonl(arguments.dataset)
    if arguments.gold:
        gold = {row["id"]: row for row in read_jsonl(arguments.gold)}
        dataset = [
            {**row, **gold[row["id"]]}
            for row in dataset
        ]
    predictions = read_jsonl(arguments.predictions)
    validate(dataset, predictions)
    expected = {
        (row["id"], ablation) for row in dataset for ablation in ABLATIONS
    }
    actual = {(row["id"], row["ablation"]) for row in predictions}
    missing = sorted(expected - actual)
    if missing:
        raise SystemExit(
            f"incomplete experiment: {len(missing)} instance/ablation rows missing"
        )

    root = Path(__file__).resolve().parents[2]
    manifest = {
        "git_commit": git_revision(root),
        "dataset_sha256": sha256(arguments.dataset),
        "predictions_sha256": sha256(arguments.predictions),
        "ablations": sorted(ABLATIONS),
        "dataset_instances": len(dataset),
    }
    if arguments.metadata:
        manifest["environment"] = json.loads(
            arguments.metadata.read_text(encoding="utf-8")
        )
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    (arguments.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (arguments.output_dir / "metrics.json").write_text(
        json.dumps(score(dataset, predictions), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (arguments.output_dir / "false-paths.json").write_text(
        json.dumps(analyze(dataset, predictions), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
