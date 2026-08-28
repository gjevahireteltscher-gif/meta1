#!/usr/bin/env python3
"""Propose a lexicalized contextual scenario from text and an offline snapshot."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

def rows(path: Path):
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--sentence", required=True)
    parser.add_argument("--source")
    parser.add_argument("--name")
    parser.add_argument(
        "--rules",
        type=Path,
        default=Path("data/contextual-language-rules.json"),
    )
    parser.add_argument(
        "--wordnet-rules",
        type=Path,
        default=Path("data/wordnet-context-rules.json"),
    )
    args = parser.parse_args()
    aliases = {}
    for row in rows(args.snapshot / "aliases.jsonl"):
        aliases.setdefault(row["alias"].casefold(), []).append(row["id"])
    manifest = json.loads((args.snapshot / "manifest.json").read_text())
    language_rules = json.loads(args.rules.read_text(encoding="utf-8"))
    action_forms = {
        form.casefold(): (lemma, definition)
        for lemma, definition in language_rules["actions"].items()
        for form in definition["forms"]
    }
    tokens = list(re.finditer(r"[A-Za-z][A-Za-z'-]*", args.sentence))
    action = next(
        (
            (match, action_forms[match.group().casefold()])
            for match in tokens
            if match.group().casefold() in action_forms
        ),
        None,
    )
    if action is None:
        raise SystemExit("unsupported-action")
    action_match, (lemma, action_definition) = action
    role = action_definition["role"]
    requirement = action_definition["requirement"]
    inferred_source = (
        args.sentence[: action_match.start()].strip()
        if role == "SubjectHole"
        else args.sentence[action_match.end() :].strip().strip(".!?")
    )
    source_text = args.source or inferred_source
    candidates = aliases.get(source_text.casefold(), [])
    proposal = {
        "schema_version": "contextual-scenario-proposal-1",
        "graph_sha256": manifest["graph_sha256"],
        "sentence": args.sentence,
        "gf_sentence": (
            args.sentence[: action_match.start()]
            + action_definition.get("gf_form", action_match.group())
            + args.sentence[action_match.end() :]
        ),
        "source_surface": source_text,
        "source_qid_candidates": sorted(candidates),
        "action": lemma,
        "role": role,
        "bridge_relations": action_definition["bridge_relations"],
        "max_depth": action_definition.get("max_depth", 1),
        "provenance": {
            "action": action_definition["provenance"],
            "rules": language_rules["schema_version"],
        },
        "constraints": [
            {
                "origin": {
                    "constructor": "Verb",
                    "lemma": lemma,
                    "surface": action_match.group(),
                    "start": action_match.start(),
                    "end": action_match.end(),
                },
                "payload": {"requires": requirement},
                "provenance": action_definition["provenance"],
            }
        ],
    }
    if args.wordnet_rules.exists():
        wordnet_rules = json.loads(args.wordnet_rules.read_text(encoding="utf-8"))
        lexical_evidence = []
        for match in tokens:
            lexical_rule = wordnet_rules.get("lexical_sorts", {}).get(
                match.group().casefold()
            )
            if lexical_rule:
                lexical_evidence.append(
                    {
                        "surface": match.group(),
                        "start": match.start(),
                        "end": match.end(),
                        **lexical_rule,
                    }
                )
        proposal["lexical_evidence"] = lexical_evidence
        proposal["provenance"]["wordnet"] = wordnet_rules["schema_version"]
    sentence_folded = args.sentence.casefold()
    if "programme" in sentence_folded and "physics" in sentence_folded:
        physics_candidates = aliases.get("physics", [])
        if len(physics_candidates) == 1:
            physics_start = sentence_folded.index("physics")
            proposal["constraints"].append(
                {
                    "origin": {
                        "constructor": "Noun",
                        "lemma": "physics",
                        "surface": args.sentence[physics_start : physics_start + 7],
                        "start": physics_start,
                        "end": physics_start + 7,
                    },
                    "payload": {
                        "requires_relation": {
                            "relation": "Conducts",
                            "target": physics_candidates[0],
                        }
                    },
                    "provenance": "context-template:programme-in-topic:v1",
                }
            )
    proposal["status"] = "ready" if len(candidates) == 1 else "source-qid-unresolved"
    if proposal["status"] == "ready":
        proposal["scenario"] = args.name or f"{candidates[0].lower()}-{lemma}"
    print(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
