#!/usr/bin/env python3
"""Offline UD dependency-parser preprocessing for the open-domain frontend.

Reads a corpus ``*.inputs.jsonl`` file (the same format consumed by
``scripts/evaluation/run_engine_predictions.py``) and emits one JSON object
per row describing, for the marked target occurrence, whether it is the
direct subject/object of a governing verb, a modifier nested inside a noun
phrase, or unresolved. This is a pure, untrusted proposal: the Haskell
engine's ``analyzeOpenAtWithDependencyHint`` (engine/src/Metonymy/OpenDomain.hs)
treats it exactly like every other candidate source, and the compiled Agda
``runtimeCheck`` independently re-derives admissibility regardless of how the
candidate was found. See docs/architecture.md for the trust boundary.

Output schema, one object per input row keyed by ``id``:

    {"id": ..., "dep_status": "direct-argument" | "nested-modifier"
                              | "no-governing-verb" | "parse-error",
     "hole_role": "Subject" | "Object" | "",
     "governing_lemma": "<verb lemma>" | "<verb lemma> <preposition>" | ""}

``hole_role`` and ``governing_lemma`` are non-empty only when
``dep_status == "direct-argument"``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
    return rows

# Target occupies a clause-argument position directly.
SUBJECT_DEPRELS = {"nsubj", "nsubj:pass", "csubj"}
OBJECT_DEPRELS = {"obj", "iobj"}
OBLIQUE_DEPRELS = {"obl"}
GOVERNING_UPOS = {"VERB", "AUX"}

# Target is a modifier inside a noun phrase, not itself a clause argument
# (e.g. "Tolstoy" in "Tolstoy's books"). Deliberately left unresolved in
# this phase: promoting it correctly requires widening the checked
# construction vocabulary in engine/src/Metonymy/Elaborator.hs
# (PositiveGFTree), which is out of scope here. See the plan's "Дальше"
# section.
NESTED_MODIFIER_DEPRELS = {
    "nmod",
    "nmod:poss",
    "amod",
    "appos",
    "compound",
    "acl",
    "acl:relcl",
    "nummod",
}

OPEN_DOMAIN_SOURCES = {"wimcor-v1.1", "conmec"}

Hint = dict[str, str]


def classify_word(sentence: Any, word: Any) -> tuple[str, str, str]:
    """Classify one target word given its UD parent sentence.

    ``sentence`` must expose ``.words`` (a list of word-like objects with
    ``.id``, ``.head``, ``.deprel``, ``.upos``, ``.lemma``, ``.text``);
    ``word`` is the target word itself. Duck-typed so tests can pass plain
    stand-in objects instead of real Stanza objects.
    """
    by_id = {candidate.id: candidate for candidate in sentence.words}
    head = by_id.get(word.head) if word.head else None

    if word.deprel in SUBJECT_DEPRELS:
        if head is not None and head.upos in GOVERNING_UPOS:
            return ("direct-argument", "Subject", head.lemma)
        return ("no-governing-verb", "", "")

    if word.deprel in OBJECT_DEPRELS:
        if head is not None and head.upos in GOVERNING_UPOS:
            return ("direct-argument", "Object", head.lemma)
        return ("no-governing-verb", "", "")

    if word.deprel in OBLIQUE_DEPRELS:
        if head is not None and head.upos in GOVERNING_UPOS:
            case_children = [
                candidate
                for candidate in sentence.words
                if candidate.head == word.id and candidate.deprel == "case"
            ]
            if case_children:
                lemma = f"{head.lemma} {case_children[0].text.lower()}"
                return ("direct-argument", "Object", lemma)
        return ("no-governing-verb", "", "")

    if word.deprel in NESTED_MODIFIER_DEPRELS:
        return ("nested-modifier", "", "")

    return ("no-governing-verb", "", "")


def find_governing_structure(
    document: Any, start: int, end: int
) -> tuple[str, str, str]:
    """Locate the target span in a parsed document and classify it.

    Character offsets on Stanza ``Word``/``Token`` objects are absolute
    over the whole input text, so sentences can be scanned in order
    without renumbering; ``.head`` indices, by contrast, are only valid
    within their own sentence, which is why classification happens once
    the owning sentence is found.
    """
    for sentence in document.sentences:
        words_in_span = [
            word
            for word in sentence.words
            if word.parent.start_char is not None
            and word.parent.end_char is not None
            and word.parent.start_char < end
            and word.parent.end_char > start
        ]
        if not words_in_span:
            continue
        span_ids = {word.id for word in words_in_span}
        roots = [
            word
            for word in words_in_span
            if word.head == 0 or word.head not in span_ids
        ]
        target_word = roots[-1] if roots else words_in_span[-1]
        return classify_word(sentence, target_word)
    return ("parse-error", "", "")


def annotate_row(pipeline: Callable[[str], Any], row: dict) -> Hint:
    text = row.get("text")
    target = row.get("target")
    span = row.get("target_span", row.get("target_spans", [None])[0])
    if not text or not target or span is None:
        return {
            "id": row["id"],
            "dep_status": "parse-error",
            "hole_role": "",
            "governing_lemma": "",
        }
    start, end = span
    # Mirrors OpenDomain.hs's validSpan check: never trust parser output
    # against an offset that does not actually cover the target string in
    # this exact text.
    if text[start:end] != target:
        return {
            "id": row["id"],
            "dep_status": "parse-error",
            "hole_role": "",
            "governing_lemma": "",
        }
    try:
        document = pipeline(text)
        status, hole_role, lemma = find_governing_structure(document, start, end)
    except Exception:  # noqa: BLE001 - any parser failure degrades to legacy
        status, hole_role, lemma = ("parse-error", "", "")
    return {
        "id": row["id"],
        "dep_status": status,
        "hole_role": hole_role,
        "governing_lemma": lemma,
    }


def annotate(pipeline: Callable[[str], Any], rows: Iterable[dict]) -> Iterator[Hint]:
    # One parse per distinct sentence text, not per row: several instances
    # (different targets/categories) can share the same source sentence.
    cache: dict[str, Any] = {}

    def cached_pipeline(text: str) -> Any:
        if text not in cache:
            cache[text] = pipeline(text)
        return cache[text]

    for row in rows:
        yield annotate_row(cached_pipeline, row)


def build_pipeline() -> Callable[[str], Any]:
    """Build the pinned UD English-EWT pipeline (see
    scripts/bootstrap_dependency_frontend.sh and toolchain.lock.json's
    "stanza" entry for the exact pinned versions and model provenance).
    """
    import os

    import stanza

    model_dir = os.environ.get("STANZA_MODEL_DIR")
    kwargs: dict[str, Any] = {}
    if model_dir:
        kwargs["model_dir"] = model_dir
    nlp = stanza.Pipeline(
        lang="en",
        package="ewt",
        processors="tokenize,mwt,pos,lemma,depparse",
        verbose=False,
        **kwargs,
    )
    return nlp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    rows = [
        row
        for row in read_jsonl(arguments.dataset)
        if row.get("source") in OPEN_DOMAIN_SOURCES
    ]
    pipeline = build_pipeline()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8") as handle:
        for hint in annotate(pipeline, rows):
            handle.write(json.dumps(hint, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
