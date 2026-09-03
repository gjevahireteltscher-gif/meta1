#!/usr/bin/env python3
"""Run the controlled-language engine for every fixed ablation condition."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
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


def open_batch_row_fields(row: dict) -> list[str]:
    span = row.get("target_span", row.get("target_spans", [[0, 0]])[0])
    return [
        row["id"],
        "wimcor" if row["source"] == "wimcor-v1.1" else "conmec",
        row.get("category", "LOCATION"),
        row["target"].replace("\t", " ").replace("\n", " "),
        str(span[0]),
        str(span[1]),
        row["text"].replace("\t", " ").replace("\n", " "),
    ]


def predict_open_batch(
    engine: Path,
    rows: list[dict],
    ablation: str,
    frontend: str = "legacy",
    dependency_hints: dict[str, dict] | None = None,
    evidence: Path | None = None,
) -> dict[str, dict]:
    """Run one ablation over ``rows`` through ``open-batch``.

    ``frontend="legacy"`` (the default) builds exactly the 7-field TSV rows
    this function has always produced, so existing evaluation runs stay
    byte-for-byte reproducible. ``frontend="dependency"`` appends the three
    UD-parser-derived columns from ``dependency_hints`` (see
    scripts/annotate_dependency_hints.py); a row missing a hint falls back
    to the legacy 7-field shape for that one instance, with a warning, so a
    partial hints file degrades gracefully rather than crashing the batch.
    """
    lines = []
    for row in rows:
        fields = open_batch_row_fields(row)
        if frontend == "dependency":
            hint = (dependency_hints or {}).get(row["id"])
            if hint is None:
                print(
                    f"warning: no dependency hint for {row['id']!r}, "
                    "falling back to the legacy frontend for this row",
                    file=sys.stderr,
                )
            else:
                fields = fields + [
                    hint.get("hole_role", ""),
                    hint.get("governing_lemma", ""),
                    hint["dep_status"],
                ]
        lines.append("\t".join(fields))
    payload = "".join(line + "\n" for line in lines)
    command = [str(engine), "open-batch", ablation]
    if evidence is not None:
        command += ["--evidence", str(evidence)]
    process = subprocess.run(
        command,
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
    parser.add_argument(
        "--frontend",
        choices=["legacy", "dependency"],
        default="legacy",
        help=(
            "legacy: today's positional string-heuristic open-domain "
            "frontend (default, unchanged). dependency: use UD-parser "
            "hints from --dependency-hints (see "
            "scripts/annotate_dependency_hints.py) instead."
        ),
    )
    parser.add_argument(
        "--dependency-hints",
        type=Path,
        help="dependency-hints.jsonl produced by annotate_dependency_hints.py; "
        "required when --frontend dependency is used",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        help="promotion-evidence TSV (id, target_entity_id, source) produced by "
        "scripts/propose_promotion_evidence.py; promotes matching "
        "SelectionalPreference candidates, subject to the compiled Agda "
        "checkPromotion re-verifying the target and a non-empty source "
        "(see engine/src/Metonymy/OpenDomain.hs's loadPromotionEvidence). "
        "The no-context ablation withholds it regardless.",
    )
    arguments = parser.parse_args()
    if arguments.frontend == "dependency" and arguments.dependency_hints is None:
        raise SystemExit("--frontend dependency requires --dependency-hints")
    if not arguments.engine.exists():
        raise SystemExit(f"engine does not exist: {arguments.engine}")
    dependency_hints: dict[str, dict] = {}
    if arguments.dependency_hints is not None:
        dependency_hints = {
            hint["id"]: hint for hint in read_jsonl(arguments.dependency_hints)
        }
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
                arguments.engine,
                open_rows,
                ablation,
                frontend=arguments.frontend,
                dependency_hints=dependency_hints,
                evidence=arguments.evidence,
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
