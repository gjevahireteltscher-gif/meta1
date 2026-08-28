#!/usr/bin/env python3
"""Download a reproducible, typed author-work slice from Wikidata."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "proof-carrying-metonymy/0.1 (research prototype)"


def query(limit: int) -> str:
    return f"""
SELECT ?author ?authorLabel ?work ?workLabel WHERE {{
  ?author wdt:P106/wdt:P279* wd:Q49757 ;
          wdt:P800 ?work .
  ?work wdt:P31/wdt:P279* wd:Q7725634 .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT {limit}
""".strip()


def qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def clean_label(value: str) -> str:
    return " ".join(value.replace("\t", " ").replace("\n", " ").split())


def fetch(limit: int) -> list[tuple[str, str, str, str, str]]:
    encoded = urllib.parse.urlencode({"query": query(limit), "format": "json"})
    request = urllib.request.Request(
        f"{ENDPOINT}?{encoded}",
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": USER_AGENT,
        },
    )
    payload = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.load(response)
            break
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 3:
                raise
            time.sleep(2**attempt)
    if payload is None:
        raise RuntimeError("Wikidata request produced no payload")

    rows: set[tuple[str, str, str, str, str]] = set()
    for binding in payload["results"]["bindings"]:
        author_id = qid(binding["author"]["value"])
        work_id = qid(binding["work"]["value"])
        author_label = clean_label(binding["authorLabel"]["value"])
        work_label = clean_label(binding["workLabel"]["value"])
        if author_label == author_id or work_label == work_id:
            continue
        rows.add(
            (
                author_id,
                author_label,
                work_id,
                work_label,
                "Wikidata:P106/P800/P31",
            )
        )
    return sorted(rows, key=lambda row: (row[1].casefold(), row[3].casefold()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum SPARQL result rows before label filtering.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/wikidata-author-works.tsv"),
    )
    arguments = parser.parse_args()

    rows = fetch(arguments.limit)
    if not rows:
        raise SystemExit("Wikidata returned no usable author-work rows")

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(
            ["author_id", "author_label", "work_id", "work_label", "provenance"]
        )
        writer.writerows(rows)

    print(f"wrote {len(rows)} author-work facts to {arguments.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
