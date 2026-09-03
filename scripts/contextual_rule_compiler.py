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
    "AboutPP": 1,
    "WithPP": 1,
    "ForPP": 1,
    "ModifyNP": 2,
    "ModifyRel": 3,
    "IndefCN": 1,
    "DefCN": 1,
    "ModifyRelCN": 3,
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


def load_action_frames(actions_path: Path) -> dict[str, list[dict[str, str]]]:
    frames: dict[str, list[dict[str, str]]] = {}
    for row in read_tsv(actions_path):
        lemma = row["lemma"].casefold().replace("_", " ")
        for frame in json.loads(row["framenet_frames_json"]):
            if not frame or frame == "None":
                continue
            entry = {
                "frame": frame,
                "action_id": row["action_id"],
                "provenance": row["provenance"],
            }
            if entry not in frames.setdefault(lemma, []):
                frames[lemma].append(entry)
    return frames


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
    dependency_hint: dict | None = None,
) -> dict:
    by_form: dict[str, list[ActionRole]] = {}
    for role in roles:
        for form in action_forms(role.lemma):
            by_form.setdefault(form, []).append(role)
    for lemma, definition in morphology_overrides.items():
        matching = [role for role in roles if role.lemma == lemma.casefold()]
        for form in definition.get("forms", []):
            by_form.setdefault(form.casefold(), []).extend(matching)

    dep_status = dependency_hint.get("dep_status") if dependency_hint else None
    if dep_status == "nested-modifier":
        raise ValueError("nested-modifier-unsupported")

    governing_start = dependency_hint.get("governing_start") if dependency_hint else None
    governing_end = dependency_hint.get("governing_end") if dependency_hint else None
    if (
        dep_status == "direct-argument"
        and governing_start is not None
        and governing_end is not None
        and dependency_hint.get("hole_role")
    ):
        # annotate_dependency_hints.py reports "Subject"/"Object";
        # ActionRole.hole_role uses "SubjectHole"/"ObjectHole".
        hint_hole_role = dependency_hint["hole_role"] + "Hole"
        governing_lemma = (dependency_hint.get("governing_lemma") or "").casefold()
        candidates = [
            (0, governing_start, governing_end, sentence[governing_start:governing_end].casefold(), role)
            for role in by_form.get(governing_lemma, [])
            if role.hole_role == hint_hole_role
        ]
    else:
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
    strength = "hard" if hard else "selectional-preference"
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


def _cumulative_origin(
    proposal: dict,
    token: str,
    constructor: str,
    semantic_lemma: str,
) -> dict:
    sentence = proposal["sentence"]
    action_origin = proposal["constraints"][0]["origin"]
    match = re.search(
        rf"\b{re.escape(token)}\b",
        sentence[action_origin["end"] :],
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"GF lexical token is absent from source: {token}")
    end = action_origin["end"] + match.end()
    return {
        "constructor": constructor,
        "lemma": semantic_lemma,
        "surface": sentence[action_origin["start"] : end],
        "start": action_origin["start"],
        "end": end,
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
    *,
    enable_existential: bool = True,
    gf_actions: dict[str, str] | None = None,
    gf_nouns: dict[str, str] | None = None,
) -> list[dict]:
    root = parse_gf_tree(tree)
    constraints = []
    if not wordnet_rules.get("lexical_sorts"):
        return constraints
    action_payload = proposal["constraints"][0]["payload"]
    action_requirement = action_payload.get(
        "requires", action_payload.get("prefers")
    )
    action_is_preference = "prefers" in action_payload
    gf_actions = gf_actions or {}
    gf_nouns = gf_nouns or {}

    def first_node(node: GFNode | str, constructor: str) -> GFNode | None:
        if not isinstance(node, GFNode):
            return None
        if node.constructor == constructor:
            return node
        for argument in node.arguments:
            found = first_node(argument, constructor)
            if found:
                return found
        return None

    def lexical_head(node: GFNode | str) -> GFNode | str:
        if isinstance(node, GFNode) and node.constructor in {
            "ModifyNP",
            "ModifyRel",
            "ModifyRelCN",
            "IndefCN",
            "DefCN",
        }:
            return lexical_head(node.arguments[0])
        return node

    complement = first_node(root, "Compl")
    if complement and len(complement.arguments) == 2:
        object_node = complement.arguments[1]
        head = lexical_head(object_node)
        head_lemma = _noun_lemma(head)
        if (
            not head_lemma
            and isinstance(head, GFNode)
            and head.constructor in gf_nouns
        ):
            head_lemma = gf_nouns[head.constructor]
        head_rule = (
            wordnet_rules.get("lexical_sorts", {}).get(head_lemma.casefold())
            if head_lemma
            else None
        )
        if not head_rule:
            action_end = proposal["constraints"][0]["origin"]["end"]
            fallback_evidence = sorted(
                (
                    evidence
                    for evidence in proposal.get("lexical_evidence", [])
                    if evidence["start"] >= action_end
                ),
                key=lambda evidence: evidence["start"],
            )
            if fallback_evidence:
                evidence = fallback_evidence[0]
                head_lemma = evidence["surface"].casefold()
                head_rule = {
                    "requirement": evidence["requirement"],
                    "provenance": evidence["provenance"],
                }
        if head_lemma and head_rule:
            head_sorts = _sorts(head_rule["requirement"])
            frame_names = sorted(
                {frame["frame"] for frame in proposal.get("frames", [])}
            )
            capability = next(
                (
                    rule
                    for rule in language_rules.get(
                        "frame_argument_capabilities", []
                    )
                    if head_sorts.intersection(rule["argument_sorts"])
                    and (
                        not rule.get("frames")
                        or set(frame_names).intersection(rule["frames"])
                    )
                ),
                None,
            ) if enable_existential else None
            semantic_lemma = " ".join([proposal["action"], head_lemma])
            provenance_parts = [
                head_rule["provenance"],
                proposal["provenance"]["action"],
            ]
            if frame_names:
                provenance_parts.append("FrameNet:" + ",".join(frame_names))
            for projection in proposal.get("frame_role_projections", []):
                provenance_parts.append(projection["provenance"])
            for pattern in proposal.get("framenet_valence_patterns", []):
                provenance_parts.append(pattern["provenance"])
            if capability:
                payload = {
                    "requires_some": {
                        "relation": capability["relation"],
                        "requirement": capability["related_requirement"],
                    }
                }
                provenance_parts.append(capability["provenance"])
            else:
                payload = {
                    (
                        "prefers"
                        if action_is_preference
                        else "requires"
                    ): action_requirement
                }
                provenance_parts.append("frame-argument-compatibility:v1")
            constraints.append(
                {
                    "origin": _cumulative_origin(
                        proposal,
                        head_lemma,
                        "FrameArgument",
                        semantic_lemma,
                    ),
                    "payload": payload,
                    "provenance": "+".join(provenance_parts),
                }
            )

        relative_node = object_node
        if (
            isinstance(relative_node, GFNode)
            and relative_node.constructor in {"IndefCN", "DefCN"}
        ):
            relative_node = relative_node.arguments[0]
        if (
            proposal.get("role") == "ObjectHole"
            and isinstance(relative_node, GFNode)
            and relative_node.constructor in {"ModifyRel", "ModifyRelCN"}
        ):
            _, relative_verb, relative_object = relative_node.arguments
            relative_lemma = (
                gf_actions.get(relative_verb.constructor)
                if isinstance(relative_verb, GFNode)
                else None
            )
            relation_name = language_rules.get(
                "relation_lexicalizations", {}
            ).get(relative_lemma or "")
            object_lemma = _proper_lemma(relative_object)
            target_qids = (
                sorted(set(aliases.get(object_lemma.casefold(), [])))
                if object_lemma
                else []
            )
            if relative_lemma and relation_name and len(target_qids) == 1:
                constraints.append(
                    {
                        "origin": _cumulative_origin(
                            proposal,
                            object_lemma,
                            "FrameRelativeClause",
                            " ".join(
                                [
                                    proposal["action"],
                                    head_lemma or "target",
                                    "that",
                                    relative_lemma,
                                    object_lemma,
                                ]
                            ),
                        ),
                        "payload": {
                            "requires_relation": {
                                "relation": relation_name,
                                "target": target_qids[0],
                            }
                        },
                        "provenance": (
                            f"FrameNet:Relative_clause+"
                            f"relation-lexicalization:{relative_lemma}"
                        ),
                    }
                )

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
                    "origin": _cumulative_origin(
                        proposal,
                        noun,
                        "FrameComposition",
                        " ".join(
                            [proposal["action"], adjective, noun]
                        ),
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
            walk(head)
            pp_constructions = {
                "InPP": ("ModifyNP+InPP", "in"),
                "AboutPP": ("ModifyNP+AboutPP", "about"),
                "WithPP": ("ModifyNP+WithPP", "with"),
                "ForPP": ("ModifyNP+ForPP", "for"),
            }
            if (
                isinstance(modifier, GFNode)
                and modifier.constructor in pp_constructions
                and modifier.arguments
            ):
                resolved_head = lexical_head(head)
                head_lemma = _noun_lemma(resolved_head)
                if (
                    not head_lemma
                    and isinstance(resolved_head, GFNode)
                    and resolved_head.constructor in gf_nouns
                ):
                    head_lemma = gf_nouns[resolved_head.constructor]
                target_lemma = _proper_lemma(modifier.arguments[0])
                head_rule = (
                    wordnet_rules.get("lexical_sorts", {}).get(head_lemma.casefold())
                    if head_lemma
                    else None
                )
                if head_rule and target_lemma:
                    head_sorts = _sorts(head_rule["requirement"])
                    construction, preposition = pp_constructions[
                        modifier.constructor
                    ]
                    accepted_constructions = {construction}
                    if construction == "ModifyNP+InPP":
                        accepted_constructions.add("ModIn")
                    template = next(
                        (
                            rule
                            for rule in language_rules.get("context_templates", [])
                            if rule["construction"] in accepted_constructions
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
                                "origin": _cumulative_origin(
                                    proposal,
                                    target_lemma,
                                    "FrameModifier",
                                    " ".join(
                                        [
                                            proposal["action"],
                                            head_lemma,
                                            preposition,
                                            target_lemma,
                                        ]
                                    ),
                                ),
                                "payload": {
                                    (
                                        "prefers_relation"
                                        if template.get("strength")
                                        == "SelectionalPreference"
                                        else "requires_relation"
                                    ): {
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
            return
        for argument in node.arguments:
            walk(argument)

    walk(root)
    return constraints
