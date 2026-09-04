#!/usr/bin/env python3
"""Populate the offline runtime-index SQLite schema from the live Wikidata API.

build_wikidata_runtime_index.py's own ``build`` subcommand requires scanning
a complete local Wikidata JSON dump (100+ GB compressed) to populate its
entities/aliases/claims/metadata tables once; docs/contextual-tower.md keeps
that deliberately outside CI. This script populates the *same* SQLite schema
a different way: resolve a bounded seed set of corpus mention surfaces (plus
optional explicit QIDs) through Wikidata's live wbsearchentities/
wbgetentities/SPARQL endpoints, expand a bounded number of hops along the
same property set, and insert exactly what ``build`` would have inserted for
those entities -- so build_wikidata_runtime_index.py's own ``lookup``/
``materialize`` subcommands and build_wikidata_linker_cache.py work
unchanged against the resulting index.

This is explicitly not a substitute for the full dump index: it only ever
knows about entities reachable from the given seeds within --depth hops,
bounded by --max-entities. It exists so entity-linking-at-scale experiments
do not require downloading and indexing the full dump just to resolve the
few thousand distinct mention surfaces that actually appear in one corpus.

Every network call is funneled through one injectable ``fetch_json``
callable so unit tests run entirely offline against canned responses -- see
tests/evaluation/test_build_wikidata_api_index.py. Wikidata content changes
over time, so re-running this against the same seeds later is not expected
to reproduce byte-identical output the way a pinned dump extraction is; the
recorded ``source_sha256`` metadata pins exactly what this run ingested, not
a claim that Wikidata itself is static. See data/SOURCES.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_wikidata_runtime_index import (  # noqa: E402
    PROPERTIES,
    aliases as record_aliases,
    initialise,
    normalized,
    targets as record_targets,
)

API_ENDPOINT = "https://www.wikidata.org/w/api.php"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "metonymy-research/1.0 (contextual-tower entity linking; offline snapshot builder)"
SEARCH_BATCH = 40


RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


def request_json(
    url: str,
    user_agent: str,
    timeout: int = 60,
    max_retries: int = 6,
    backoff_base: float = 1.0,
) -> dict:
    """Fetch one URL as JSON, retrying transient failures with backoff.

    Wikidata's public API rate-limits aggressively for unauthenticated
    traffic, especially from a shared CI-runner IP range -- a real run
    hit HTTP 429 on a plain sequential wbsearchentities loop with no
    retry at all. Honors a numeric ``Retry-After`` header when the server
    sends one; otherwise backs off exponentially (backoff_base * 2**n,
    capped at 60s). Retries connection-level failures (URLError) the same
    way, since those are just as common on a noisy shared runner.
    """
    request = Request(url, headers={"User-Agent": user_agent})
    attempt = 0
    while True:
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as error:
            attempt += 1
            if error.code not in RETRYABLE_HTTP_CODES or attempt > max_retries:
                raise
            retry_after = error.headers.get("Retry-After") if error.headers else None
            delay = (
                float(retry_after)
                if retry_after and retry_after.isdigit()
                else min(60.0, backoff_base * (2 ** (attempt - 1)))
            )
        except URLError:
            attempt += 1
            if attempt > max_retries:
                raise
            delay = min(60.0, backoff_base * (2 ** (attempt - 1)))
        time.sleep(delay)


def search_exact(
    fetch_json: Callable[[str], dict],
    endpoint: str,
    surface: str,
    language: str,
    limit: int = 20,
) -> list[str]:
    """Resolve one surface to QIDs whose matched label/alias is exactly it.

    wbsearchentities does fuzzy/prefix ranking server-side; only hits whose
    own reported match text is exactly the query (case-insensitively,
    whitespace-normalized) are kept, mirroring
    build_wikidata_linker_cache.py's "exact alias only, ambiguity abstains"
    policy -- an ambiguous surface simply resolves to more than one QID
    here, and callers decide what to do with that.
    """
    data = fetch_json(
        endpoint
        + "?"
        + urlencode(
            {
                "action": "wbsearchentities",
                "search": surface,
                "language": language,
                "format": "json",
                "limit": limit,
                "type": "item",
            }
        )
    )
    target = normalized(surface)
    matches = {
        hit["id"]
        for hit in data.get("search", [])
        if isinstance(hit.get("id"), str)
        and normalized(hit.get("match", {}).get("text", "")) == target
    }
    return sorted(matches)


def expand_neighbors(
    fetch_json: Callable[[str], dict],
    endpoint: str,
    seeds: set[str],
    properties: tuple[str, ...],
    depth: int,
    max_entities: int,
) -> set[str]:
    """Breadth-first SPARQL expansion along ``properties``, both directions.

    Bounded by --depth hops and --max-entities total QIDs (seeds included),
    so a pathological seed set cannot silently balloon into an unbounded
    fetch against a live, rate-limited endpoint.
    """
    visited = set(seeds)
    frontier = set(seeds)
    for _ in range(depth):
        if not frontier or len(visited) >= max_entities:
            break
        neighbors: set[str] = set()
        ordered = sorted(frontier)
        for start in range(0, len(ordered), SEARCH_BATCH):
            batch = ordered[start : start + SEARCH_BATCH]
            values = " ".join(f"wd:{qid}" for qid in batch)
            property_values = " ".join(f"wdt:{p}" for p in properties)
            remaining = max(max_entities - len(visited), 1)
            query = (
                "SELECT DISTINCT ?item WHERE { "
                f"VALUES ?seed {{ {values} }} "
                "{ ?seed ?property ?item } UNION { ?item ?property ?seed } "
                f"VALUES ?property {{ {property_values} }} "
                "FILTER(STRSTARTS(STR(?item), 'http://www.wikidata.org/entity/Q')) "
                f"}} LIMIT {remaining}"
            )
            data = fetch_json(endpoint + "?" + urlencode({"query": query, "format": "json"}))
            neighbors.update(
                binding["item"]["value"].rsplit("/", 1)[-1]
                for binding in data["results"]["bindings"]
            )
        new = neighbors - visited
        room = max(max_entities - len(visited), 0)
        if len(new) > room:
            new = set(sorted(new)[:room])
        visited |= new
        frontier = new
    return visited


def fetch_entities_batch(
    fetch_json: Callable[[str], dict],
    endpoint: str,
    qids: set[str],
    language: str,
) -> list[dict]:
    records = []
    ordered = sorted(qids)
    for start in range(0, len(ordered), 50):
        batch = ordered[start : start + 50]
        data = fetch_json(
            endpoint
            + "?"
            + urlencode(
                {
                    "action": "wbgetentities",
                    "ids": "|".join(batch),
                    "format": "json",
                    "languages": language,
                    "props": "labels|aliases|claims",
                }
            )
        )
        records.extend(data.get("entities", {}).values())
    return sorted(
        (record for record in records if isinstance(record.get("id"), str)),
        key=lambda record: record["id"],
    )


def populate_index(
    connection: sqlite3.Connection, records: list[dict], languages: set[str]
) -> int:
    count = 0
    for record in records:
        qid = record["id"]
        if not qid.startswith("Q"):
            continue
        names = sorted(
            set(record_aliases(record, languages)),
            key=lambda item: (item[1], item[0].casefold()),
        )
        label = next((name for name, rank in names if rank == 0), qid)
        connection.execute("INSERT INTO entities VALUES (?, ?)", (qid, label))
        connection.executemany(
            "INSERT INTO aliases VALUES (?, ?, ?, ?)",
            [(name, normalized(name), qid, rank) for name, rank in names],
        )
        connection.executemany(
            "INSERT INTO claims VALUES (?, ?, ?)",
            [
                (property_id, qid, target)
                for property_id in PROPERTIES
                for target in record_targets(record, property_id)
            ],
        )
        count += 1
    return count


def content_sha256(records: list[dict]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(
            json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def collect_seed_surfaces(seeds_path: Path | None, dataset_path: Path | None, field: str) -> set[str]:
    surfaces: set[str] = set()
    if seeds_path is not None:
        surfaces.update(
            line.strip()
            for line in seeds_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    if dataset_path is not None:
        for line in dataset_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            value = row.get(field)
            if isinstance(value, str) and value.strip():
                surfaces.add(value.strip())
    return surfaces


def build_api_index(
    fetch_json: Callable[[str], dict],
    database: Path,
    surfaces: set[str],
    explicit_qids: set[str],
    languages: str,
    depth: int,
    max_entities: int,
    properties: tuple[str, ...],
    api_endpoint: str,
    sparql_endpoint: str,
) -> dict:
    """Pure-ish orchestration around one injected ``fetch_json`` callable.

    Kept separate from main() so tests can drive the whole pipeline against
    a fake fetcher without touching argv/sqlite file cleanup semantics.
    """
    language = languages.split(",")[0]
    resolved = set(explicit_qids)
    unresolved_surfaces = []
    for surface in sorted(surfaces, key=normalized):
        matches = search_exact(fetch_json, api_endpoint, surface, language)
        if matches:
            resolved.update(matches)
        else:
            unresolved_surfaces.append(surface)

    closure = expand_neighbors(
        fetch_json, sparql_endpoint, resolved, properties, depth, max_entities
    )
    all_qids = resolved | closure
    if len(all_qids) > max_entities:
        all_qids = set(sorted(all_qids)[:max_entities])

    records = fetch_entities_batch(fetch_json, api_endpoint, all_qids, language)

    if database.exists():
        database.unlink()
    connection = sqlite3.connect(database)
    initialise(connection)
    digest = content_sha256(records)
    connection.executemany(
        "INSERT INTO metadata VALUES (?, ?)",
        [
            ("schema_version", "wikidata-runtime-index-2"),
            ("source_sha256", digest),
            ("source_size_bytes", str(sum(len(json.dumps(r)) for r in records))),
            ("languages", languages),
            ("properties", ",".join(PROPERTIES)),
            ("source_kind", "wikidata-live-api"),
            ("api_endpoint", api_endpoint),
            ("sparql_endpoint", sparql_endpoint),
            ("retrieved_at", datetime.now(timezone.utc).isoformat()),
            ("seed_surfaces", str(len(surfaces))),
            ("seed_qids_explicit", ",".join(sorted(explicit_qids))),
            ("unresolved_surfaces", ",".join(sorted(unresolved_surfaces, key=normalized))),
        ],
    )
    inserted = populate_index(connection, records, set(languages.split(",")))
    connection.commit()
    connection.execute("VACUUM")
    connection.close()
    return {
        "seed_surfaces": len(surfaces),
        "resolved_surfaces": len(surfaces) - len(unresolved_surfaces),
        "unresolved_surfaces": len(unresolved_surfaces),
        "seed_qids": len(resolved),
        "closure_qids": len(all_qids),
        "entities_indexed": inserted,
        "source_sha256": digest,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument(
        "--seeds", type=Path, help="newline-delimited mention surfaces to resolve"
    )
    parser.add_argument(
        "--dataset", type=Path, help="corpus JSONL to pull seed mention surfaces from"
    )
    parser.add_argument("--dataset-field", default="source")
    parser.add_argument(
        "--seed-qid",
        action="append",
        default=[],
        help="explicit QID to include regardless of search, repeatable",
    )
    parser.add_argument("--languages", default="en")
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--max-entities", type=int, default=5000)
    parser.add_argument("--properties", default=",".join(PROPERTIES))
    parser.add_argument("--api-endpoint", default=API_ENDPOINT)
    parser.add_argument("--sparql-endpoint", default=SPARQL_ENDPOINT)
    parser.add_argument("--user-agent", default=USER_AGENT)
    parser.add_argument(
        "--request-delay",
        type=float,
        default=0.3,
        help="pause between successful requests, seconds (default: 0.3 -- "
        "a real run on a shared CI-runner IP hit 429s at a shorter delay "
        "even with retry/backoff in place; request_json still retries any "
        "429/5xx that happens anyway)",
    )
    args = parser.parse_args()

    if not args.seeds and not args.dataset and not args.seed_qid:
        raise SystemExit("at least one of --seeds/--dataset/--seed-qid is required")

    surfaces = collect_seed_surfaces(args.seeds, args.dataset, args.dataset_field)

    def fetch(url: str) -> dict:
        result = request_json(url, args.user_agent)
        if args.request_delay:
            time.sleep(args.request_delay)
        return result

    summary = build_api_index(
        fetch,
        args.database,
        surfaces,
        set(args.seed_qid),
        args.languages,
        args.depth,
        args.max_entities,
        tuple(args.properties.split(",")),
        args.api_endpoint,
        args.sparql_endpoint,
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
