#!/usr/bin/env python3
"""Prepare WiMCor v1.1 directly from its verified tar archive."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import tarfile
from pathlib import Path

ARCHIVE_SHA256 = "df4d52a63d9c03cdce543f5d9638efafab73736ce117f90352373fd7051f8e2b"
SPLITS = {
    "full": ("wimcor-v1.1/dataset/xml/full-corpus.xml", 206000),
    "train": ("wimcor-v1.1/dataset/xml/train-partition.xml", 123600),
    "validation": ("wimcor-v1.1/dataset/xml/val-partition.xml", 41200),
    "test": ("wimcor-v1.1/dataset/xml/test-partition.xml", 41200),
}
SAMPLE = re.compile(rb"<sample>(.*?)</sample>", re.DOTALL)
PMW = re.compile(
    rb"<pmw\s+coarse='([^']+)'\s+medium='([^']+)'\s+fine='([^']+)'>(.*?)</pmw>",
    re.DOTALL,
)
TAG = re.compile(r"<[^>]+>")
BRIDGES = {
    "INSTITUTE": "location-for-institution",
    "ARTIFACT": "location-for-artifact",
    "TEAM": "location-for-team",
    "EVENT": "location-for-event",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_text(payload: bytes) -> str:
    decoded = payload.decode("utf-8", errors="replace")
    # A space, not "": WiMCor's raw XML has inline tags directly abutting
    # adjacent text with no whitespace at the boundary (e.g.
    # "raised in<pmw ...>High Point</pmw>"). Deleting the tag glues the
    # surrounding words together ("raised inHigh Point"), which still
    # passes this module's own substring check (target_position =
    # text.lower().find(target.lower())) but fails every downstream
    # \b-anchored word-boundary match (contextual_rule_compiler.py's
    # _mention_span) -- verified against the full 41,200-row test split:
    # substituting a space here instead resolves all of them with zero
    # regressions, since the surrounding .split()/" ".join() collapses
    # any resulting double space back to one wherever a real space
    # already existed at the boundary.
    return " ".join(html.unescape(TAG.sub(" ", decoded)).split())


def prepare(archive: Path, split: str) -> list[dict]:
    actual_hash = sha256_file(archive)
    if actual_hash != ARCHIVE_SHA256:
        raise ValueError(
            f"WiMCor archive hash mismatch: expected {ARCHIVE_SHA256}, got {actual_hash}"
        )
    member_name, expected_count = SPLITS[split]
    with tarfile.open(archive, "r:gz") as bundle:
        member = bundle.getmember(member_name)
        if not member.isfile():
            raise ValueError(f"WiMCor member is not a regular file: {member_name}")
        extracted = bundle.extractfile(member)
        if extracted is None:
            raise ValueError(f"cannot read WiMCor member: {member_name}")
        payload = extracted.read()
    rows: list[dict] = []
    for ordinal, match in enumerate(SAMPLE.finditer(payload), 1):
        raw_sample = match.group(1)
        annotation = PMW.search(raw_sample)
        if annotation is None:
            raise ValueError(f"WiMCor sample {ordinal} has no valid pmw annotation")
        coarse, medium, fine, target_payload = annotation.groups()
        target = clean_text(target_payload)
        text = clean_text(raw_sample)
        target_position = text.lower().find(target.lower())
        if target_position < 0:
            raise ValueError(f"WiMCor sample {ordinal} target reconstruction failed")
        medium_label = medium.decode("utf-8")
        is_metonymic = coarse == b"met"
        rows.append(
            {
                "id": f"wimcor:{split}:{ordinal}",
                "source": "wimcor-v1.1",
                "source_sha256": ARCHIVE_SHA256,
                "source_row": ordinal,
                "split": split,
                "direction": "expand",
                "category": "LOCATION",
                "text": text,
                "target": target,
                "target_span": [target_position, target_position + len(target)],
                "target_spans": [[target_position, target_position + len(target)]],
                "gold": "metonymic" if is_metonymic else "literal",
                "gold_fine": medium_label,
                "gold_bridge": BRIDGES.get(medium_label),
                "explicit_target": html.unescape(
                    fine.decode("utf-8", errors="replace")
                ),
                "content_sha256": sha256_bytes(raw_sample),
                "license": "CC-BY-SA-3.0",
            }
        )
    if len(rows) != expected_count:
        raise ValueError(
            f"WiMCor {split} count mismatch: expected {expected_count}, got {len(rows)}"
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--split", choices=sorted(SPLITS), required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    rows = prepare(arguments.archive, arguments.split)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"instances": len(rows), "split": arguments.split}))


if __name__ == "__main__":
    main()
