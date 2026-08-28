#!/usr/bin/env python3
"""Prepare the pinned ConMeC CSV with deterministic grouped folds."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

SOURCE_SHA256 = "cd692d6953bb719bb6aeb0ac13df7c3641564918c38cf39ad15bcf20c8b76d90"
HEADER = [
    "Label",
    "Category",
    "Target Word (Noun)",
    "Sentence",
    "Sentence T-2",
    "Sentence T-1",
    "Sentence T+1",
    "Sentence T+2",
    "Document URL",
    "Document Title",
]
CATEGORIES = {"CAUSER", "CONTAINER", "LOCATION", "POSSESSED", "PRODUCER", "PRODUCT"}
BRIDGES = {
    "CAUSER": "causer-for-result",
    "CONTAINER": "container-for-content",
    "LOCATION": "location-for-people",
    "POSSESSED": "possessed-for-possessor",
    "PRODUCER": "producer-for-product",
    "PRODUCT": "product-for-producer",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_label(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"metonymic", "1", "met"}:
        return "metonymic"
    if normalized in {"literal", "0", "non-metonymic", "non_metonymic"}:
        return "literal"
    raise ValueError(f"unknown ConMeC label: {value!r}")


def target_spans(target: str, sentence: str) -> list[list[int]]:
    spans: list[list[int]] = []
    start = 0
    lower_target = target.lower()
    lower_sentence = sentence.lower()
    while True:
        position = lower_sentence.find(lower_target, start)
        if position < 0:
            return spans
        spans.append([position, position + len(target)])
        start = position + max(1, len(target))


def grouped_fold(document_url: str, target: str) -> int:
    key = f"conmec-fold-v1\0{document_url}\0{target.lower()}".encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % 5


def prepare(path: Path) -> tuple[list[dict], list[dict]]:
    actual_hash = sha256_file(path)
    if actual_hash != SOURCE_SHA256:
        raise ValueError(
            f"ConMeC hash mismatch: expected {SOURCE_SHA256}, got {actual_hash}"
        )
    rows: list[dict] = []
    quarantine: list[dict] = []
    source_counts: Counter[str] = Counter()
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != HEADER:
            raise ValueError(f"unexpected ConMeC header: {reader.fieldnames}")
        for ordinal, row in enumerate(reader, 1):
            category = row["Category"].strip().upper()
            if category not in CATEGORIES:
                raise ValueError(f"row {ordinal}: unknown category {category!r}")
            target = row["Target Word (Noun)"].strip()
            sentence = row["Sentence"].strip()
            label = normalize_label(row["Label"])
            source_counts[label] += 1
            spans = target_spans(target, sentence)
            if not spans:
                quarantine.append(
                    {
                        "source_row": ordinal,
                        "reason": "target-not-found",
                        "content_sha256": hashlib.sha256(
                            json.dumps(row, sort_keys=True).encode()
                        ).hexdigest(),
                    }
                )
                continue
            rows.append(
                {
                    "id": f"conmec:{ordinal}",
                    "source": "conmec",
                    "source_sha256": SOURCE_SHA256,
                    "source_row": ordinal,
                    "split": "all",
                    "fold": grouped_fold(row["Document URL"], target),
                    "direction": "expand",
                    "category": category,
                    "text": sentence,
                    "target": target,
                    "target_span": spans[0],
                    "target_spans": spans,
                    "gold": label,
                    "gold_fine": category,
                    "gold_bridge": BRIDGES[category] if label == "metonymic" else None,
                    "context_before": [
                        row["Sentence T-2"],
                        row["Sentence T-1"],
                    ],
                    "context_after": [
                        row["Sentence T+1"],
                        row["Sentence T+2"],
                    ],
                    "document_url": row["Document URL"],
                    "content_sha256": hashlib.sha256(
                        f"{target}\0{sentence}".encode()
                    ).hexdigest(),
                    "license": "Apache-2.0-and-Wikipedia-CC-BY-SA",
                }
            )
    if len(rows) + len(quarantine) != 6000:
        raise ValueError("ConMeC physical row count is not 6000")
    if source_counts != Counter({"literal": 4286, "metonymic": 1714}):
        raise ValueError(f"unexpected ConMeC label counts: {source_counts}")
    return rows, quarantine


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quarantine", type=Path, required=True)
    arguments = parser.parse_args()
    rows, quarantine = prepare(arguments.csv)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    arguments.quarantine.write_text(
        json.dumps(quarantine, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"instances": len(rows), "quarantined": len(quarantine)},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
