#!/usr/bin/env python3
"""Independent scorer for metonymy expansion and contraction predictions."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

LABELS = ("literal", "metonymic", "mixed")
STATUSES = {"emitted", "no_rewrite", "abstain", "error"}
ABLATIONS = {"full", "no-types", "no-ontology", "no-context", "no-verbnet"}
DIRECTIONS = {"expand", "contract"}


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
    return rows


def safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or precision + recall == 0:
        return None if precision is None or recall is None else 0.0
    return 2 * precision * recall / (precision + recall)


def validate(dataset: Iterable[dict], predictions: Iterable[dict]) -> None:
    dataset_rows = list(dataset)
    prediction_rows = list(predictions)
    ids = [row["id"] for row in dataset_rows]
    if len(ids) != len(set(ids)):
        raise ValueError("dataset contains duplicate ids")
    known = set(ids)
    keys: set[tuple[str, str]] = set()
    for row in dataset_rows:
        if row.get("direction") not in DIRECTIONS:
            raise ValueError(f"{row.get('id')}: invalid direction")
        if row.get("gold") not in LABELS:
            raise ValueError(f"{row.get('id')}: invalid gold label")
    for row in prediction_rows:
        identifier = row.get("id")
        ablation = row.get("ablation")
        status = row.get("status")
        if identifier not in known:
            raise ValueError(f"prediction references unknown id: {identifier}")
        if ablation not in ABLATIONS:
            raise ValueError(f"{identifier}: invalid ablation {ablation}")
        if status not in STATUSES:
            raise ValueError(f"{identifier}: invalid status {status}")
        if status in {"emitted", "no_rewrite"} and row.get("prediction") not in LABELS:
            raise ValueError(f"{identifier}: submitted prediction lacks a valid label")
        key = (identifier, ablation)
        if key in keys:
            raise ValueError(f"duplicate prediction: {identifier}/{ablation}")
        keys.add(key)


def score_group(dataset: list[dict], predictions: list[dict]) -> dict:
    gold = {row["id"]: row["gold"] for row in dataset}
    dataset_by_id = {row["id"]: row for row in dataset}
    submitted = [
        row for row in predictions if row["status"] in {"emitted", "no_rewrite"}
    ]
    correct = sum(row["prediction"] == gold[row["id"]] for row in submitted)
    total = len(dataset)
    confusion = Counter(
        (gold[row["id"]], row["prediction"]) for row in submitted
    )
    per_class: dict[str, dict] = {}
    for label in LABELS:
        tp = confusion[(label, label)]
        fp = sum(
            count
            for (actual, predicted), count in confusion.items()
            if predicted == label and actual != label
        )
        fn = sum(1 for actual in gold.values() if actual == label) - tp
        precision = safe_ratio(tp, tp + fp)
        recall = safe_ratio(tp, tp + fn)
        per_class[label] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1(precision, recall),
        }
    class_f1 = [
        metrics["f1"] for metrics in per_class.values() if metrics["f1"] is not None
    ]
    precision = safe_ratio(correct, len(submitted))
    recall = safe_ratio(correct, total)
    bridge_rows = [
        row
        for row in submitted
        if dataset_by_id[row["id"]].get("gold_bridge")
        and row.get("prediction") == "metonymic"
    ]
    bridge_correct = sum(
        row.get("predicted_bridge")
        == dataset_by_id[row["id"]].get("gold_bridge")
        for row in bridge_rows
    )
    prediction_by_id = {row["id"]: row for row in predictions}
    endpoint_gold_rows = [
        row
        for row in dataset
        if row.get("gold") == "metonymic" and row.get("explicit_target")
    ]
    endpoint_rows = [
        prediction_by_id[row["id"]]
        for row in endpoint_gold_rows
        if prediction_by_id.get(row["id"], {}).get("predicted_endpoint")
    ]
    endpoint_correct = sum(
        row["predicted_endpoint"].strip().casefold()
        == dataset_by_id[row["id"]]["explicit_target"].strip().casefold()
        for row in endpoint_rows
    )
    return {
        "instances": total,
        "submitted": len(submitted),
        "correct": correct,
        "coverage": safe_ratio(len(submitted), total),
        "selective_accuracy": precision,
        "micro_precision": precision,
        "micro_recall": recall,
        "micro_f1": f1(precision, recall),
        "macro_f1": sum(class_f1) / len(class_f1) if class_f1 else None,
        "bridge_family": {
            "evaluated": len(bridge_rows),
            "correct": bridge_correct,
            "accuracy": safe_ratio(bridge_correct, len(bridge_rows)),
        },
        "endpoint": {
            "gold_instances": len(endpoint_gold_rows),
            "evaluated": len(endpoint_rows),
            "correct": endpoint_correct,
            "selective_accuracy": safe_ratio(endpoint_correct, len(endpoint_rows)),
            "end_to_end_accuracy": safe_ratio(
                endpoint_correct, len(endpoint_gold_rows)
            ),
            "recall_at_1": safe_ratio(
                endpoint_correct, len(endpoint_gold_rows)
            ),
        },
        "per_class": per_class,
        "confusion": {
            f"{actual}->{predicted}": count
            for (actual, predicted), count in sorted(confusion.items())
        },
        "statuses": dict(Counter(row["status"] for row in predictions)),
    }


def score(dataset: list[dict], predictions: list[dict]) -> dict:
    validate(dataset, predictions)
    report: dict[str, dict] = {}
    for ablation in sorted(ABLATIONS):
        ablation_predictions = [
            row for row in predictions if row["ablation"] == ablation
        ]
        if not ablation_predictions:
            continue
        report[ablation] = {}
        for direction in sorted(DIRECTIONS):
            direction_dataset = [
                row for row in dataset if row["direction"] == direction
            ]
            direction_ids = {row["id"] for row in direction_dataset}
            direction_predictions = [
                row for row in ablation_predictions if row["id"] in direction_ids
            ]
            report[ablation][direction] = score_group(
                direction_dataset, direction_predictions
            )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    report = score(
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
