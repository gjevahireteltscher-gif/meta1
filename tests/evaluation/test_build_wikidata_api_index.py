from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_wikidata_api_index import (  # noqa: E402
    build_api_index,
    collect_seed_surfaces,
    content_sha256,
    expand_neighbors,
    fetch_entities_batch,
    populate_index,
    search_exact,
)
from build_wikidata_runtime_index import initialise  # noqa: E402


def query_params(url: str) -> dict[str, str]:
    return {key: value[0] for key, value in parse_qs(urlparse(url).query).items()}


class SearchExactTests(unittest.TestCase):
    def test_keeps_only_hits_whose_match_text_is_exactly_the_surface(self) -> None:
        def fetch(url: str) -> dict:
            return {
                "search": [
                    {"id": "Q649", "match": {"text": "Waterloo"}},
                    {"id": "Q1129448", "match": {"text": "Waterloo Road"}},
                ]
            }

        self.assertEqual(search_exact(fetch, "https://x", "Waterloo", "en"), ["Q649"])

    def test_is_case_and_whitespace_insensitive(self) -> None:
        def fetch(url: str) -> dict:
            return {"search": [{"id": "Q649", "match": {"text": "waterloo"}}]}

        self.assertEqual(search_exact(fetch, "https://x", "  Waterloo  ", "en"), ["Q649"])

    def test_no_exact_hit_returns_empty(self) -> None:
        def fetch(url: str) -> dict:
            return {"search": [{"id": "Q1129448", "match": {"text": "Waterloo Road"}}]}

        self.assertEqual(search_exact(fetch, "https://x", "Waterloo", "en"), [])

    def test_ambiguous_surface_returns_every_exact_candidate(self) -> None:
        def fetch(url: str) -> dict:
            return {
                "search": [
                    {"id": "Q649", "match": {"text": "Waterloo"}},
                    {"id": "Q1748716", "match": {"text": "Waterloo"}},
                ]
            }

        self.assertEqual(
            search_exact(fetch, "https://x", "Waterloo", "en"), ["Q1748716", "Q649"]
        )


class ExpandNeighborsTests(unittest.TestCase):
    def test_single_hop_collects_neighbors_from_sparql(self) -> None:
        def fetch(url: str) -> dict:
            return {
                "results": {
                    "bindings": [
                        {"item": {"value": "http://www.wikidata.org/entity/Q2"}},
                        {"item": {"value": "http://www.wikidata.org/entity/Q3"}},
                    ]
                }
            }

        result = expand_neighbors(
            fetch, "https://sparql", {"Q1"}, ("P31",), depth=1, max_entities=100
        )
        self.assertEqual(result, {"Q1", "Q2", "Q3"})

    def test_zero_depth_returns_only_the_seeds(self) -> None:
        calls = []

        def fetch(url: str) -> dict:
            calls.append(url)
            return {"results": {"bindings": []}}

        result = expand_neighbors(
            fetch, "https://sparql", {"Q1"}, ("P31",), depth=0, max_entities=100
        )
        self.assertEqual(result, {"Q1"})
        self.assertEqual(calls, [])

    def test_expansion_stops_growing_past_max_entities(self) -> None:
        def fetch(url: str) -> dict:
            return {
                "results": {
                    "bindings": [
                        {"item": {"value": f"http://www.wikidata.org/entity/Q{n}"}}
                        for n in range(2, 50)
                    ]
                }
            }

        result = expand_neighbors(
            fetch, "https://sparql", {"Q1"}, ("P31",), depth=3, max_entities=5
        )
        self.assertLessEqual(len(result), 5)
        self.assertIn("Q1", result)

    def test_two_hops_reach_a_second_degree_neighbor(self) -> None:
        def fetch(url: str) -> dict:
            query = query_params(url)["query"]
            if "wd:Q2" in query:
                return {
                    "results": {
                        "bindings": [
                            {"item": {"value": "http://www.wikidata.org/entity/Q3"}}
                        ]
                    }
                }
            if "wd:Q1" in query:
                return {
                    "results": {
                        "bindings": [
                            {"item": {"value": "http://www.wikidata.org/entity/Q2"}}
                        ]
                    }
                }
            raise AssertionError(f"unexpected SPARQL query: {query}")

        result = expand_neighbors(
            fetch, "https://sparql", {"Q1"}, ("P31",), depth=2, max_entities=100
        )
        self.assertEqual(result, {"Q1", "Q2", "Q3"})


class FetchEntitiesBatchTests(unittest.TestCase):
    def test_batches_requests_at_fifty_ids(self) -> None:
        qids = {f"Q{n}" for n in range(1, 121)}
        batches = []

        def fetch(url: str) -> dict:
            ids = query_params(url)["ids"].split("|")
            batches.append(ids)
            return {"entities": {qid: {"id": qid, "labels": {}, "claims": {}} for qid in ids}}

        records = fetch_entities_batch(fetch, "https://api", qids, "en")
        self.assertEqual(sorted(len(batch) for batch in batches), [20, 50, 50])
        self.assertEqual({record["id"] for record in records}, qids)

    def test_records_are_sorted_by_id(self) -> None:
        def fetch(url: str) -> dict:
            return {
                "entities": {
                    "Q9": {"id": "Q9", "labels": {}, "claims": {}},
                    "Q2": {"id": "Q2", "labels": {}, "claims": {}},
                }
            }

        records = fetch_entities_batch(fetch, "https://api", {"Q9", "Q2"}, "en")
        self.assertEqual([record["id"] for record in records], ["Q2", "Q9"])


class PopulateIndexTests(unittest.TestCase):
    def test_inserts_entities_aliases_and_claims(self) -> None:
        connection = sqlite3.connect(":memory:")
        initialise(connection)
        records = [
            {
                "id": "Q649",
                "labels": {"en": {"language": "en", "value": "Waterloo"}},
                "aliases": {"en": [{"language": "en", "value": "Battle of Waterloo"}]},
                "claims": {
                    "P31": [
                        {
                            "mainsnak": {
                                "datavalue": {"value": {"id": "Q178561"}}
                            },
                            "rank": "normal",
                        }
                    ]
                },
            }
        ]
        count = populate_index(connection, records, {"en"})
        self.assertEqual(count, 1)
        self.assertEqual(
            connection.execute("SELECT label FROM entities WHERE qid='Q649'").fetchone(),
            ("Waterloo",),
        )
        aliases = {
            row[0] for row in connection.execute("SELECT alias FROM aliases WHERE qid='Q649'")
        }
        self.assertEqual(aliases, {"Waterloo", "Battle of Waterloo"})
        claims = connection.execute(
            "SELECT property, source, target FROM claims WHERE source='Q649'"
        ).fetchall()
        self.assertEqual(claims, [("P31", "Q649", "Q178561")])

    def test_deprecated_claims_are_not_ingested(self) -> None:
        connection = sqlite3.connect(":memory:")
        initialise(connection)
        records = [
            {
                "id": "Q1",
                "labels": {"en": {"language": "en", "value": "One"}},
                "aliases": {},
                "claims": {
                    "P31": [
                        {
                            "mainsnak": {"datavalue": {"value": {"id": "Q2"}}},
                            "rank": "deprecated",
                        }
                    ]
                },
            }
        ]
        populate_index(connection, records, {"en"})
        self.assertEqual(
            connection.execute("SELECT COUNT(*) FROM claims").fetchone(), (0,)
        )


class CollectSeedSurfacesTests(unittest.TestCase):
    def test_reads_seeds_file_and_dataset_field_together(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            seeds = Path(directory) / "seeds.txt"
            seeds.write_text("Tolstoy\nWaterloo\n", encoding="utf-8")
            dataset = Path(directory) / "dataset.jsonl"
            dataset.write_text(
                '{"id": "1", "source": "Napoleon"}\n{"id": "2", "source": ""}\n',
                encoding="utf-8",
            )
            surfaces = collect_seed_surfaces(seeds, dataset, "source")
        self.assertEqual(surfaces, {"Tolstoy", "Waterloo", "Napoleon"})

    def test_missing_field_in_a_row_is_skipped_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "dataset.jsonl"
            dataset.write_text('{"id": "1"}\n', encoding="utf-8")
            surfaces = collect_seed_surfaces(None, dataset, "source")
        self.assertEqual(surfaces, set())


class BuildApiIndexEndToEndTests(unittest.TestCase):
    def test_full_pipeline_produces_a_queryable_index_with_honest_metadata(self) -> None:
        def fetch(url: str) -> dict:
            params = query_params(url)
            if params.get("action") == "wbsearchentities":
                if params["search"] == "Waterloo":
                    return {"search": [{"id": "Q649", "match": {"text": "Waterloo"}}]}
                if params["search"] == "Nowhere":
                    return {"search": [{"id": "Q999", "match": {"text": "Nowhereville"}}]}
                return {"search": []}
            if "query" in params:
                return {"results": {"bindings": []}}
            if params.get("action") == "wbgetentities":
                ids = params["ids"].split("|")
                entities = {}
                if "Q649" in ids:
                    entities["Q649"] = {
                        "id": "Q649",
                        "labels": {"en": {"language": "en", "value": "Waterloo"}},
                        "aliases": {},
                        "claims": {},
                    }
                return {"entities": entities}
            raise AssertionError(f"unexpected request: {url}")

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runtime.sqlite"
            summary = build_api_index(
                fetch,
                database,
                {"Waterloo", "Nowhere"},
                set(),
                "en",
                depth=1,
                max_entities=100,
                properties=("P31",),
                api_endpoint="https://www.wikidata.org/w/api.php",
                sparql_endpoint="https://query.wikidata.org/sparql",
            )
            self.assertEqual(summary["seed_surfaces"], 2)
            self.assertEqual(summary["resolved_surfaces"], 1)
            self.assertEqual(summary["unresolved_surfaces"], 1)
            self.assertEqual(summary["entities_indexed"], 1)

            connection = sqlite3.connect(database)
            self.assertEqual(
                connection.execute(
                    "SELECT value FROM metadata WHERE key='source_kind'"
                ).fetchone(),
                ("wikidata-live-api",),
            )
            self.assertEqual(
                connection.execute(
                    "SELECT value FROM metadata WHERE key='unresolved_surfaces'"
                ).fetchone(),
                ("Nowhere",),
            )
            self.assertIsNotNone(
                connection.execute(
                    "SELECT value FROM metadata WHERE key='source_sha256'"
                ).fetchone()
            )
            self.assertEqual(
                connection.execute(
                    "SELECT qid, label FROM entities WHERE qid='Q649'"
                ).fetchone(),
                ("Q649", "Waterloo"),
            )
            connection.close()

    def test_explicit_seed_qid_is_ingested_even_without_a_matching_surface(self) -> None:
        def fetch(url: str) -> dict:
            params = query_params(url)
            if params.get("action") == "wbsearchentities":
                return {"search": []}
            if "query" in params:
                return {"results": {"bindings": []}}
            if params.get("action") == "wbgetentities":
                return {
                    "entities": {
                        "Q649": {
                            "id": "Q649",
                            "labels": {"en": {"language": "en", "value": "Waterloo"}},
                            "aliases": {},
                            "claims": {},
                        }
                    }
                }
            raise AssertionError(f"unexpected request: {url}")

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runtime.sqlite"
            summary = build_api_index(
                fetch,
                database,
                set(),
                {"Q649"},
                "en",
                depth=0,
                max_entities=100,
                properties=("P31",),
                api_endpoint="https://www.wikidata.org/w/api.php",
                sparql_endpoint="https://query.wikidata.org/sparql",
            )
            self.assertEqual(summary["seed_qids"], 1)
            self.assertEqual(summary["entities_indexed"], 1)


class ContentSha256Tests(unittest.TestCase):
    def test_is_order_sensitive_so_callers_must_pass_sorted_records(self) -> None:
        first = [{"id": "Q1"}, {"id": "Q2"}]
        second = [{"id": "Q2"}, {"id": "Q1"}]
        self.assertNotEqual(content_sha256(first), content_sha256(second))

    def test_is_deterministic_for_the_same_input(self) -> None:
        records = [{"id": "Q1"}, {"id": "Q2"}]
        self.assertEqual(content_sha256(records), content_sha256(records))


if __name__ == "__main__":
    unittest.main()
