#!/usr/bin/env python3
"""Run text → proposal → data scenario → checked contextual tower."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from contextual_rule_compiler import compile_gf_constraints

HEADER = "scenario\tsource_qid\taction\trole\tmax_depth\tbridge_relations\tconstraints\n"


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
    if args.ablation == "no-framenet":
        command.append("--disable-framenet")
    elif args.framenet_snapshot:
        command.extend(
            ["--framenet-snapshot", str(args.framenet_snapshot)]
        )
    proposal = json.loads(subprocess.run(command, check=True, text=True, capture_output=True).stdout)
    if proposal["status"] != "ready":
        print(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True))
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
    row = "\t".join(
        [
            proposal["scenario"],
            proposal["source_qid_candidates"][0],
            proposal["action"],
            proposal["role"],
            str(proposal["max_depth"]),
            ",".join(proposal["bridge_relations"]),
            ";;".join(encode_constraint(item) for item in proposal["constraints"]),
        ]
    )
    with tempfile.TemporaryDirectory() as directory:
        scenarios = Path(directory) / "scenarios.tsv"
        scenarios.write_text(HEADER + row + "\n", encoding="utf-8")
        operation = ["contextual-fiber", proposal["scenario"]]
        if args.contract_target:
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
            operation = [
                "contextual-contract",
                proposal["scenario"],
                target_candidates[0],
            ]
        completed = subprocess.run(
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
        )
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
