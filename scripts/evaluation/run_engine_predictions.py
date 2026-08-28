#!/usr/bin/env python3
"""Run the controlled-language engine for every fixed ablation condition."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from score_predictions import ABLATIONS, read_jsonl

RELATION = re.compile(r"--([A-Za-z0-9_]+)-->")
FAMILY = re.compile(r"\bfamily=([a-z0-9-]+)")
ENDPOINT = re.compile(r"^endpoint=(.*)$", re.MULTILINE)


def predict(engine: Path, row: dict, ablation: str) -> dict:
    text = row.get("text")
    if not text:
        return {
            "id": row["id"],
            "ablation": ablation,
            "status": "abstain",
            "abstention_reason": "missing-local-context",
        }
    source = row.get("source", "")
    if source in {"wimcor-v1.1", "conmec"}:
        command = [
            str(engine),
            "open-evaluate",
            ablation,
            "wimcor" if source == "wimcor-v1.1" else "conmec",
            row.get("category", "LOCATION"),
            row["target"],
            text,
        ]
    else:
        command = [
            str(engine),
            "evaluate",
            ablation,
            row["direction"],
            text,
        ]
    process = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip()
        reason = (
            "parse-abstention"
            if "GF parse failed" in message
            else "resolution-abstention"
        )
        return {
            "id": row["id"],
            "ablation": ablation,
            "status": "abstain",
            "abstention_reason": reason,
        }
    if "status=abstain" in process.stdout or "status=rejected" in process.stdout:
        return {
            "id": row["id"],
            "ablation": ablation,
            "status": "abstain",
            "abstention_reason": (
                "formal-rejection"
                if "status=rejected" in process.stdout
                else "frontend-abstention"
            ),
        }
    if "status=no-rewrite" in process.stdout:
        return {
            "id": row["id"],
            "ablation": ablation,
            "status": "no_rewrite",
            "prediction": "literal",
            "runtime_verified": True,
            "agda_verified": True,
        }
    relations = RELATION.findall(process.stdout)
    family = FAMILY.search(process.stdout)
    endpoint = ENDPOINT.search(process.stdout)
    return {
        "id": row["id"],
        "ablation": ablation,
        "status": "emitted",
        "prediction": "metonymic",
        "path": relations,
        "predicted_bridge": family.group(1) if family else None,
        "predicted_endpoint": endpoint.group(1) if endpoint else None,
        "runtime_verified": "status=" in process.stdout,
        "agda_verified": "certificate=agda-verified-" in process.stdout,
    }


def predict_open_batch(
    engine: Path, rows: list[dict], ablation: str
) -> dict[str, dict]:
    payload = "".join(
        "\t".join(
            [
                row["id"],
                "wimcor" if row["source"] == "wimcor-v1.1" else "conmec",
                row.get("category", "LOCATION"),
                row["target"].replace("\t", " ").replace("\n", " "),
                str(row.get("target_span", row.get("target_spans", [[0, 0]])[0])[0]),
                str(row.get("target_span", row.get("target_spans", [[0, 0]])[0])[1]),
                row["text"].replace("\t", " ").replace("\n", " "),
            ]
        )
        + "\n"
        for row in rows
    )
    process = subprocess.run(
        [str(engine), "open-batch", ablation],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "open-batch failed")
    predictions: dict[str, dict] = {}
    for line in process.stdout.splitlines():
        identifier, status, prediction, family, detail = line.split("\t", 4)
        row = {
            "id": identifier,
            "ablation": ablation,
            "status": "abstain" if status == "rejected" else status,
        }
        if prediction:
            row["prediction"] = prediction
        if family:
            row["predicted_bridge"] = family
        if status == "emitted":
            row["predicted_endpoint"] = detail
            row["runtime_verified"] = True
            row["agda_verified"] = True
        elif status == "no_rewrite":
            row["runtime_verified"] = True
            row["agda_verified"] = True
        else:
            row["abstention_reason"] = detail
        predictions[identifier] = row
    if len(predictions) != len(rows):
        raise RuntimeError(
            f"open-batch returned {len(predictions)} rows for {len(rows)} inputs"
        )
    return predictions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, default=Path("build/metonymy"))
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-gold-input", action="store_true")
    arguments = parser.parse_args()
    if not arguments.engine.exists():
        raise SystemExit(f"engine does not exist: {arguments.engine}")
    dataset = read_jsonl(arguments.dataset)
    forbidden = {"gold", "gold_fine", "gold_bridge", "explicit_target"}
    if not arguments.allow_gold_input:
        leaked = [
            row["id"]
            for row in dataset
            if any(key in row for key in forbidden)
        ]
        if leaked:
            raise SystemExit(
                "inference input contains scoring-only gold fields; "
                "run split_inputs_gold.py first"
            )
    open_rows = [
        row
        for row in dataset
        if row.get("source") in {"wimcor-v1.1", "conmec"}
    ]
    batched: dict[tuple[str, str], dict] = {}
    if open_rows:
        for ablation in sorted(ABLATIONS):
            for identifier, prediction in predict_open_batch(
                arguments.engine, open_rows, ablation
            ).items():
                batched[(identifier, ablation)] = prediction
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8") as output:
        for row in dataset:
            for ablation in sorted(ABLATIONS):
                prediction = batched.get((row["id"], ablation))
                if prediction is None:
                    prediction = predict(arguments.engine, row, ablation)
                output.write(
                    json.dumps(
                        prediction,
                        sort_keys=True,
                    )
                    + "\n"
                )


if __name__ == "__main__":
    main()
