#!/usr/bin/env python3
"""Extract SelectionalPreference candidates awaiting promotion evidence.

Reads a predictions.jsonl file (produced by run_engine_predictions.py) and
the corresponding *.inputs.jsonl it was run against, joins them by id, and
emits one row per instance whose prediction, for the given ablation,
abstained specifically because it found a checked SelectionalPreference
candidate with no promotion evidence (abstention_reason starting with
"selectional-preference:") -- see engine/src/Metonymy/OpenDomain.hs and
Main.hs's renderOpenBatchRow.

Output rows carry the exact raw target EntityId (embedded in
abstention_reason as a trailing tab-separated field, not the
human-readable surface label), which is what
scripts/propose_promotion_evidence.py must reference for the evidence to
match under Agda's checkPromotion (string equality against the candidate's
actual fine target, not a paraphrase of it).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


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


def extract(
    predictions: list[dict], inputs_by_id: dict[str, dict], ablation: str
) -> list[dict]:
    candidates: list[dict] = []
    for row in predictions:
        if row.get("ablation") != ablation:
            continue
        if row.get("status") != "abstain":
            continue
        reason = row.get("abstention_reason", "")
        if not reason.startswith("selectional-preference:") or "\t" not in reason:
            continue
        surface_part, target_entity_id = reason.split("\t", 1)
        surface = surface_part[len("selectional-preference:") :]
        source_row = inputs_by_id.get(row["id"])
        if source_row is None:
            continue
        candidates.append(
            {
                "id": row["id"],
                "sentence": source_row.get("text", ""),
                "target": source_row.get("target", ""),
                "family": row.get("predicted_bridge", ""),
                "target_entity_id": target_entity_id,
                "target_surface": surface,
            }
        )
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--ablation", default="full")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    predictions = read_jsonl(arguments.predictions)
    inputs_by_id = {row["id"]: row for row in read_jsonl(arguments.inputs)}
    candidates = extract(predictions, inputs_by_id, arguments.ablation)

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8") as handle:
        for candidate in candidates:
            handle.write(json.dumps(candidate, sort_keys=True) + "\n")
    print(f"extracted {len(candidates)} promotion candidates")


if __name__ == "__main__":
    main()
