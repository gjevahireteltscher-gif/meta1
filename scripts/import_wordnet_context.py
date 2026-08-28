#!/usr/bin/env python3
"""Project a local Princeton WordNet noun database into lexical sort rules."""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path

ROOT_PROJECTIONS = {
    "clothing": "Clothing",
    "wearable": "Wearable",
    "book": "Readable",
    "publication": "Readable",
    "discipline": "ScientificDiscipline",
    "science": "ScientificDiscipline",
    "program": "Programme",
    "programme": "Programme",
    "organization": "Organization",
    "institution": "Institution",
    "agreement": "Agreement",
}
ADJECTIVE_PROJECTIONS = {
    "political": "Political",
    "commercial": "Commercial",
    "educational": "Programme",
    "scientific": "ScientificDiscipline",
}


def parse_data(path: Path):
    synsets, parents = {}, {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line or line[0].isspace():
                continue
            body = line.split("|", 1)[0].split()
            offset, pos = body[0], body[2]
            if pos != "n":
                continue
            word_count = int(body[3], 16)
            cursor = 4
            words = [body[cursor + index * 2].replace("_", " ") for index in range(word_count)]
            cursor += word_count * 2
            pointer_count = int(body[cursor])
            cursor += 1
            hypernyms = []
            for _ in range(pointer_count):
                symbol, target, target_pos, _ = body[cursor : cursor + 4]
                cursor += 4
                if symbol in {"@", "@i"} and target_pos == "n":
                    hypernyms.append(target)
            synsets[offset] = words
            parents[offset] = hypernyms
    return synsets, parents


def parse_adjectives(path: Path):
    words = {}
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line or line[0].isspace():
                continue
            body = line.split("|", 1)[0].split()
            offset = body[0]
            word_count = int(body[3], 16)
            values = [
                body[4 + index * 2].replace("_", " ").casefold()
                for index in range(word_count)
            ]
            words[offset] = values
    return words


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wordnet-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    synsets, parents = parse_data(args.wordnet_dir / "data.noun")
    adjective_synsets = parse_adjectives(args.wordnet_dir / "data.adj")

    @lru_cache(maxsize=None)
    def inherited_words(offset: str) -> frozenset[str]:
        return frozenset(word.casefold() for word in synsets.get(offset, [])) | frozenset(
            word for parent in parents.get(offset, []) for word in inherited_words(parent)
        )

    rules = {}
    for offset, words in synsets.items():
        ancestry = inherited_words(offset)
        sorts = sorted({sort for root, sort in ROOT_PROJECTIONS.items() if root in ancestry})
        if not sorts:
            continue
        requirement = (
            f"HasSort {sorts[0]}"
            if len(sorts) == 1
            else "AnyOf [" + ",".join(f"HasSort {sort_name}" for sort_name in sorts) + "]"
        )
        for word in words:
            rules.setdefault(
                word.casefold(),
                {
                    "requirement": requirement,
                    "provenance": f"PrincetonWordNet:data.noun:{offset}",
                },
            )
    adjective_rules = {}
    for offset, words in adjective_synsets.items():
        for word in words:
            normalized_word = word.split("(", 1)[0]
            if normalized_word in ADJECTIVE_PROJECTIONS:
                adjective_rules[normalized_word] = {
                    "sort": ADJECTIVE_PROJECTIONS[normalized_word],
                    "provenance": f"PrincetonWordNet:data.adj:{offset}",
                }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "schema_version": "wordnet-context-projection-2",
                "lexical_sorts": rules,
                "adjective_sorts": adjective_rules,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
