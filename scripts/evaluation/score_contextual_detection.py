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
import hashlib
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

# Generic GHC/Prelude runtime-crash signatures -- a different *kind* of
# token from KNOWN_FAILURE_TOKENS above: those are precise, this-codebase-
# specific named failure conditions (an explicit `Left "reason"` or `fail
# "reason"` this project's own code chose to raise); these are the
# standard library's own well-known partial-function/pattern-match/
# arithmetic crash message prefixes, which any GHC program can hit
# whenever such a function is applied outside its domain (e.g. `head` on
# an empty list) -- something this codebase does not raise on purpose.
# Motivation: two rounds of adding KNOWN_FAILURE_TOKENS entries (both
# guessed from reading Metonymy.Contextual/ContextualChecked/ContextSpec's
# own explicit Left/fail sites) changed nothing -- a real
# contextual-tower-evaluation.yml run produced byte-identical
# "unrecognized" counts before and after both additions, meaning neither
# round's tokens matched anything. `Checker.hs` (compiled from Agda,
# Metonymy.ContextualChecked's `verifyContextLayerWithAgda` calls into it)
# produced real GHC compiler warnings during this project's own build
# about exactly this class of partial function ("throws an error on empty
# lists... consider... Data.List.NonEmpty") -- and the live-API-built
# snapshot's own sparser entities (a same-named-place candidate with zero
# claims at all, confirmed by locally reproducing the real sample) are
# exactly the kind of edge case a curated, hand-picked snapshot would
# never have exercised. Deliberately broad rather than an exact function
# name, since GHC's own message varies by which partial function actually
# ran out of domain and this project cannot predict that in advance; still
# safe to match on since these are fixed standard-library message
# prefixes, never sentence text.
GENERIC_RUNTIME_CRASH_TOKENS = (
    "Prelude.",
    "Non-exhaustive patterns",
    "divide by zero",
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
    covers three different origins that all end up looking identical at
    this level -- everything resolve_action/propose_contextual_scenario.py
    itself raises as a ValueError (target-occurrence-not-found/
    unsupported-action-role/nested-modifier-unsupported), reaching
    run_automatic_contextual_pipeline.py as an uncaught CalledProcessError
    from its own `subprocess.run(..., check=True)` call; the case where
    every one of the disambiguation loop's candidates failed its own
    engine invocation outright (not just an empty fiber), which the
    pipeline surfaces by propagating that candidate's own exit code; and,
    within that same case, GHC's own exit code for an uncaught runtime
    exception (a partial function applied outside its domain, a
    non-exhaustive pattern match, ...) -- always 1 as well, same as
    System.Exit.die and a `fail` reaching GHC's default top-level handler,
    so the exit code alone genuinely cannot tell any of these three apart
    (see GENERIC_RUNTIME_CRASH_TOKENS's own comment for why that
    possibility gets a second, broader pass). So for exit 1 this also
    searches the row's own "failure" text (never exposed itself) for one of
    KNOWN_FAILURE_TOKENS, then -- if none of those precise, this-codebase
    tokens match -- one of GENERIC_RUNTIME_CRASH_TOKENS (see its own
    comment for why a separate, broader pass exists), and reports only the
    matched token name, or "failed:exit1:unrecognized" if neither matches.
    Exit 2 similarly gets a sub-tag from exit2_candidate_bucket -- see its
    own docstring. Carries no sentence text either way, so this is safe to
    upload as a CI artifact even though the inference row it's drawn from
    is not.
    """
    if inference_row.get("status") == "ok":
        return "ok:empty-fiber"
    exit_code = inference_row.get("exit_code", "unknown")
    if exit_code == 1:
        failure_text = inference_row.get("failure", "")
        for token in KNOWN_FAILURE_TOKENS:
            if token in failure_text:
                return f"failed:exit1:{token}"
        for token in GENERIC_RUNTIME_CRASH_TOKENS:
            if token in failure_text:
                return f"failed:exit1:{token}"
        return "failed:exit1:unrecognized"
    if exit_code == 2:
        return f"failed:exit2:{exit2_candidate_bucket(inference_row.get('failure', ''))}"
    return f"failed:exit{exit_code}"


def fingerprint_failure_text(failure_text: str) -> dict:
    """A safe, content-free fingerprint of a failure text: a short hash
    prefix and a character length, never the text itself.

    Exists specifically for "failed:exit1:unrecognized" rows -- two
    consecutive contextual-tower-evaluation.yml runs added 18 precise
    KNOWN_FAILURE_TOKENS entries and 3 broad GENERIC_RUNTIME_CRASH_TOKENS
    ones with zero matches either time, burning a CI round trip each time
    on a guess. This answers a cheaper, more useful question first --
    "is this one repeated message or many different ones" -- without
    needing another guess: a single dominant sha256_prefix repeated
    across most/all "unrecognized" rows means one root cause; many
    distinct ones means several unrelated things are going wrong at once.
    12 hex characters of SHA-256 (48 bits) makes an accidental collision
    among a few hundred rows astronomically unlikely, so equal prefixes
    reliably mean equal underlying text without ever transmitting it.
    """
    return {
        "sha256_prefix": hashlib.sha256(failure_text.encode("utf-8")).hexdigest()[:12],
        "length": len(failure_text),
    }


def score(inference_rows: list[dict], gold_rows: list[dict]) -> dict:
    inference_by_id = {row["id"]: row for row in inference_rows}
    true_positive = false_positive = true_negative = false_negative = 0
    missing = 0
    literal_prediction_reasons: Counter[str] = Counter()
    unrecognized_fingerprints: Counter[tuple[str, int]] = Counter()
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
            reason = literal_reason(inference_row)
            literal_prediction_reasons[reason] += 1
            if reason == "failed:exit1:unrecognized":
                fingerprint = fingerprint_failure_text(inference_row.get("failure", ""))
                unrecognized_fingerprints[
                    (fingerprint["sha256_prefix"], fingerprint["length"])
                ] += 1

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
        "unrecognized_fingerprints": [
            {"sha256_prefix": prefix, "length": length, "count": count}
            for (prefix, length), count in sorted(
                unrecognized_fingerprints.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ],
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
