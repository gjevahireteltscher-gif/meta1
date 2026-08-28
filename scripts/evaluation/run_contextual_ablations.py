#!/usr/bin/env python3
"""Run and score the fixed contextual semantic-source ablations."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


ABLATIONS = [
    "full",
    "no-wordnet",
    "no-framenet",
    "no-existential",
    "no-formal-filtering",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    output = arguments.output_dir
    output.mkdir(parents=True, exist_ok=True)
    reports = {}
    for ablation in ABLATIONS:
        inference = output / f"{ablation}.inference.jsonl"
        report = output / f"{ablation}.metrics.json"
        subprocess.run(
            [
                "python3",
                "scripts/evaluation/run_contextual_corpus.py",
                "--dataset",
                str(arguments.dataset),
                "--engine",
                str(arguments.engine),
                "--snapshot",
                str(arguments.snapshot),
                "--ablation",
                ablation,
                "--allow-failures",
                "--output",
                str(inference),
            ],
            check=True,
        )
        subprocess.run(
            [
                "python3",
                "scripts/evaluation/score_qid_fibers.py",
                "--inference",
                str(inference),
                "--gold",
                str(arguments.gold),
                "--output",
                str(report),
            ],
            check=True,
        )
        reports[ablation] = json.loads(report.read_text(encoding="utf-8"))
    result = {
        "schema_version": "contextual-ablations-1",
        "dataset_sha256": sha256(arguments.dataset),
        "gold_sha256": sha256(arguments.gold),
        "snapshot_manifest_sha256": sha256(
            arguments.snapshot / "manifest.json"
        ),
        "ablations": reports,
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    comparison = {
        "schema_version": result["schema_version"],
        "dataset_sha256": result["dataset_sha256"],
        "gold_sha256": result["gold_sha256"],
        "snapshot_manifest_sha256": result["snapshot_manifest_sha256"],
        "ablations": {
            name: {
                key: report[key]
                for key in (
                    "coverage",
                    "abstention_rate",
                    "empty_fiber_rate",
                    "gold_in_fiber_hit_rate",
                    "fiber_exact_match_rate",
                    "formal_stage_verification_rate",
                )
            }
            for name, report in reports.items()
        },
    }
    (output / "comparison.json").write_text(
        json.dumps(comparison, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
