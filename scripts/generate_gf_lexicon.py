#!/usr/bin/env python3
"""Generate GF abstract and English lexicon modules from the data snapshot."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path


def gf_suffix(identifier: str) -> str:
    return "".join(character if character.isalnum() else "_" for character in identifier)


def gf_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def possessive(label: str) -> str:
    return f"{label}'" if label.endswith("s") else f"{label}'s"


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def generate(
    rows: list[dict[str, str]],
    semantic_entities: list[dict[str, str]],
    predicates: list[dict[str, str]],
    action_roles: list[dict[str, str]],
) -> tuple[str, str]:
    authors: dict[str, str] = {}
    works: dict[str, str] = {}
    for row in rows:
        authors[row["author_id"]] = row["author_label"]
        works[row["work_id"]] = row["work_label"]

    declarations: list[str] = []
    linearizations: list[str] = []

    for identifier, label in sorted(authors.items()):
        suffix = gf_suffix(identifier)
        declarations.extend(
            [
                f"    Author_{suffix} : NP ;",
                f"    Works_{suffix} : NP ;",
            ]
        )
        linearizations.extend(
            [
                f'    Author_{suffix} = mkNP (mkPN "{gf_string(label)}") ;',
                (
                    f'    Works_{suffix} = mkNP (mkPN "'
                    f'{gf_string(possessive(label) + " works")}") ;'
                ),
            ]
        )

    for identifier, label in sorted(works.items()):
        suffix = gf_suffix(identifier)
        declarations.append(f"    Work_{suffix} : NP ;")
        linearizations.append(
            f'    Work_{suffix} = mkNP (mkPN "{gf_string(label)}") ;'
        )

    for row in sorted(semantic_entities, key=lambda item: item["gf_function"]):
        function = row["gf_function"]
        declarations.append(f"    {function} : NP ;")
        linearizations.append(
            f'    {function} = mkNP (mkPN "{gf_string(row["label"])}") ;'
        )

    base_predicates = {"Read", "Drink", "Sign"}
    represented_lemmas = {"announce", "read", "drink", "sign"}
    for row in predicates:
        function = row["gf_function"]
        represented_lemmas.add(row["lemma"].casefold().replace("_", " "))
        if function in base_predicates:
            continue
        declarations.append(f"    {function} : V2 ;")
        linearizations.append(
            f'    {function} = {row["gf_expression"]} ;'
        )

    contextual_lemmas = sorted(
        {
            row["lemma"].casefold().replace("_", " ")
            for row in action_roles
            if row["mapping_status"] == "compiled"
            and row["hole_role"] in {"SubjectHole", "ObjectHole"}
            and row["requirement"] not in {"", "null"}
        }
        - represented_lemmas
    )
    for lemma in contextual_lemmas:
        digest = hashlib.sha256(lemma.encode()).hexdigest()[:16]
        function = f"CTX_{digest}"
        declarations.append(f"    {function} : V2 ;")
        linearizations.append(
            f'    {function} = mkV2 "{gf_string(lemma)}" ;'
        )

    abstract = "\n".join(
        [
            "abstract GeneratedMetonymy = Metonymy ** {",
            "  fun",
            *declarations,
            "}",
            "",
        ]
    )
    concrete = "\n".join(
        [
            "concrete GeneratedMetonymyEng of GeneratedMetonymy =",
            "  MetonymyEng ** open SyntaxEng, ParadigmsEng in {",
            "  lin",
            *linearizations,
            "}",
            "",
        ]
    )
    return abstract, concrete


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/wikidata-author-works.tsv"),
    )
    parser.add_argument(
        "--semantic-entities",
        type=Path,
        default=Path("data/semantic-entities.tsv"),
    )
    parser.add_argument(
        "--predicates",
        type=Path,
        default=Path("data/predicates.tsv"),
    )
    parser.add_argument(
        "--verbnet-predicates",
        type=Path,
        default=Path("data/verbnet-predicates.tsv"),
    )
    parser.add_argument(
        "--verbnet-action-roles",
        type=Path,
        default=Path("data/verbnet-action-roles.tsv"),
    )
    parser.add_argument(
        "--abstract-output",
        type=Path,
        default=Path("grammar/GeneratedMetonymy.gf"),
    )
    parser.add_argument(
        "--concrete-output",
        type=Path,
        default=Path("grammar/GeneratedMetonymyEng.gf"),
    )
    arguments = parser.parse_args()

    abstract, concrete = generate(
        read_rows(arguments.input),
        read_rows(arguments.semantic_entities),
        read_rows(arguments.predicates)
        + read_rows(arguments.verbnet_predicates),
        read_rows(arguments.verbnet_action_roles),
    )
    arguments.abstract_output.write_text(abstract, encoding="utf-8")
    arguments.concrete_output.write_text(concrete, encoding="utf-8")
    print(
        f"generated {arguments.abstract_output} and {arguments.concrete_output}"
    )


if __name__ == "__main__":
    main()
