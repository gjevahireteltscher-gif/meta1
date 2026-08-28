#!/usr/bin/env python3
"""Fetch a reproducible, multi-domain seed dump for repository fixtures only."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SPARQL = "https://query.wikidata.org/sparql"
API = "https://www.wikidata.org/w/api.php"
CLASSES = {
    "university": "Q3918",
    "city": "Q515",
    "organization": "Q43229",
    "business": "Q4830453",
    "writer": "Q49757",
    "sports-team": "Q12973014",
}
PINNED_QIDS = {
    "Q639408", "Q1049470", "Q2004561", "Q7974219", "Q413",
    "Q649", "Q2184", "Q218115", "Q7243", "Q43347", "Q6579646",
}
NEIGHBOR_PROPERTIES = (
    "P176", "P50", "P131", "P159", "P749", "P361", "P31", "P279"
)


def request_json(url: str) -> dict:
    request = Request(
        url,
        headers={"User-Agent": "metonymy-research-fixture/1.0 (offline snapshot builder)"},
    )
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def qids_for_class(qid: str, limit: int) -> list[str]:
    query = f"SELECT ?item WHERE {{ ?item wdt:P31 wd:{qid} . }} LIMIT {limit}"
    data = request_json(SPARQL + "?" + urlencode({"query": query, "format": "json"}))
    return sorted(
        binding["item"]["value"].rsplit("/", 1)[-1]
        for binding in data["results"]["bindings"]
    )


def related_qids(seeds: set[str], limit: int = 500) -> list[str]:
    results = set()
    ordered = sorted(seeds)
    for start in range(0, len(ordered), 40):
        values = " ".join(f"wd:{qid}" for qid in ordered[start : start + 40])
        query = (
            f"SELECT DISTINCT ?item WHERE {{ VALUES ?seed {{ {values} }} "
            f"{{ ?seed ?property ?item }} UNION {{ ?item ?property ?seed }} "
            f"VALUES ?property {{ {' '.join(f'wdt:{p}' for p in NEIGHBOR_PROPERTIES)} }} "
            f"FILTER(STRSTARTS(STR(?item), 'http://www.wikidata.org/entity/Q')) }} LIMIT {limit}"
        )
        data = request_json(SPARQL + "?" + urlencode({"query": query, "format": "json"}))
        results.update(
            binding["item"]["value"].rsplit("/", 1)[-1]
            for binding in data["results"]["bindings"]
        )
    return sorted(results)


def entities(qids: list[str]) -> list[dict]:
    result = []
    for start in range(0, len(qids), 50):
        batch = qids[start : start + 50]
        data = request_json(
            API
            + "?"
            + urlencode(
                {
                    "action": "wbgetentities",
                    "ids": "|".join(batch),
                    "format": "json",
                    "languages": "en",
                    "props": "labels|aliases|claims",
                }
            )
        )
        result.extend(data["entities"].values())
        time.sleep(0.1)
    return sorted(result, key=lambda entity: entity["id"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--per-class", type=int, default=60)
    args = parser.parse_args()
    base_qids = PINNED_QIDS | {
            qid
            for class_qid in CLASSES.values()
            for qid in qids_for_class(class_qid, args.per_class)
        }
    closure = set(PINNED_QIDS)
    for _ in range(2):
        closure |= set(related_qids(closure))
    qids = sorted(base_qids | closure)
    rows = entities(qids)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(f"wrote {len(rows)} entities")


if __name__ == "__main__":
    main()
