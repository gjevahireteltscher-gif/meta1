#!/usr/bin/env python3
"""Import OpenAlex institution-topic evidence into canonical QID relations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def request_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "metonymy-research/1.0"})
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def qid(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.rsplit("/", 1)[-1]
    return candidate if candidate.startswith("Q") else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--per-page", type=int, default=200)
    parser.add_argument("--source-qids", help="comma-separated QIDs to resolve by label")
    args = parser.parse_args()
    aliases = {}
    labels = {}
    with (args.snapshot / "entities.jsonl").open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            entity_labels = row.get("labels") or [row["id"]]
            labels[row["id"]] = entity_labels[0]
    with (args.snapshot / "aliases.jsonl").open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            aliases.setdefault(row["alias"].casefold(), set()).add(row["id"])
    cursor = "*"
    relations = []
    pages = []
    if args.source_qids:
        for source_qid in args.source_qids.split(","):
            data = request_json(
                "https://api.openalex.org/institutions?"
                + urlencode({"search": labels.get(source_qid, source_qid), "per-page": 10})
            )
            pages.append(data)
    else:
        for _ in range(args.pages):
            data = request_json(
                "https://api.openalex.org/institutions?"
                + urlencode({"per-page": args.per_page, "cursor": cursor})
            )
            pages.append(data)
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break
    for data in pages:
        for institution in data.get("results", []):
            source_qid = qid(institution.get("ids", {}).get("wikidata"))
            if not source_qid:
                continue
            for topic in institution.get("topics", []):
                topic_name = topic.get("display_name", "").casefold()
                candidates = aliases.get(topic_name, set())
                if not candidates:
                    candidates = {
                        qid
                        for alias, qids in aliases.items()
                        if len(alias) >= 4 and alias in topic_name
                        for qid in qids
                    }
                if len(candidates) == 1:
                    relations.append(
                        {
                            "relation": "Conducts",
                            "source": source_qid,
                            "target": next(iter(candidates)),
                            "provenance": f"OpenAlex:{institution['id']}:{topic['id']}",
                        }
                    )
    unique = {
        (row["relation"], row["source"], row["target"], row["provenance"]): row
        for row in relations
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in unique.values()),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
