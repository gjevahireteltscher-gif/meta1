#!/usr/bin/env python3
"""Score the contextual tower's metonymic-vs-literal detection.

WiMCor/ConMeC gold only ever says metonymic-vs-literal plus a bridge-
family type; neither annotates a specific correct Wikidata entity, so
score_qid_fibers.py's exact-QID-in-fiber metric cannot be computed for
them at all -- there is no gold_qids field to compare against. This
scores the weaker claim these corpora actually support: for a
gold-metonymic mention, did the tower successfully run and produce a
non-empty final fiber (some bridged reading survived every stage); for a
gold-literal mention, did it correctly produce none.

This mapping is a design choice, not a re-derivation of something the
engine already reports as a "detected" flag -- the tower has no native
metonymic/literal output, only a per-run status and a final fiber (see
scripts/evaluation/run_contextual_corpus.py's run_one). "status == ok and
fiber non-empty" is treated as a positive prediction; every kind of
failure (GF parse failure, unsupported action role, semantic-composition
failure, or a successful run that filters the fiber down to nothing) is
treated as a negative one, mirroring how the flat pipeline's own
emitted/abstain split already works. Verify this mapping is what the
paper wants before citing raw precision/recall/F1 from it.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def jsonl(path: Path):
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def predict(inference_row: dict) -> str:
    if inference_row.get("status") == "ok" and inference_row.get("fiber"):
        return "metonymic"
    return "literal"


# Every short, fixed error token resolve_action/propose_contextual_scenario.py
# can raise (contextual_rule_compiler.py, propose_contextual_scenario.py).
# These strings never contain sentence text -- they are the *names* of
# failure conditions -- so matching one out of a subprocess's combined
# stdout+stderr traceback and reporting only the matched token, never the
# surrounding text, stays safe to upload even though the untruncated
# traceback (which does echo sentence text -- e.g. propose_contextual_scenario.py
# prints the offending gf_sentence/gf_tree on some failures) is not.
KNOWN_FAILURE_TOKENS = (
    "target-occurrence-not-found",
    "unsupported-action-role",
    "nested-modifier-unsupported",
    "source-qid-unresolved",
    "contract-target-qid-unresolved",
    "unsupported-linker-cache-schema",
)


def literal_reason(inference_row: dict) -> str:
    """A text-free tag for why a row predicted "literal" -- status plus
    exit code (run_automatic_contextual_pipeline.py uses a distinct exit
    code per failure kind: 3 gf-parse-failed, 4 semantic-composition-
    failed, 5 contract-target-qid-unresolved, 2 source-qid-unresolved -- a
    resolved target_surface has no unique QID in the snapshot's own
    aliases.jsonl). Exit 1 covers everything resolve_action/
    propose_contextual_scenario.py itself raises as a ValueError
    (target-occurrence-not-found/unsupported-action-role/nested-modifier-
    unsupported), which reaches run_automatic_contextual_pipeline.py as an
    uncaught CalledProcessError from its own `subprocess.run(...,
    check=True)` call -- the exit code alone can't tell those apart, so
    for exit 1 this also searches the row's own "failure" text (never
    exposed itself) for one of KNOWN_FAILURE_TOKENS and reports only the
    matched token name, or "failed:exit1:unrecognized" if none match.
    Carries no sentence text either way, so this is safe to upload as a CI
    artifact even though the inference row it's drawn from is not.
    """
    if inference_row.get("status") == "ok":
        return "ok:empty-fiber"
    exit_code = inference_row.get("exit_code", "unknown")
    if exit_code == 1:
        failure_text = inference_row.get("failure", "")
        for token in KNOWN_FAILURE_TOKENS:
            if token in failure_text:
                return f"failed:exit1:{token}"
        return "failed:exit1:unrecognized"
    return f"failed:exit{exit_code}"


def score(inference_rows: list[dict], gold_rows: list[dict]) -> dict:
    inference_by_id = {row["id"]: row for row in inference_rows}
    true_positive = false_positive = true_negative = false_negative = 0
    missing = 0
    literal_prediction_reasons: Counter[str] = Counter()
    for gold in gold_rows:
        inference_row = inference_by_id.get(gold["id"])
        if inference_row is None:
            missing += 1
            continue
        predicted = predict(inference_row)
        actual = gold["gold_label"]
        if predicted == "metonymic" and actual == "metonymic":
            true_positive += 1
        elif predicted == "metonymic" and actual == "literal":
            false_positive += 1
        elif predicted == "literal" and actual == "literal":
            true_negative += 1
        else:
            false_negative += 1
        if predicted == "literal":
            literal_prediction_reasons[literal_reason(inference_row)] += 1

    precision = (
        true_positive / (true_positive + false_positive)
        if (true_positive + false_positive)
        else None
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if (true_positive + false_negative)
        else None
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and (precision + recall)
        else None
    )
    return {
        "instances": len(gold_rows),
        "missing_inference_rows": missing,
        "confusion": {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "true_negative": true_negative,
            "false_negative": false_negative,
        },
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "literal_prediction_reasons": dict(sorted(literal_prediction_reasons.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", required=True, type=Path)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    gold_rows = list(jsonl(args.gold))
    if not gold_rows:
        raise SystemExit("gold file is empty")
    report = score(list(jsonl(args.inference)), gold_rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"f1": report["f1"], "instances": report["instances"]}, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
