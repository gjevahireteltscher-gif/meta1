#!/usr/bin/env python3
"""Compile versioned lexical resources into contextual tower constraints."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ActionRole:
    lemma: str
    hole_role: str
    requirement: str
    strength: str
    provenance: str
    identity: str


@dataclass(frozen=True)
class GFNode:
    constructor: str
    arguments: tuple["GFNode | str", ...] = ()


ARITIES = {
    "Pred": 2,
    "NegPred": 2,
    "Compl": 2,
    "InPP": 1,
    "ModifyNP": 2,
    "EveryCN": 2,
    "OpenAdjDefCN": 3,
    "OpenAdjIndefCN": 3,
    "OpenPN": 1,
    "OpenIndefCN": 2,
    "OpenDefCN": 2,
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def action_forms(raw_lemma: str) -> set[str]:
    lemma = raw_lemma.casefold().replace("_", " ")
    if " " in lemma:
        return {lemma}
    forms = {lemma}
    if lemma.endswith(("s", "sh", "ch", "x", "z", "o")):
        forms.add(lemma + "es")
    elif lemma.endswith("y") and len(lemma) > 1 and lemma[-2] not in "aeiou":
        forms.add(lemma[:-1] + "ies")
    else:
        forms.add(lemma + "s")
    forms.add(lemma[:-1] + "ed" if lemma.endswith("e") else lemma + "ed")
    forms.add(lemma[:-1] + "ing" if lemma.endswith("e") else lemma + "ing")
    return forms


def third_person(lemma: str) -> str:
    candidates = action_forms(lemma)
    if lemma.endswith(("s", "sh", "ch", "x", "z", "o")):
        wanted = lemma + "es"
    elif lemma.endswith("y") and len(lemma) > 1 and lemma[-2] not in "aeiou":
        wanted = lemma[:-1] + "ies"
    else:
        wanted = lemma + "s"
    return wanted if wanted in candidates else lemma


def load_action_roles(
    predicates_path: Path, verbnet_roles_path: Path
) -> list[ActionRole]:
    roles = []
    for row in read_tsv(predicates_path):
        for hole, column in (
            ("SubjectHole", "subject_sort"),
            ("ObjectHole", "object_sort"),
        ):
            roles.append(
                ActionRole(
                    lemma=row["lemma"].casefold(),
                    hole_role=hole,
                    requirement=f"HasSort {row[column]}",
                    strength=row["strength"],
                    provenance=row["provenance"],
                    identity=f"predicate:{row['predicate_id']}:{hole}",
                )
            )
    for row in read_tsv(verbnet_roles_path):
        if (
            row["mapping_status"] != "compiled"
            or row["hole_role"] not in {"SubjectHole", "ObjectHole"}
            or not row["requirement"]
            or row["requirement"] == "null"
        ):
            continue
        roles.append(
            ActionRole(
                lemma=row["lemma"].casefold().replace("_", " "),
                hole_role=row["hole_role"],
                requirement=row["requirement"],
                strength=row["strength"],
                provenance=row["provenance"],
                identity=f"{row['action_id']}:{row['frame_id']}:{row['thematic_role']}",
            )
        )
    return roles


def _surface_phrases(sentence: str) -> list[tuple[str, int, int]]:
    tokens = list(re.finditer(r"[A-Za-z][A-Za-z'-]*", sentence))
    phrases = []
    for size in (1, 2, 3):
        for index in range(len(tokens) - size + 1):
            selected = tokens[index : index + size]
            phrases.append(
                (
                    sentence[selected[0].start() : selected[-1].end()].casefold(),
                    selected[0].start(),
                    selected[-1].end(),
                )
            )
    return phrases


def _mention_span(sentence: str, surfaces: list[str]) -> tuple[int, int] | None:
    for surface in surfaces:
        match = re.search(rf"\b{re.escape(surface)}\b", sentence, re.IGNORECASE)
        if match:
            return match.start(), match.end()
    return None


def _split_top_level(value: str) -> list[str]:
    fields, start, depth = [], 0, 0
    for index, character in enumerate(value):
        if character in "[(":
            depth += 1
        elif character in "])":
            depth -= 1
        elif character == "," and depth == 0:
            fields.append(value[start:index])
            start = index + 1
    fields.append(value[start:])
    return [field.strip() for field in fields if field.strip()]


def _disjunction_members(requirement: str) -> list[str]:
    prefix = "AnyOf ["
    if requirement.startswith(prefix) and requirement.endswith("]"):
        return _split_top_level(requirement[len(prefix) : -1])
    return [requirement]


def resolve_action(
    sentence: str,
    target_surfaces: list[str],
    roles: list[ActionRole],
    morphology_overrides: dict,
) -> dict:
    by_form: dict[str, list[ActionRole]] = {}
    for role in roles:
        for form in action_forms(role.lemma):
            by_form.setdefault(form, []).append(role)
    for lemma, definition in morphology_overrides.items():
        matching = [role for role in roles if role.lemma == lemma.casefold()]
        for form in definition.get("forms", []):
            by_form.setdefault(form.casefold(), []).extend(matching)

    target_span = _mention_span(sentence, target_surfaces)
    if target_span is None:
        raise ValueError("target-occurrence-not-found")

    candidates = []
    for surface, start, end in _surface_phrases(sentence):
        for role in by_form.get(surface, []):
            expected_role = "SubjectHole" if target_span[0] < start else "ObjectHole"
            if role.hole_role == expected_role:
                candidates.append((abs(start - target_span[0]), start, end, surface, role))
    if not candidates:
        raise ValueError("unsupported-action-role")

    candidates.sort(
        key=lambda item: (
            item[0],
            0 if item[4].strength == "HardRequirement" else 1,
            -len(item[4].lemma),
            item[4].identity,
        )
    )
    _, start, end, surface, selected = candidates[0]
    same_action = [
        item[4]
        for item in candidates
        if item[1] == start
        and item[4].lemma == selected.lemma
        and item[4].hole_role == selected.hole_role
    ]
    hard = [role for role in same_action if role.strength == "HardRequirement"]
    chosen = hard or same_action
    requirements = sorted(
        {
            member
            for role in chosen
            for member in _disjunction_members(role.requirement)
        }
    )
    requirement = (
        requirements[0]
        if len(requirements) == 1
        else "AnyOf [" + ",".join(requirements) + "]"
    )
    evidence = sorted(
        {
            (role.identity, role.provenance, role.strength, role.requirement)
            for role in chosen
        }
    )
    digest = hashlib.sha256(
        json.dumps(evidence, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    strength = "hard" if hard else "selectional-preference-as-context-filter"
    override = morphology_overrides.get(selected.lemma, {})
    return {
        "lemma": selected.lemma,
        "surface": sentence[start:end],
        "start": start,
        "end": end,
        "role": selected.hole_role,
        "requirement": requirement,
        "strength": strength,
        "provenance": f"compiled-action-role:v1:{strength}:{digest}",
        "evidence": [
            {
                "identity": identity,
                "provenance": provenance,
                "strength": source_strength,
                "requirement": source_requirement,
            }
            for identity, provenance, source_strength, source_requirement in evidence
        ],
        "gf_form": override.get("gf_form", third_person(selected.lemma)),
    }


def tokenize_gf(tree: str) -> list[str]:
    return re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', tree)


def parse_gf_tree(tree: str) -> GFNode:
    tokens = tokenize_gf(tree)

    def parse(index: int) -> tuple[GFNode | str, int]:
        parenthesized = tokens[index] == "("
        if parenthesized:
            index += 1
        token = tokens[index]
        index += 1
        if token.startswith('"') or token.startswith("?"):
            value: GFNode | str = token[1:-1] if token.startswith('"') else token
        else:
            arguments = []
            for _ in range(ARITIES.get(token, 0)):
                argument, index = parse(index)
                arguments.append(argument)
            value = GFNode(token, tuple(arguments))
        if parenthesized:
            if index >= len(tokens) or tokens[index] != ")":
                raise ValueError(f"malformed GF tree near {token}")
            index += 1
        return value, index

    parsed, index = parse(0)
    if not isinstance(parsed, GFNode) or index != len(tokens):
        raise ValueError("malformed or incomplete GF tree")
    return parsed


def _origin(sentence: str, token: str, constructor: str) -> dict:
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


def _noun_lemma(node: GFNode | str) -> str | None:
    if not isinstance(node, GFNode):
        return None
    if node.constructor in {"OpenIndefCN", "OpenDefCN"}:
        return node.arguments[0] if isinstance(node.arguments[0], str) else None
    if node.constructor in {"OpenAdjDefCN", "OpenAdjIndefCN"}:
        return node.arguments[1] if isinstance(node.arguments[1], str) else None
    return None


def _proper_lemma(node: GFNode | str) -> str | None:
    if (
        isinstance(node, GFNode)
        and node.constructor == "OpenPN"
        and node.arguments
        and isinstance(node.arguments[0], str)
    ):
        return node.arguments[0]
    return None


def _sorts(requirement: str) -> set[str]:
    return set(re.findall(r"HasSort ([A-Za-z][A-Za-z0-9]*)", requirement))


def compile_gf_constraints(
    proposal: dict,
    tree: str,
    language_rules: dict,
    wordnet_rules: dict,
    aliases: dict[str, list[str]],
) -> list[dict]:
    root = parse_gf_tree(tree)
    constraints = []

    def walk(node: GFNode | str) -> None:
        if not isinstance(node, GFNode):
            return
        if node.constructor in {"OpenAdjDefCN", "OpenAdjIndefCN"}:
            adjective, noun = node.arguments[:2]
            if not isinstance(adjective, str) or not isinstance(noun, str):
                raise ValueError("malformed adjective-noun GF node")
            noun_rule = wordnet_rules.get("lexical_sorts", {}).get(noun.casefold())
            adjective_rule = wordnet_rules.get("adjective_sorts", {}).get(
                adjective.casefold()
            )
            if not noun_rule or not adjective_rule:
                raise ValueError(
                    f"unsupported GF adjective-noun semantics: {adjective} {noun}"
                )
            noun_sorts = _sorts(noun_rule["requirement"])
            if len(noun_sorts) != 1:
                raise ValueError(f"ambiguous noun sort for GF composition: {noun}")
            noun_sort = next(iter(noun_sorts))
            action_rules = language_rules.get("action_object_requirements", {}).get(
                proposal["action"], {}
            )
            base_action_rule = action_rules.get(noun_sort)
            if base_action_rule:
                constraints.append(
                    {
                        "origin": _origin(proposal["sentence"], noun, "OpenCN"),
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
            composition = next(
                (
                    rule
                    for rule in language_rules.get("composition_matrix", [])
                    if rule["modifier_sort"] == adjective_rule["sort"]
                    and rule["noun_sort"] == noun_sort
                ),
                None,
            )
            if composition is None:
                raise ValueError(
                    f"no semantic composition for "
                    f"{adjective_rule['sort']}×{noun_sort}"
                )
            composed_rule = action_rules.get(composition["result_sort"])
            if composed_rule is None:
                raise ValueError(
                    f"action {proposal['action']} has no role rule for "
                    f"{composition['result_sort']}"
                )
            constraints.append(
                {
                    "origin": _origin(
                        proposal["sentence"], adjective, "OpenAdj"
                    ),
                    "payload": {
                        "requires": composed_rule["candidate_requirement"]
                    },
                    "provenance": (
                        adjective_rule["provenance"]
                        + "+"
                        + composition["provenance"]
                        + "+"
                        + composed_rule["provenance"]
                    ),
                }
            )

        if node.constructor == "ModifyNP" and len(node.arguments) == 2:
            head, modifier = node.arguments
            if (
                isinstance(modifier, GFNode)
                and modifier.constructor == "InPP"
                and modifier.arguments
            ):
                head_lemma = _noun_lemma(head)
                target_lemma = _proper_lemma(modifier.arguments[0])
                head_rule = (
                    wordnet_rules.get("lexical_sorts", {}).get(head_lemma.casefold())
                    if head_lemma
                    else None
                )
                if head_rule and target_lemma:
                    head_sorts = _sorts(head_rule["requirement"])
                    template = next(
                        (
                            rule
                            for rule in language_rules.get("context_templates", [])
                            if rule["construction"] in {"ModIn", "ModifyNP+InPP"}
                            and head_sorts.intersection(rule["head_sorts"])
                        ),
                        None,
                    )
                    if template:
                        qids = sorted(set(aliases.get(target_lemma.casefold(), [])))
                        if len(qids) != 1:
                            raise ValueError(
                                f"context modifier QID is not unique: {target_lemma}"
                            )
                        constraints.append(
                            {
                                "origin": _origin(
                                    proposal["sentence"], target_lemma, "OpenPN"
                                ),
                                "payload": {
                                    "requires_relation": {
                                        "relation": template["relation"],
                                        "target": qids[0],
                                    }
                                },
                                "provenance": (
                                    head_rule["provenance"]
                                    + "+"
                                    + template["provenance"]
                                ),
                            }
                        )
        for argument in node.arguments:
            walk(argument)

    walk(root)
    return constraints
