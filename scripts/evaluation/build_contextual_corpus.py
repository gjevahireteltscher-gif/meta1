#!/usr/bin/env python3
"""Build a deterministic silver corpus from independently frozen graph facts."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


def rows(path: Path):
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    entities = {row["id"]: row.get("labels") or [row["id"]] for row in rows(args.snapshot / "entities.jsonl")}
    aliases = defaultdict(list)
    for row in rows(args.snapshot / "aliases.jsonl"):
        aliases[row["id"]].append(row["alias"])
    claims = rows(args.snapshot / "claims.jsonl")
    evidence = rows(args.snapshot / "evidence.jsonl") if (args.snapshot / "evidence.jsonl").exists() else []
    rules = json.loads((args.snapshot / "rules.json").read_text(encoding="utf-8"))
    manifest = json.loads((args.snapshot / "manifest.json").read_text(encoding="utf-8"))
    projected_types = defaultdict(set)
    type_map = {row["qid"]: row["sort"] for row in rules["types"]}
    for claim in claims:
        if claim["property"] == "P31" and claim["target"] in type_map:
            projected_types[claim["source"]].add(type_map[claim["target"]])
    supersorts = {
        "University": {"Organization", "Agent"},
        "ResearchInstitution": {"Organization", "Agent"},
        "Government": {"PoliticalOrganization", "Organization", "Agent"},
        "PoliticalOrganization": {"Organization", "Agent"},
        "BusinessOrganization": {"Organization", "Agent"},
        "Organization": {"Agent"},
        "LiteraryWork": {"Readable"},
        "Clothing": {"Wearable"},
    }
    for entity, sorts in projected_types.items():
        changed = True
        while changed:
            before = len(sorts)
            sorts |= {supersort for sort in list(sorts) for supersort in supersorts.get(sort, set())}
            changed = len(sorts) != before
    relations = defaultdict(set)
    projections = defaultdict(list)
    for rule in rules["relations"]:
        projections[rule["property"]].append(rule)
    for claim in claims:
        for projection in projections.get(claim["property"], []):
            source, target = claim["source"], claim["target"]
            if projection["direction"] == "inverse":
                source, target = target, source
            relations[(projection["internal"], source)].add(target)
    for row in evidence:
        relations[(row["relation"], row["source"])].add(row["target"])

    def surface(qid: str) -> str | None:
        names = set(aliases[qid] + entities.get(qid, []))
        proper = [
            value
            for value in names
            if re.fullmatch(r"[A-Z][a-z]{3,11}", value)
        ]

        def mention_hits(value: str) -> int:
            needle = value.casefold()
            return sum(
                1
                for other in names
                if other.casefold() != needle
                and (
                    other.casefold().startswith(needle)
                    or other.casefold().endswith(needle)
                    or f" {needle}" in other.casefold()
                    or f"{needle} " in other.casefold()
                )
            )

        if proper:
            return sorted(
                proper,
                key=lambda value: (-mention_hits(value), abs(len(value) - 6), value),
            )[0]
        fallback = [
            value
            for value in names
            if re.fullmatch(r"[A-Za-z][A-Za-z-]{2,32}", value)
        ]
        if not fallback:
            return None
        return sorted(fallback, key=lambda value: (len(value), value))[0]

    def add_contraction(
        stem: str,
        family: str,
        source_qid: str,
        source_name: str,
        targets: list[str],
        sentence_for,
    ) -> None:
        if not targets:
            return
        target_name = surface(targets[0])
        if not target_name:
            return
        unique = len(targets) == 1
        prefix = "contract" if unique else "reject-contract"
        identifier = f"{prefix}-{stem}"
        corpus.append(
            {
                "id": identifier,
                "sentence": sentence_for(target_name),
                "source": source_name,
                "contract_target": target_name,
                "family": family,
                "direction": "contract",
                **({} if unique else {"expected_status": "rejected"}),
            }
        )
        gold.append(
            {
                "id": identifier,
                "gold_qids": [source_qid] if unique else [],
                "gold_families": [family],
            }
        )

    corpus = []
    gold = []
    authors = sorted({claim["target"] for claim in claims if claim["property"] == "P50"})
    for author in authors:
        name = surface(author)
        targets = sorted(
            target
            for target in relations[("Authored", author)]
            if "Readable" in projected_types[target]
        )
        if name and targets:
            identifier = f"read-{author.lower()}"
            corpus.append({"id": identifier, "sentence": f"Anna reads {name}", "source": name, "family": "author-for-work", "direction": "expand"})
            gold.append({"id": identifier, "gold_qids": targets, "gold_families": ["author-for-work"]})
            add_contraction(
                identifier,
                "author-for-work",
                author,
                name,
                targets,
                lambda target_name: f"Anna reads {target_name}",
            )

    places = sorted(source for relation, source in relations if relation == "InstitutionOf")
    variants = [
        ("generic", "the agreement", "Agent"),
        ("commercial", "the commercial agreement", "BusinessOrganization"),
        ("political", "the political agreement", "PoliticalOrganization"),
    ]
    for place in places:
        name = surface(place)
        if not name:
            continue
        direct = relations[("InstitutionOf", place)]
        for variant, object_phrase, wanted_sort in variants:
            targets = sorted(
                target for target in direct if wanted_sort in projected_types[target]
            )
            identifier = f"sign-{variant}-{place.lower()}"
            corpus.append(
                {
                    "id": identifier,
                    "sentence": f"{name} signed {object_phrase}",
                    "source": name,
                    "family": "location-for-institution",
                    "direction": "expand",
                }
            )
            gold.append(
                {
                    "id": identifier,
                    "gold_qids": targets,
                    "gold_families": ["location-for-institution"],
                }
            )
            add_contraction(
                identifier,
                "location-for-institution",
                place,
                name,
                targets,
                lambda target_name, phrase=object_phrase: f"{target_name} signed {phrase}",
            )

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    (output / "silver-inputs.jsonl").write_text(
        "".join(canonical(row) + "\n" for row in corpus), encoding="utf-8"
    )
    (output / "silver-gold.jsonl").write_text(
        "".join(canonical(row) + "\n" for row in gold), encoding="utf-8"
    )
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "contextual-silver-corpus-1",
                "graph_sha256": manifest["graph_sha256"],
                "instances": len(corpus),
                "families": dict(
                    (family, sum(row["family"] == family for row in corpus))
                    for family in sorted({row["family"] for row in corpus})
                ),
                "directions": dict(
                    (direction, sum(row.get("direction", "expand") == direction for row in corpus))
                    for direction in ("expand", "contract")
                ),
                "gold_policy": "derived from frozen graph/type projections; not independent linguistic annotation",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(corpus)} instances")


if __name__ == "__main__":
    main()
