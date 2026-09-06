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


# Every short, fixed error token that can show up in an exit-1 row's
# "failure" text. Three distinct sources feed this same exit code:
# resolve_action/propose_contextual_scenario.py's own ValueErrors
# (contextual_rule_compiler.py, propose_contextual_scenario.py); the
# compiled engine's own `die` messages (System.Exit.die always exits 1),
# built as "contextual fiber failed: <reason>" from Metonymy.Contextual's
# validateContext/contextualFiber (empty-snapshot-hash/empty-action/
# tree-without-lexical-leaves/empty-constraint-provenance/unknown-
# constraint-provenance/invalid-lexical-span/snapshot-hash-mismatch/
# invalid-max-depth) and Metonymy.ContextualChecked's own per-stage Agda
# cross-check (agda-rejected-survivor-at-stage-/agda-accepted-
# obstruction-at-stage-/agda-rejected-preference-at-stage-/agda-accepted-
# preference-miss-at-stage-, each followed by a stage number this
# deliberately does not capture); and -- an easy one to miss, since it
# fires before any command dispatch, let alone the fiber computation
# above -- Metonymy.ContextSpec.loadContextScenarios's own scenario-TSV
# parsing, which runs unconditionally at the very start of every engine
# invocation and raises via plain `fail`, not `die`, so GHC's default
# top-level handler (not System.Exit.die's convention) formats the
# message, still exiting 1 either way (unknown contextual scenario:/
# empty contextual scenario file:/unexpected contextual scenario header:/
# expected seven tab-separated fields/malformed contextual constraint:/
# unknown symbolic value:). run_automatic_contextual_pipeline.py's
# multi-candidate disambiguation loop (see its own module docstring)
# reaches all of this by propagating a representative candidate's own
# exit code when *no* candidate's engine run succeeds. All of these are
# the *names* of failure conditions, never sentence text, so matching one
# out of a subprocess's combined stdout+stderr and reporting only the
# matched token, never the surrounding text, stays safe to upload even
# though the untruncated text (which does echo sentence text -- e.g.
# propose_contextual_scenario.py prints the offending gf_sentence/gf_tree
# on some failures, and a malformed-constraint message echoes the
# offending encoded constraint, which can include a source word) is not.
KNOWN_FAILURE_TOKENS = (
    "target-occurrence-not-found",
    "unsupported-action-role",
    "nested-modifier-unsupported",
    "source-qid-unresolved",
    "contract-target-qid-unresolved",
    "unsupported-linker-cache-schema",
    "empty-snapshot-hash",
    "empty-action",
    "tree-without-lexical-leaves",
    "empty-constraint-provenance",
    "unknown-constraint-provenance",
    "invalid-lexical-span",
    "snapshot-hash-mismatch",
    "invalid-max-depth",
    "agda-rejected-survivor-at-stage-",
    "agda-accepted-obstruction-at-stage-",
    "agda-rejected-preference-at-stage-",
    "agda-accepted-preference-miss-at-stage-",
    "unknown contextual scenario:",
    "empty contextual scenario file:",
    "unexpected contextual scenario header:",
    "expected seven tab-separated fields",
    "malformed contextual constraint:",
    "unknown symbolic value:",
)


def exit2_candidate_bucket(failure_text: str) -> str:
    """Split exit 2 (source-qid-unresolved) into zero vs ambiguous candidates.

    run_automatic_contextual_pipeline.py's exit-2 branch prints the full
    proposal dict -- including "source_qid_candidates", a list of QIDs,
    never sentence text -- to stdout before raising SystemExit(2), and
    that is the only thing it prints on that path; run_contextual_corpus.py
    captures the subprocess's stdout+stderr into this row's "failure"
    field unconditionally on any non-zero exit, not only exit 1. Parsing
    it back out distinguishes "the surface matched no Wikidata alias at
    all" from "the surface matched more than one, and the linker's
    exact-alias-or-abstain policy (build_wikidata_api_index.py's
    search_exact: "an ambiguous surface simply resolves to more than one
    QID here, and callers decide what to do with that") refused to
    guess" -- two causes needing very different fixes, previously
    conflated under one undifferentiated "failed:exit2" tally. A QID list
    carries no sentence text, so this stays as safe to upload as the
    exit-1 token extraction above. Falls back to "unrecognized" if the
    field isn't parseable JSON with that key, so an unexpected shape
    degrades gracefully instead of crashing the scorer.
    """
    try:
        candidates = json.loads(failure_text)["source_qid_candidates"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return "unrecognized"
    if not candidates:
        return "zero-candidates"
    return "ambiguous-candidates"


def literal_reason(inference_row: dict) -> str:
    """A text-free tag for why a row predicted "literal" -- status plus
    exit code (run_automatic_contextual_pipeline.py uses a distinct exit
    code per failure kind: 3 gf-parse-failed, 4 semantic-composition-
    failed, 5 contract-target-qid-unresolved, 2 source-qid-unresolved -- no
    candidate QID at all for the source surface in the snapshot's own
    aliases.jsonl, or (--contract-target only) not exactly one -- 6
    source-disambiguation-ambiguous -- two or more source candidates each
    independently ran the tower's full per-layer narrowing to a non-empty
    final fiber, and the pipeline refuses to guess between them). Exit 1
    covers two different origins that both end up looking identical at
    this level -- everything resolve_action/propose_contextual_scenario.py
    itself raises as a ValueError (target-occurrence-not-found/
    unsupported-action-role/nested-modifier-unsupported), reaching
    run_automatic_contextual_pipeline.py as an uncaught CalledProcessError
    from its own `subprocess.run(..., check=True)` call; *and* the case
    where every one of the disambiguation loop's candidates failed its own
    engine invocation outright (not just an empty fiber), which the
    pipeline surfaces by propagating that candidate's own exit code --
    always 1, since the engine's `die` (System.Exit.die) always does --
    with the engine's own stderr message, never JSON-wrapped. The exit
    code alone can't tell any of this apart, so for exit 1 this also
    searches the row's own "failure" text (never exposed itself) for one of
    KNOWN_FAILURE_TOKENS and reports only the matched token name, or
    "failed:exit1:unrecognized" if none match. Exit 2 similarly gets a
    sub-tag from exit2_candidate_bucket -- see its own docstring. Carries
    no sentence text either way, so this is safe to upload as a CI
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
    if exit_code == 2:
        return f"failed:exit2:{exit2_candidate_bucket(inference_row.get('failure', ''))}"
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
