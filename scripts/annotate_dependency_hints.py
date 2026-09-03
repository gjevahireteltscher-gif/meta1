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
     "governing_lemma": "<verb lemma>" | "<verb lemma> <preposition>" | "",
     "governing_start": <int or null>, "governing_end": <int or null>}

``hole_role``, ``governing_lemma``, ``governing_start`` and
``governing_end`` are non-empty/non-null only when
``dep_status == "direct-argument"``. ``governing_start``/``governing_end``
are the governing word's own absolute character span in the input text
(covering the case-marking preposition too for a reconstructed phrasal
verb) -- needed by consumers that substitute a canonical verb form back
into the sentence (e.g. scripts/contextual_rule_compiler.py's
``resolve_action``, which builds a GF-parseable sentence this way); the
open-domain frontend consuming ``hole_role``/``governing_lemma`` alone
does not need them.

This module works on two input shapes: rows with an explicit
``target_span``/``target_spans`` (the open-domain corpus format, offsets
computed by scripts/evaluation/prepare_wimcor.py etc.) are validated
strictly against that exact span; rows with only a plain mention string
(e.g. the contextual-tower corpus format's ``source``/``target`` field,
no span) fall back to the first case-insensitive word-boundary match,
mirroring scripts/contextual_rule_compiler.py's own ``_mention_span``.

Sentences are parsed in batches (see ``annotate``/``--batch-size``), not one
``pipeline(text)`` call per row: Stanza's own documentation warns that
calling the pipeline once per short text is very slow on CPU, since each
call pays fixed per-call overhead instead of letting the neural processors
batch across many sentences at once. Pass a list of ``stanza.Document``
objects to the pipeline in one call to get that batching.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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
DEFAULT_BATCH_SIZE = 500

Hint = dict[str, "str | int | None"]
ValidatedRow = tuple[str, int, int]


ClassifyResult = tuple[str, str, str, "int | None", "int | None"]


def classify_word(sentence: Any, word: Any) -> ClassifyResult:
    """Classify one target word given its UD parent sentence.

    ``sentence`` must expose ``.words`` (a list of word-like objects with
    ``.id``, ``.head``, ``.deprel``, ``.upos``, ``.lemma``, ``.text``, and a
    ``.parent`` exposing ``.start_char``/``.end_char``); ``word`` is the
    target word itself. Duck-typed so tests can pass plain stand-in objects
    instead of real Stanza objects.

    Returns ``(dep_status, hole_role, governing_lemma, governing_start,
    governing_end)``; the last two are the governing word's own absolute
    character span (covering the case-marking preposition too for a
    reconstructed phrasal verb), or ``None`` when there is no governing
    verb to report.
    """
    by_id = {candidate.id: candidate for candidate in sentence.words}
    head = by_id.get(word.head) if word.head else None

    if word.deprel in SUBJECT_DEPRELS:
        if head is not None and head.upos in GOVERNING_UPOS:
            return (
                "direct-argument",
                "Subject",
                head.lemma,
                head.parent.start_char,
                head.parent.end_char,
            )
        return ("no-governing-verb", "", "", None, None)

    if word.deprel in OBJECT_DEPRELS:
        if head is not None and head.upos in GOVERNING_UPOS:
            return (
                "direct-argument",
                "Object",
                head.lemma,
                head.parent.start_char,
                head.parent.end_char,
            )
        return ("no-governing-verb", "", "", None, None)

    if word.deprel in OBLIQUE_DEPRELS:
        if head is not None and head.upos in GOVERNING_UPOS:
            case_children = [
                candidate
                for candidate in sentence.words
                if candidate.head == word.id and candidate.deprel == "case"
            ]
            if case_children:
                case_word = case_children[0]
                lemma = f"{head.lemma} {case_word.text.lower()}"
                start = min(head.parent.start_char, case_word.parent.start_char)
                end = max(head.parent.end_char, case_word.parent.end_char)
                return ("direct-argument", "Object", lemma, start, end)
        return ("no-governing-verb", "", "", None, None)

    if word.deprel in NESTED_MODIFIER_DEPRELS:
        return ("nested-modifier", "", "", None, None)

    return ("no-governing-verb", "", "", None, None)


def find_governing_structure(
    document: Any, start: int, end: int
) -> ClassifyResult:
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
    return ("parse-error", "", "", None, None)


def validate_row(
    row: dict, text_field: str = "text", target_field: str = "target"
) -> ValidatedRow | None:
    """Return ``(text, start, end)`` if the row's span is trustworthy.

    With an explicit ``target_span``/``target_spans``: mirrors
    OpenDomain.hs's ``validSpan`` check exactly -- never trust parser
    output against an offset that does not actually cover the target
    string in this exact text. Pure and parser-independent, so invalid
    rows are filtered out before anything is sent to Stanza.

    Without one (the contextual-tower corpus format, which only supplies a
    mention string): falls back to the first case-insensitive
    word-boundary match, mirroring
    scripts/contextual_rule_compiler.py's ``_mention_span``. The match
    itself is the source of truth here, so it is not re-checked against
    case-sensitive equality the way an explicit span is.
    """
    text = row.get(text_field)
    target = row.get(target_field)
    if not text or not target:
        return None
    span = row.get("target_span", row.get("target_spans", [None])[0])
    if span is not None:
        start, end = span
        if text[start:end] != target:
            return None
        return text, start, end
    match = re.search(rf"\b{re.escape(target)}\b", text, re.IGNORECASE)
    if match is None:
        return None
    return text, match.start(), match.end()


def annotate(
    pipeline_batch: Callable[[list[str]], list[Any]],
    rows: Iterable[dict],
    batch_size: int = DEFAULT_BATCH_SIZE,
    on_progress: Callable[[int, int], None] | None = None,
    text_field: str = "text",
    target_field: str = "target",
) -> Iterator[Hint]:
    """Annotate every row, parsing distinct sentence texts in batches.

    Several rows (different targets/categories) can share the same source
    sentence, and processing many short texts one at a time is very slow
    on CPU (see the module docstring), so this collects every distinct
    valid text once, parses them ``batch_size`` at a time via
    ``pipeline_batch``, and only then walks the rows to classify each
    target against its (already parsed) sentence.
    """
    rows = list(rows)
    validated: dict[str, ValidatedRow | None] = {
        row["id"]: validate_row(row, text_field, target_field) for row in rows
    }

    unique_texts: list[str] = []
    seen_texts: set[str] = set()
    for result in validated.values():
        if result is not None and result[0] not in seen_texts:
            seen_texts.add(result[0])
            unique_texts.append(result[0])

    documents: dict[str, Any] = {}
    total_batches = (len(unique_texts) + batch_size - 1) // batch_size or 1
    for batch_index, start_index in enumerate(
        range(0, len(unique_texts), batch_size), start=1
    ):
        chunk = unique_texts[start_index : start_index + batch_size]
        try:
            parsed = pipeline_batch(chunk)
        except Exception:  # noqa: BLE001 - a batch failure degrades to parse-error
            parsed = [None] * len(chunk)
        for text, document in zip(chunk, parsed):
            documents[text] = document
        if on_progress is not None:
            on_progress(batch_index, total_batches)

    for row in rows:
        result = validated[row["id"]]
        if result is None:
            yield {
                "id": row["id"],
                "dep_status": "parse-error",
                "hole_role": "",
                "governing_lemma": "",
                "governing_start": None,
                "governing_end": None,
            }
            continue
        text, start, end = result
        document = documents.get(text)
        if document is None:
            status, hole_role, lemma, g_start, g_end = ("parse-error", "", "", None, None)
        else:
            try:
                status, hole_role, lemma, g_start, g_end = find_governing_structure(
                    document, start, end
                )
            except Exception:  # noqa: BLE001 - malformed parse -> parse-error
                status, hole_role, lemma, g_start, g_end = ("parse-error", "", "", None, None)
        yield {
            "id": row["id"],
            "dep_status": status,
            "hole_role": hole_role,
            "governing_lemma": lemma,
            "governing_start": g_start,
            "governing_end": g_end,
        }


def build_pipeline() -> Callable[[list[str]], list[Any]]:
    """Build the pinned UD English-EWT pipeline as a batch-callable: pass a
    list of texts, get back a list of parsed ``stanza.Document`` objects in
    the same order (see scripts/bootstrap_dependency_frontend.sh and
    toolchain.lock.json's "stanza" entry for the exact pinned versions and
    model provenance).
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

    def run_batch(texts: list[str]) -> list[Any]:
        return nlp([stanza.Document([], text=text) for text in texts])

    return run_batch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="how many distinct sentences to parse per pipeline call "
        f"(default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--text-field",
        default="text",
        help="dataset field holding the full sentence text (default: text; "
        "the contextual-tower corpus format uses 'sentence')",
    )
    parser.add_argument(
        "--target-field",
        default="target",
        help="dataset field holding the marked mention (default: target; "
        "the contextual-tower corpus format uses 'source')",
    )
    parser.add_argument(
        "--no-source-filter",
        action="store_true",
        help="do not filter rows by source in "
        f"{sorted(OPEN_DOMAIN_SOURCES)!r} -- use for datasets without a "
        "matching 'source' field, e.g. the contextual-tower corpus format",
    )
    arguments = parser.parse_args()

    all_rows = read_jsonl(arguments.dataset)
    rows = (
        all_rows
        if arguments.no_source_filter
        else [row for row in all_rows if row.get("source") in OPEN_DOMAIN_SOURCES]
    )
    pipeline = build_pipeline()

    def report_progress(batch_index: int, total_batches: int) -> None:
        print(
            f"annotate_dependency_hints: parsed batch {batch_index}/{total_batches}",
            file=sys.stderr,
            flush=True,
        )

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8") as handle:
        for hint in annotate(
            pipeline,
            rows,
            batch_size=arguments.batch_size,
            on_progress=report_progress,
            text_field=arguments.text_field,
            target_field=arguments.target_field,
        ):
            handle.write(json.dumps(hint, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
