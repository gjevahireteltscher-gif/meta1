#!/usr/bin/env python3
"""Propose a lexicalized contextual scenario from text and an offline snapshot."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from contextual_rule_compiler import (
    load_action_frames,
    load_action_roles,
    resolve_action,
)


def rows(path: Path):
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--sentence", required=True)
    parser.add_argument("--source")
    parser.add_argument("--target-surface")
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
    parser.add_argument(
        "--predicates",
        type=Path,
        default=Path("data/predicates.tsv"),
    )
    parser.add_argument(
        "--verbnet-action-roles",
        type=Path,
        default=Path("data/verbnet-action-roles.tsv"),
    )
    parser.add_argument(
        "--verbnet-actions",
        type=Path,
        default=Path("data/verbnet-actions.tsv"),
    )
    parser.add_argument(
        "--framenet-capabilities",
        type=Path,
        default=Path("data/framenet-role-capabilities.json"),
    )
    parser.add_argument("--disable-framenet", action="store_true")
    args = parser.parse_args()
    aliases = {}
    for row in rows(args.snapshot / "aliases.jsonl"):
        aliases.setdefault(row["alias"].casefold(), []).append(row["id"])
    manifest = json.loads((args.snapshot / "manifest.json").read_text())
    snapshot_rules = json.loads(
        (args.snapshot / "rules.json").read_text(encoding="utf-8")
    )
    language_rules = json.loads(args.rules.read_text(encoding="utf-8"))
    tokens = list(re.finditer(r"[A-Za-z][A-Za-z'-]*", args.sentence))
    source_text = args.source or args.target_surface
    if not source_text:
        source_text = tokens[0].group() if tokens else ""
    action_roles = load_action_roles(
        args.predicates, args.verbnet_action_roles
    )
    try:
        action = resolve_action(
            args.sentence,
            [value for value in (args.target_surface, source_text) if value],
            action_roles,
            language_rules.get(
                "morphology_overrides",
                language_rules.get("actions", {}),
            ),
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    lemma = action["lemma"]
    role = action["role"]
    requirement = action["requirement"]
    candidates = aliases.get(source_text.casefold(), [])
    action_frames = (
        []
        if args.disable_framenet
        else load_action_frames(args.verbnet_actions).get(lemma, [])
    )
    frame_names = {frame["frame"] for frame in action_frames}
    frame_capabilities = (
        json.loads(args.framenet_capabilities.read_text(encoding="utf-8"))
        if not args.disable_framenet and args.framenet_capabilities.exists()
        else {"projections": []}
    )
    matching_frame_projections = [
        projection
        for projection in frame_capabilities.get("projections", [])
        if projection["frame"] in frame_names
        and projection["hole_role"] == role
    ]
    snapshot_relations = list(
        dict.fromkeys(rule["internal"] for rule in snapshot_rules["relations"])
    )
    requirement_sorts = set(
        re.findall(r"HasSort ([A-Za-z][A-Za-z0-9]*)", requirement)
    )
    configured_relations = [
        relation
        for sort_name in sorted(requirement_sorts)
        for relation in language_rules.get("bridge_relations_by_sort", {}).get(
            sort_name, []
        )
    ]
    bridge_relations = [
        relation
        for relation in dict.fromkeys(configured_relations)
        if relation in snapshot_relations
    ] or snapshot_relations
    proposal = {
        "schema_version": "contextual-scenario-proposal-1",
        "graph_sha256": manifest["graph_sha256"],
        "sentence": args.sentence,
        "gf_sentence": (
            args.sentence[: action["start"]]
            + action["gf_form"]
            + args.sentence[action["end"] :]
        ),
        "source_surface": source_text,
        "source_qid_candidates": sorted(candidates),
        "action": lemma,
        "frames": action_frames,
        "frame_role_projections": matching_frame_projections,
        "role": role,
        "bridge_relations": bridge_relations,
        "max_depth": language_rules.get("max_bridge_depth", 1),
        "provenance": {
            "action": action["provenance"],
            "action_strength_policy": action["strength"],
            "action_evidence": action["evidence"],
            "rules": language_rules["schema_version"],
        },
        "constraints": [
            {
                "origin": {
                    "constructor": "Verb",
                    "lemma": lemma,
                    "surface": action["surface"],
                    "start": action["start"],
                    "end": action["end"],
                },
                "payload": {
                    (
                        "requires"
                        if action["strength"] == "hard"
                        else "prefers"
                    ): requirement
                },
                "provenance": action["provenance"],
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
    proposal["status"] = "ready" if len(candidates) == 1 else "source-qid-unresolved"
    if proposal["status"] == "ready":
        proposal["scenario"] = args.name or f"{candidates[0].lower()}-{lemma}"
    print(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
