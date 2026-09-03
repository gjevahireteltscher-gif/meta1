#!/usr/bin/env python3
"""Adapt a flat-pipeline WiMCor/ConMeC row for the contextual-tower pipeline.

scripts/evaluation/prepare_wimcor.py and prepare_conmec.py both emit a
shared row shape (id/source/text/target/gold/gold_bridge/...) built for
the flat OpenDomain.hs pipeline. scripts/evaluation/run_contextual_corpus.py
expects a different, smaller shape instead: {id, sentence, source, family,
direction}.

Critically, this is a *lossy* adapter: WiMCor and ConMeC only ever
annotate metonymic-vs-literal plus a bridge-family type (e.g.
"location-for-institution"); neither corpus names a specific correct
Wikidata entity. The contextual tower's own scorer
(scripts/evaluation/score_qid_fibers.py) is built entirely around
exact-QID-in-fiber matching via a gold_qids field these corpora cannot
supply -- there is nothing to adapt it *into*. The gold file this script
produces instead carries only gold_label/gold_bridge_family, meant for
scripts/evaluation/score_contextual_detection.py, which scores the
weaker (but actually attested) claim these corpora support: did the
tower find some bridged reading for a gold-metonymic mention, and none
for a gold-literal one.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def jsonl(path: Path):
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def adapt_row(row: dict) -> tuple[dict, dict]:
    sentence_row = {
        "id": row["id"],
        "sentence": row["text"],
        "source": row["target"],
        "direction": "expand",
        "family": row.get("gold_bridge") or "none",
    }
    gold_row = {
        "id": row["id"],
        "gold_label": row["gold"],
        "gold_bridge_family": row.get("gold_bridge"),
    }
    return sentence_row, gold_row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--sentences-output", required=True, type=Path)
    parser.add_argument("--gold-output", required=True, type=Path)
    args = parser.parse_args()

    sentences = []
    golds = []
    for row in jsonl(args.dataset):
        sentence_row, gold_row = adapt_row(row)
        sentences.append(sentence_row)
        golds.append(gold_row)

    for path, rows in (
        (args.sentences_output, sentences),
        (args.gold_output, golds),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    print(json.dumps({"instances": len(sentences)}, sort_keys=True))


if __name__ == "__main__":
    main()
