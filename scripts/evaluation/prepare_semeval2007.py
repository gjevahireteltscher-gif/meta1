#!/usr/bin/env python3
"""Convert locally supplied SemEval-2007 Task 8 XML into local JSONL.

The output may contain BNC-derived contexts and must remain outside Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def coarse_label(label: str) -> str:
    normalized = label.strip().lower()
    if normalized.startswith("literal"):
        return "literal"
    if normalized.startswith("mixed"):
        return "mixed"
    return "metonymic"


def annotation(sample: ET.Element) -> str:
    for element in sample.iter():
        if local_name(element.tag) in {"location", "org", "organisation"}:
            reading = element.get("reading")
            if reading:
                if reading == "metonymic" and element.get("metotype"):
                    return element.get("metotype", reading)
                return reading
    for key in ("label", "type", "metonymy"):
        if sample.get(key):
            return sample.get(key, "")
    for element in sample.iter():
        if local_name(element.tag) in {"annot", "annotation", "label"}:
            value = element.get("label") or element.get("type") or element.text
            if value and value.strip():
                return value.strip()
    raise ValueError(f"sample {sample.get('id')} has no annotation")


def target_text(sample: ET.Element) -> str:
    target_names = {"location", "organization", "organisation", "org", "target", "enamex"}
    for element in sample.iter():
        if local_name(element.tag) in target_names:
            text = "".join(element.itertext()).strip()
            if text:
                return text
    raise ValueError(f"sample {sample.get('id')} has no marked target")


def context_text(sample: ET.Element) -> str:
    for element in sample.iter():
        if local_name(element.tag) in {"context", "sentence", "sent", "par"}:
            text = " ".join("".join(element.itertext()).split())
            if text:
                return text
    return " ".join("".join(sample.itertext()).split())


def samples(root: ET.Element) -> list[ET.Element]:
    selected = [
        element
        for element in root.iter()
        if local_name(element.tag) in {"sample", "instance"}
    ]
    if not selected:
        raise ValueError("no <sample> or <instance> elements found")
    return selected


def prepare(path: Path, domain: str, split: str) -> list[dict]:
    root = ET.parse(path).getroot()
    rows: list[dict] = []
    for index, sample in enumerate(samples(root), 1):
        identifier = sample.get("id") or sample.get("xml:id") or str(index)
        fine = annotation(sample)
        rows.append(
            {
                "id": f"{domain}:{split}:{identifier}",
                "source": "semeval-2007-task-8",
                "split": split,
                "domain": domain,
                "direction": "expand",
                "text": context_text(sample),
                "target": target_text(sample),
                "gold": coarse_label(fine),
                "gold_fine": fine,
            }
        )
    return rows


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml", type=Path, required=True)
    parser.add_argument(
        "--domain", choices=("location", "organisation"), required=True
    )
    parser.add_argument("--split", choices=("train", "dev", "test"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256")
    arguments = parser.parse_args()
    actual_hash = sha256(arguments.xml)
    if arguments.expected_sha256 and actual_hash != arguments.expected_sha256:
        raise SystemExit(
            f"dataset hash mismatch: expected {arguments.expected_sha256}, got {actual_hash}"
        )
    rows = prepare(arguments.xml, arguments.domain, arguments.split)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps({"instances": len(rows), "sha256": actual_hash}, sort_keys=True))


if __name__ == "__main__":
    main()
