#!/usr/bin/env python3
"""Categorize emitted paths that disagree with independent gold labels."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from score_predictions import read_jsonl


def category(gold: dict, prediction: dict) -> str | None:
    status = prediction["status"]
    if status == "error":
        return "runtime-error"
    if status == "abstain":
        return prediction.get("abstention_reason", "unsupported")
    predicted = prediction.get("prediction")
    if gold["gold"] == "literal" and predicted != "literal":
        return "literal-trigger"
    if gold["gold"] == "mixed" and predicted != "mixed":
        return "mixed-treated-as-single"
    if predicted != gold["gold"]:
        return "wrong-coarse-label"
    if (
        gold.get("gold_fine")
        and prediction.get("predicted_fine")
        and gold["gold_fine"] != prediction["predicted_fine"]
    ):
        return "wrong-fine-family"
    if prediction.get("runtime_verified") is False:
        return "runtime-rejected"
    if prediction.get("agda_verified") is False:
        return "agda-rejected"
    return None


def analyze(dataset: list[dict], predictions: list[dict]) -> dict:
    gold = {row["id"]: row for row in dataset}
    rows: list[dict] = []
    for prediction in predictions:
        if prediction["id"] not in gold:
            continue
        error = category(gold[prediction["id"]], prediction)
        if error is not None:
            rows.append(
                {
                    "id": prediction["id"],
                    "ablation": prediction["ablation"],
                    "direction": gold[prediction["id"]]["direction"],
                    "gold": gold[prediction["id"]]["gold"],
                    "prediction": prediction.get("prediction"),
                    "path": prediction.get("path", []),
                    "error_category": error,
                }
            )
    return {
        "counts": dict(Counter(row["error_category"] for row in rows)),
        "errors": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = analyze(
        read_jsonl(arguments.dataset),
        read_jsonl(arguments.predictions),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
