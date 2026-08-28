#!/usr/bin/env python3
"""Run and score the independently authored SafeCon-Mini benchmark."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

BRIDGE = re.compile(r"^\s*bridge:\s+(\S+)\s+--(\w+)-->", re.MULTILINE)
CANDIDATE = re.compile(r"^candidate:\s+(.+?)(?:\s{2}|$)", re.MULTILINE)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def run(engine: Path, dataset: list[dict]) -> list[dict]:
    predictions: list[dict] = []
    for row in dataset:
        process = subprocess.run(
            [str(engine), "contract", row["text"]],
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode == 0:
            bridge = BRIDGE.search(process.stdout)
            candidate = CANDIDATE.search(process.stdout)
            predictions.append(
                {
                    "id": row["id"],
                    "status": "contracted",
                    "output_text": candidate.group(1) if candidate else None,
                    "coarse_entity_id": bridge.group(1) if bridge else None,
                    "bridge": bridge.group(2) if bridge else None,
                }
            )
        else:
            message = process.stderr.strip() or process.stdout.strip()
            predictions.append(
                {
                    "id": row["id"],
                    "status": (
                        "abstain"
                        if "GF parse failed" in message
                        else "no_contraction"
                    ),
                }
            )
    return predictions


def safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score_rows(dataset: list[dict], predictions: list[dict]) -> dict:
    by_id = {row["id"]: row for row in dataset}
    prediction_by_id = {row["id"]: row for row in predictions}
    if len(prediction_by_id) != len(predictions):
        raise ValueError("duplicate prediction ids")
    if set(prediction_by_id) != set(by_id):
        raise ValueError("predictions must contain every dataset id exactly once")
    tp = fp = fn = tn = 0
    covered = unsafe_contractions = unsafe_total = 0
    errors: list[dict] = []
    for identifier, gold_row in by_id.items():
        prediction = prediction_by_id[identifier]
        safe = gold_row["gold"]["action"] == "contract"
        contracted = prediction["status"] == "contracted"
        correct_target = (
            contracted
            and prediction.get("coarse_entity_id")
            == gold_row["gold"].get("coarse_entity_id")
        )
        if prediction["status"] not in {"abstain", "error"}:
            covered += 1
        if safe and correct_target:
            tp += 1
        elif safe:
            fn += 1
            if contracted:
                fp += 1
        elif contracted:
            fp += 1
            unsafe_contractions += 1
        else:
            tn += 1
        if not safe:
            unsafe_total += 1
        if (safe and not correct_target) or (not safe and contracted):
            errors.append(
                {
                    "id": identifier,
                    "stratum": gold_row["stratum"],
                    "status": prediction["status"],
                    "error": (
                        "unsafe-contraction"
                        if not safe and contracted
                        else "missed-safe-contraction"
                    ),
                }
            )
    precision = safe_ratio(tp, tp + fp)
    recall = safe_ratio(tp, tp + fn)
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None
        and recall is not None
        and precision + recall > 0
        else None
    )
    return {
        "instances": len(dataset),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "coverage": safe_ratio(covered, len(dataset)),
        "unsafe_contraction_rate": safe_ratio(
            unsafe_contractions, unsafe_total
        ),
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--engine", type=Path)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    dataset = read_jsonl(arguments.dataset)
    if arguments.engine:
        predictions = run(arguments.engine, dataset)
        arguments.predictions.parent.mkdir(parents=True, exist_ok=True)
        with arguments.predictions.open("w", encoding="utf-8") as output:
            for prediction in predictions:
                output.write(json.dumps(prediction, sort_keys=True) + "\n")
    else:
        predictions = read_jsonl(arguments.predictions)
    report = score_rows(dataset, predictions)
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
