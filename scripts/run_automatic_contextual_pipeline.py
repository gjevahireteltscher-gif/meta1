#!/usr/bin/env python3
"""Run text → proposal → data scenario → checked contextual tower.

Entity linking for the source mention (propose_contextual_scenario.py) is
allowed to be ambiguous: a surface like "Liverpool" routinely resolves to a
dozen distinct Wikidata QIDs (the real city, plus a pile of identically
named US townships -- see data/SOURCES.md). The action/role requirement,
the GF parse, and the compiled constraint set are all independent of which
QID that turns out to be, so this pipeline computes them exactly once and
then runs the contextual tower's own existing per-layer narrowing (the
same stage-by-stage HasSort/relation filtering that already narrows
candidate bridge *targets*) once per candidate source QID. A candidate
"survives" if its own run ends with a non-empty final-stage fiber -- i.e.
the tower found something reachable from *that* candidate satisfying every
constraint the sentence's own words imposed, which is exactly the
signal that distinguishes the real Liverpool (reachable to a university
satisfying the sentence's role/topic requirements) from a same-named
census-designated place (reachable to nothing that fits). Three outcomes:
exactly one candidate survives -> that is the answer, printed and scored
exactly as a single-candidate run always was; zero survive -> a legitimate
"no metonymic reading found" result (empty fiber, still exit 0, still
scored as literal), using any one candidate's own (empty) trace since
they are interchangeable; two or more survive -> genuine, irreducible
ambiguity even after full contextual narrowing, which gets its own
SystemExit(6) rather than silently picking one (the same
exact-match-or-abstain policy the entity linker itself already follows).

This candidate loop only applies to the "expand" direction
(contextual-fiber). --contract-target uses a different, safety-sensitive
operation (a contraction can be *correctly* rejected by the formal
checker, which is not a failure to disambiguate) and keeps requiring
exactly one resolved source QID, unchanged.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from contextual_rule_compiler import compile_gf_constraints

HEADER = "scenario\tsource_qid\taction\trole\tmax_depth\tbridge_relations\tconstraints\n"
FINAL_SURVIVORS = re.compile(r"survivors=(\[[^\]]*\])")
QID = re.compile(r"Q[0-9]+")


def final_fiber(stdout: str) -> list[str]:
    """The last "survivors=[...]" line's QIDs, or [] if there is none.

    Mirrors scripts/evaluation/run_contextual_corpus.py's own stage
    parsing (it keeps the *last* stage's survivors as the final fiber);
    duplicated narrowly here rather than imported, since that module is
    the batch-corpus driver and pulls in evaluation-only dependencies this
    single-instance pipeline script doesn't otherwise need.
    """
    matches = FINAL_SURVIVORS.findall(stdout)
    return QID.findall(matches[-1]) if matches else []


def encode_constraint(constraint: dict) -> str:
    origin = constraint["origin"]
    prefix = "|".join(
        [
            origin["constructor"],
            origin["lemma"],
            origin["surface"],
            str(origin["start"]),
            str(origin["end"]),
        ]
    )
    payload = constraint["payload"]
    if "requires" in payload:
        return (
            prefix
            + "|requires|"
            + payload["requires"]
            + "|"
            + constraint["provenance"]
        )
    if "prefers" in payload:
        return (
            prefix
            + "|prefers|"
            + payload["prefers"]
            + "|"
            + constraint["provenance"]
        )
    if "prefers_some" in payload:
        related = payload["prefers_some"]
        return (
            prefix
            + "|prefers-some|"
            + related["relation"]
            + "|"
            + related["requirement"]
            + "|"
            + constraint["provenance"]
        )
    if "prefers_relation" in payload:
        relation = payload["prefers_relation"]
        return (
            prefix
            + "|prefers-relation|"
            + relation["relation"]
            + "|"
            + relation["target"]
            + "|"
            + constraint["provenance"]
        )
    if "requires_some" in payload:
        related = payload["requires_some"]
        return (
            prefix
            + "|some|"
            + related["relation"]
            + "|"
            + related["requirement"]
            + "|"
            + constraint["provenance"]
        )
    relation = payload["requires_relation"]
    return (
        prefix
        + "|relation|"
        + relation["relation"]
        + "|"
        + relation["target"]
        + "|"
        + constraint["provenance"]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--sentence", required=True)
    parser.add_argument("--source")
    parser.add_argument("--linker-cache", type=Path)
    parser.add_argument("--contract-target")
    parser.add_argument(
        "--dependency-hint",
        help=(
            "compact JSON object precomputed by annotate_dependency_hints.py, "
            "passed through to propose_contextual_scenario.py"
        ),
    )
    parser.add_argument("--rules", default="data/contextual-language-rules.json")
    parser.add_argument(
        "--gf-actions", default="data/contextual-gf-actions.json"
    )
    parser.add_argument(
        "--gf-nouns", default="data/contextual-gf-nouns.json"
    )
    parser.add_argument("--framenet-snapshot", type=Path)
    parser.add_argument(
        "--ablation",
        choices=[
            "full",
            "no-wordnet",
            "no-framenet",
            "no-existential",
            "no-formal-filtering",
        ],
        default="full",
    )
    args = parser.parse_args()
    command = [
        "python3",
        "scripts/propose_contextual_scenario.py",
        "--snapshot",
        str(args.snapshot),
        "--sentence",
        args.sentence,
        "--rules",
        args.rules,
    ]
    if args.source:
        command.extend(["--source", args.source])
    if args.linker_cache:
        command.extend(["--linker-cache", str(args.linker_cache)])
    if args.contract_target:
        command.extend(["--target-surface", args.contract_target])
    if args.dependency_hint:
        command.extend(["--dependency-hint", args.dependency_hint])
    if args.ablation == "no-framenet":
        command.append("--disable-framenet")
    elif args.framenet_snapshot:
        command.extend(
            ["--framenet-snapshot", str(args.framenet_snapshot)]
        )
    proposed = subprocess.run(command, text=True, capture_output=True)
    if proposed.returncode != 0:
        # Deliberately not check=True: an uncaught CalledProcessError's
        # default traceback prints only "Command '...' returned non-zero
        # exit status N" and silently discards the captured stdout/stderr
        # -- which is exactly where propose_contextual_scenario.py's own
        # short, sentence-free error message (raise SystemExit(str(error))
        # for target-occurrence-not-found/unsupported-action-role/
        # nested-modifier-unsupported) actually landed, undiagnosable from
        # any caller that only sees this process's own combined output.
        print(
            json.dumps(
                {
                    "status": "propose-scenario-failed",
                    "sentence": args.sentence,
                    "detail": (proposed.stdout + proposed.stderr).strip(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(1)
    proposal = json.loads(proposed.stdout)
    candidates = proposal.get("source_qid_candidates") or []
    if not candidates:
        print(
            json.dumps(
                {**proposal, "status": "source-qid-unresolved"},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(2)
    if args.contract_target and len(candidates) != 1:
        # --contract-target keeps the old, stricter single-candidate
        # requirement -- see the module docstring for why the multi-
        # candidate tower loop below is scoped to the expand direction
        # only.
        print(
            json.dumps(
                {**proposal, "status": "source-qid-unresolved"},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        raise SystemExit(2)
    parsed = subprocess.run(
        [str(args.engine), "parse", proposal["gf_sentence"]],
        text=True,
        capture_output=True,
    )
    if parsed.returncode != 0:
        print(
            json.dumps(
                {
                    "status": "gf-parse-failed",
                    "gf_sentence": proposal["gf_sentence"],
                    "detail": parsed.stderr.strip(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(3)
    trees = [line for line in parsed.stdout.splitlines() if line.strip()]
    if not trees or trees[0].startswith("The parser failed"):
        raise SystemExit("GF returned no lexicalized trees")
    language_rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    wordnet_rules_path = Path("data/wordnet-context-rules.json")
    wordnet_rules = json.loads(wordnet_rules_path.read_text(encoding="utf-8"))
    if args.ablation == "no-wordnet":
        wordnet_rules = {"lexical_sorts": {}, "adjective_sorts": {}}
    aliases = {}
    with (args.snapshot / "aliases.jsonl").open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            aliases.setdefault(row["alias"].casefold(), []).append(row["id"])
    action_map = json.loads(
        Path(args.gf_actions).read_text(encoding="utf-8")
    )
    gf_actions = {
        action["gf_function"]: action["lemma"]
        for action in action_map["actions"]
    }
    noun_map = json.loads(
        Path(args.gf_nouns).read_text(encoding="utf-8")
    )
    gf_nouns = {
        noun["gf_function"]: noun["lemma"]
        for noun in noun_map["nouns"]
    }
    try:
        proposal["constraints"].extend(
            compile_gf_constraints(
                proposal,
                trees[0],
                language_rules,
                wordnet_rules,
                aliases,
                enable_existential=args.ablation != "no-existential",
                gf_actions=gf_actions,
                gf_nouns=gf_nouns,
            )
        )
    except ValueError as error:
        print(
            json.dumps(
                {
                    "status": "semantic-composition-failed",
                    "gf_tree": trees[0],
                    "detail": str(error),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(4)
    print("gf-tree=" + trees[0], flush=True)
    encoded_constraints = ";;".join(
        encode_constraint(item) for item in proposal["constraints"]
    )
    bridge_relations = ",".join(proposal["bridge_relations"])

    def run_engine(
        operation: list[str], source_qid: str, scenario_name: str, *, capture: bool
    ) -> subprocess.CompletedProcess:
        row = "\t".join(
            [
                scenario_name,
                source_qid,
                proposal["action"],
                proposal["role"],
                str(proposal["max_depth"]),
                bridge_relations,
                encoded_constraints,
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            scenarios = Path(directory) / "scenarios.tsv"
            scenarios.write_text(HEADER + row + "\n", encoding="utf-8")
            return subprocess.run(
                [
                    str(args.engine),
                    *operation,
                    "--snapshot",
                    str(args.snapshot),
                    "--scenarios",
                    str(scenarios),
                    *(
                        ["--no-formal-filtering"]
                        if args.ablation == "no-formal-filtering"
                        else []
                    ),
                ],
                text=True,
                capture_output=capture,
            )

    if args.contract_target:
        # Single, already-uniquely-resolved source QID (enforced above, by
        # the len(candidates) != 1 guard) -- unchanged from before the
        # multi-candidate expand-direction loop below was introduced.
        # Inherits stdout/stderr directly since there is nothing to choose
        # between, and a contraction can be *correctly* rejected by the
        # formal checker (see module docstring), which this must not
        # confuse with a disambiguation failure.
        target_candidates = []
        with (args.snapshot / "aliases.jsonl").open(encoding="utf-8") as source:
            for line in source:
                alias = json.loads(line)
                if alias["alias"].casefold() == args.contract_target.casefold():
                    target_candidates.append(alias["id"])
        target_candidates = sorted(set(target_candidates))
        if len(target_candidates) != 1:
            print(
                json.dumps(
                    {
                        "status": "contract-target-qid-unresolved",
                        "surface": args.contract_target,
                        "qid_candidates": target_candidates,
                    },
                    indent=2,
                )
            )
            raise SystemExit(5)
        source_qid = candidates[0]
        scenario_name = f"{source_qid.lower()}-{proposal['action']}"
        completed = run_engine(
            ["contextual-contract", scenario_name, target_candidates[0]],
            source_qid,
            scenario_name,
            capture=False,
        )
        raise SystemExit(completed.returncode)

    # Expand direction: run the tower's existing per-layer narrowing once
    # per ambiguous source candidate -- see the module docstring for why
    # this is a faithful (not an approximate) way to let the sentence's own
    # context disambiguate which candidate was actually meant.
    def run_candidate(source_qid: str) -> subprocess.CompletedProcess:
        scenario_name = f"{source_qid.lower()}-{proposal['action']}"
        return run_engine(
            ["contextual-fiber", scenario_name], source_qid, scenario_name, capture=True
        )

    results = [(source_qid, run_candidate(source_qid)) for source_qid in candidates]
    confirmed = [
        (qid, completed)
        for qid, completed in results
        if completed.returncode == 0 and final_fiber(completed.stdout)
    ]

    def emit(completed: subprocess.CompletedProcess) -> None:
        sys.stdout.write(completed.stdout)
        sys.stderr.write(completed.stderr)

    if len(confirmed) == 1:
        _, completed = confirmed[0]
        emit(completed)
        raise SystemExit(completed.returncode)

    if not confirmed:
        # No candidate identity bridges to anything satisfying the
        # sentence's own constraints -- a legitimate "nothing metonymic
        # here" result (empty fiber, still exit 0, still scored as
        # literal), not a disambiguation failure. Any one candidate's own
        # trace is representative for scoring purposes since they are all
        # empty; prefer one whose own run actually completed (exit 0) over
        # one that hit a genuine engine-level rejection, so a real internal
        # error still surfaces instead of being masked by picking blindly.
        clean = [(qid, completed) for qid, completed in results if completed.returncode == 0]
        _, completed = clean[0] if clean else results[0]
        emit(completed)
        raise SystemExit(completed.returncode)

    # Two or more candidates survived full contextual narrowing: genuine,
    # irreducible ambiguity even given the sentence's own context. Never
    # silently pick one -- the same exact-match-or-abstain policy the
    # entity linker itself already follows (build_wikidata_api_index.py's
    # search_exact docstring: "an ambiguous surface simply resolves to more
    # than one QID here, and callers decide what to do with that").
    print(
        json.dumps(
            {
                "status": "source-disambiguation-ambiguous",
                "action": proposal["action"],
                "confirmed_source_qid_candidates": sorted(
                    qid for qid, _ in confirmed
                ),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    raise SystemExit(6)


if __name__ == "__main__":
    main()
