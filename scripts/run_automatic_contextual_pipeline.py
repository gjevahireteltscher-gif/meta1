#!/usr/bin/env python3
"""Run text → proposal → data scenario → checked contextual tower."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import re
from pathlib import Path

HEADER = "scenario\tsource_qid\taction\trole\tmax_depth\tbridge_relations\tconstraints\n"


def token_origin(sentence: str, token: str, constructor: str) -> dict:
    match = re.search(rf"\b{re.escape(token)}\b", sentence, re.IGNORECASE)
    if not match:
        raise ValueError(f"GF lexical token is absent from source: {token}")
    return {
        "constructor": constructor,
        "lemma": token.casefold(),
        "surface": match.group(),
        "start": match.start(),
        "end": match.end(),
    }


def compile_gf_constraints(
    proposal: dict,
    tree: str,
    language_rules: dict,
    wordnet_rules: dict,
) -> list[dict]:
    constraints = []
    adjective_nodes = re.findall(
        r'OpenAdj(?:Def|Indef)CN "([^"]+)" "([^"]+)"', tree
    )
    for adjective, noun in adjective_nodes:
        noun_rule = wordnet_rules.get("lexical_sorts", {}).get(noun.casefold())
        adjective_rule = wordnet_rules.get("adjective_sorts", {}).get(
            adjective.casefold()
        )
        if not noun_rule or not adjective_rule:
            raise ValueError(
                f"unsupported GF adjective-noun semantics: {adjective} {noun}"
            )
        noun_requirement = noun_rule["requirement"]
        noun_sort = (
            noun_requirement.removeprefix("HasSort ")
            if noun_requirement.startswith("HasSort ")
            else None
        )
        if noun_sort is None:
            raise ValueError(f"ambiguous noun sort for GF composition: {noun}")
        action_rules = language_rules.get("action_object_requirements", {}).get(
            proposal["action"], {}
        )
        base_action_rule = action_rules.get(noun_sort)
        if base_action_rule:
            constraints.append(
                {
                    "origin": token_origin(proposal["sentence"], noun, "OpenCN"),
                    "payload": {
                        "requires": base_action_rule["candidate_requirement"]
                    },
                    "provenance": (
                        noun_rule["provenance"]
                        + "+"
                        + base_action_rule["provenance"]
                    ),
                }
            )
        result = next(
            (
                rule
                for rule in language_rules.get("composition_matrix", [])
                if rule["modifier_sort"] == adjective_rule["sort"]
                and rule["noun_sort"] == noun_sort
            ),
            None,
        )
        if result is None:
            raise ValueError(
                f"no semantic composition for {adjective_rule['sort']}×{noun_sort}"
            )
        composed_action_rule = action_rules.get(result["result_sort"])
        if composed_action_rule is None:
            raise ValueError(
                f"action {proposal['action']} has no role rule for {result['result_sort']}"
            )
        constraints.append(
            {
                "origin": token_origin(
                    proposal["sentence"], adjective, "OpenAdj"
                ),
                "payload": {
                    "requires": composed_action_rule["candidate_requirement"]
                },
                "provenance": (
                    adjective_rule["provenance"]
                    + "+"
                    + result["provenance"]
                    + "+"
                    + composed_action_rule["provenance"]
                ),
            }
        )
    return constraints


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
    parser.add_argument("--contract-target")
    parser.add_argument("--rules", default="data/contextual-language-rules.json")
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
    try:
        proposal["constraints"].extend(
            compile_gf_constraints(
                proposal, trees[0], language_rules, wordnet_rules
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
            ],
            text=True,
        )
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
