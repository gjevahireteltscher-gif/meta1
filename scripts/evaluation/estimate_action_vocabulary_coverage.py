#!/usr/bin/env python3
"""Research-only tool: estimate how much of a corpus's governing-verb
vocabulary is covered by the compiled action-role predicate vocabulary
(data/predicates.tsv + mapping_status=compiled rows in
data/verbnet-action-roles.tsv).

Not part of make test/reproduce.sh and never run in CI -- this exists to
measure the real-world effect of editing scripts/import_verbnet.py's sort-
mapping tables (AUDITED_ROLE_SORTS, THEMATIC_ROLE_DEFAULTS, etc.) entirely
locally, before spending a CI round-trip on it. It approximates governing-
verb extraction with NLTK's POS tagger + WordNet lemmatizer (nltk.pos_tag +
WordNetLemmatizer) rather than the real UD dependency parse
(annotate_dependency_hints.py's Stanza pipeline): this is a coarser signal
(no real dependency relation, so e.g. "was captured" tags "be" as a verb
token alongside the real predicate "capture", and non-governing verbs like
auxiliaries/modals count too) but needs no GPU/PyTorch and installs
cleanly where Stanza does not. Treat the percentage as directional, not
exact -- cross-check anything that changes the recommended plan against
the real pipeline (annotate_dependency_hints.py + resolve_action) before
relying on it.

Requires nltk (not a project dependency otherwise -- pip install nltk,
then nltk.download('punkt_tab'), nltk.download('averaged_perceptron_tagger_eng'),
nltk.download('wordnet'), nltk.download('omw-1.4')).

Usage: point --sentences at a tower-shaped {id, sentence, source, ...}
JSONL (e.g. the output of adapt_metonymy_corpus_for_tower.py) and
--roles at a candidate data/verbnet-action-roles.tsv (the committed one,
or a scratch regeneration from a locally-edited import_verbnet.py) to see
what fraction of real verb tokens the compiled vocabulary would resolve.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def jsonl(path: Path):
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def compiled_lemma_vocabulary(predicates_path: Path, roles_path: Path) -> set[str]:
    lemmas: set[str] = set()
    with predicates_path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            lemmas.add(row["lemma"].casefold())
    with roles_path.open(encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            if row["mapping_status"] == "compiled":
                lemmas.add(row["lemma"].casefold().replace("_", " "))
    return lemmas


def governing_verb_lemmas(sentence: str, tag_fn, lemmatize_fn) -> list[str]:
    tagged = tag_fn(sentence)
    return [
        lemmatize_fn(word.lower())
        for word, tag in tagged
        if tag.startswith("VB")
    ]


def estimate(sentences: list[dict], vocabulary: set[str], tag_fn, lemmatize_fn) -> dict:
    total = 0
    missing: Counter[str] = Counter()
    covered: Counter[str] = Counter()
    for row in sentences:
        for lemma in governing_verb_lemmas(row["sentence"], tag_fn, lemmatize_fn):
            total += 1
            if lemma in vocabulary:
                covered[lemma] += 1
            else:
                missing[lemma] += 1
    missing_total = sum(missing.values())
    return {
        "verb_tokens": total,
        "missing_verb_tokens": missing_total,
        "missing_fraction": missing_total / total if total else None,
        "missing_lemmas": missing.most_common(40),
        "covered_lemmas": covered.most_common(15),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sentences", required=True, type=Path)
    parser.add_argument(
        "--predicates", type=Path, default=Path("data/predicates.tsv")
    )
    parser.add_argument(
        "--roles", type=Path, default=Path("data/verbnet-action-roles.tsv")
    )
    args = parser.parse_args()

    import nltk
    from nltk.stem import WordNetLemmatizer

    lemmatizer = WordNetLemmatizer()

    def tag_fn(sentence: str):
        return nltk.pos_tag(nltk.word_tokenize(sentence))

    def lemmatize_fn(word: str) -> str:
        return lemmatizer.lemmatize(word, pos="v")

    vocabulary = compiled_lemma_vocabulary(args.predicates, args.roles)
    sentences = list(jsonl(args.sentences))
    report = estimate(sentences, vocabulary, tag_fn, lemmatize_fn)

    print(f"compiled vocabulary size: {len(vocabulary)}")
    print(f"instances: {len(sentences)}")
    print(f"verb tokens: {report['verb_tokens']}")
    print(
        f"missing: {report['missing_verb_tokens']} "
        f"({report['missing_fraction']:.1%})"
        if report["missing_fraction"] is not None
        else "missing: n/a (no verb tokens found)"
    )
    print("top missing lemmas:")
    for lemma, count in report["missing_lemmas"]:
        print(f"  {lemma}: {count}")


if __name__ == "__main__":
    main()
