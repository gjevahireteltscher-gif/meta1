from __future__ import annotations

import contextlib
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_wikidata_api_index  # noqa: E402
from build_wikidata_api_index import (  # noqa: E402
    build_api_index,
    collect_seed_surfaces,
    content_sha256,
    expand_neighbors,
    fetch_entities_batch,
    populate_index,
    request_json,
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

    def test_resolved_qids_excludes_sparql_expanded_neighbors(self) -> None:
        # Q649 resolves directly from the surface "Waterloo"; Q2 only shows
        # up via SPARQL neighbor expansion. resolved_qids is meant to seed
        # build_wikidata_runtime_index.py materialize's own bounded walk,
        # so it must be just the corpus's own mentions (Q649), not every
        # entity this run happened to ingest (Q649 and Q2) -- passing the
        # full ingested set as materialize's seeds made a real run redo a
        # bounded walk redundantly from thousands of points instead of a
        # few hundred.
        def fetch(url: str) -> dict:
            params = query_params(url)
            if params.get("action") == "wbsearchentities":
                return {"search": [{"id": "Q649", "match": {"text": "Waterloo"}}]}
            if "query" in params:
                return {
                    "results": {
                        "bindings": [
                            {"item": {"value": "http://www.wikidata.org/entity/Q2"}}
                        ]
                    }
                }
            if params.get("action") == "wbgetentities":
                ids = params["ids"].split("|")
                return {
                    "entities": {
                        qid: {"id": qid, "labels": {}, "aliases": {}, "claims": {}}
                        for qid in ids
                    }
                }
            raise AssertionError(f"unexpected request: {url}")

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runtime.sqlite"
            summary = build_api_index(
                fetch,
                database,
                {"Waterloo"},
                set(),
                "en",
                depth=1,
                max_entities=100,
                properties=("P31",),
                api_endpoint="https://www.wikidata.org/w/api.php",
                sparql_endpoint="https://query.wikidata.org/sparql",
            )
        self.assertEqual(summary["resolved_qids"], ["Q649"])
        self.assertEqual(summary["closure_qids"], 2)  # Q649 and Q2 both ingested

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


class MainResolvedQidsOutputTests(unittest.TestCase):
    def test_writes_resolved_qids_to_the_requested_file_and_omits_them_from_stdout(
        self,
    ) -> None:
        canned_summary = {
            "seed_surfaces": 1,
            "resolved_surfaces": 1,
            "unresolved_surfaces": 0,
            "seed_qids": 1,
            "resolved_qids": ["Q649"],
            "closure_qids": 2,
            "entities_indexed": 2,
            "source_sha256": "deadbeef",
        }
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runtime.sqlite"
            resolved_output = Path(directory) / "resolved-qids.txt"
            sys.argv = [
                "build_wikidata_api_index.py",
                "--database",
                str(database),
                "--seed-qid",
                "Q649",
                "--resolved-qids-output",
                str(resolved_output),
            ]
            stdout = io.StringIO()
            with patch.object(
                build_wikidata_api_index,
                "build_api_index",
                return_value=canned_summary,
            ):
                with contextlib.redirect_stdout(stdout):
                    build_wikidata_api_index.main()
            self.assertEqual(resolved_output.read_text(encoding="utf-8"), "Q649\n")
            self.assertNotIn("resolved_qids", stdout.getvalue())
            self.assertIn("entities_indexed", stdout.getvalue())


class ContentSha256Tests(unittest.TestCase):
    def test_is_order_sensitive_so_callers_must_pass_sorted_records(self) -> None:
        first = [{"id": "Q1"}, {"id": "Q2"}]
        second = [{"id": "Q2"}, {"id": "Q1"}]
        self.assertNotEqual(content_sha256(first), content_sha256(second))

    def test_is_deterministic_for_the_same_input(self) -> None:
        records = [{"id": "Q1"}, {"id": "Q2"}]
        self.assertEqual(content_sha256(records), content_sha256(records))


def _fake_response(payload: dict):
    return io.BytesIO(__import__("json").dumps(payload).encode("utf-8"))


class RequestJsonRetryTests(unittest.TestCase):
    """A real run hit HTTP 429 on a plain sequential search loop with no
    retry at all -- these lock in that request_json now backs off and
    retries instead of failing the whole run on the first rate limit.
    """

    def test_succeeds_immediately_with_no_retry_needed(self) -> None:
        with patch("build_wikidata_api_index.urlopen") as mock_urlopen, patch(
            "build_wikidata_api_index.time.sleep"
        ) as mock_sleep:
            mock_urlopen.return_value.__enter__.return_value = _fake_response({"ok": True})
            result = request_json("https://example/x", "ua")
        self.assertEqual(result, {"ok": True})
        mock_sleep.assert_not_called()

    def test_retries_after_a_429_and_then_succeeds(self) -> None:
        error = HTTPError("https://example/x", 429, "Too Many Requests", {}, None)
        success = io.StringIO()
        with patch("build_wikidata_api_index.urlopen") as mock_urlopen, patch(
            "build_wikidata_api_index.time.sleep"
        ) as mock_sleep:
            mock_urlopen.side_effect = [
                error,
                _managed(_fake_response({"ok": True})),
            ]
            result = request_json(
                "https://example/x", "ua", max_retries=3, backoff_base=1.0
            )
        self.assertEqual(result, {"ok": True})
        mock_sleep.assert_called_once()

    def test_respects_a_numeric_retry_after_header(self) -> None:
        from email.message import Message

        headers = Message()
        headers["Retry-After"] = "7"
        error = HTTPError("https://example/x", 429, "Too Many Requests", headers, None)
        with patch("build_wikidata_api_index.urlopen") as mock_urlopen, patch(
            "build_wikidata_api_index.time.sleep"
        ) as mock_sleep:
            mock_urlopen.side_effect = [error, _managed(_fake_response({"ok": True}))]
            request_json("https://example/x", "ua", max_retries=3)
        mock_sleep.assert_called_once_with(7.0)

    def test_non_retryable_status_raises_immediately(self) -> None:
        error = HTTPError("https://example/x", 404, "Not Found", {}, None)
        with patch("build_wikidata_api_index.urlopen") as mock_urlopen, patch(
            "build_wikidata_api_index.time.sleep"
        ) as mock_sleep:
            mock_urlopen.side_effect = error
            with self.assertRaises(HTTPError):
                request_json("https://example/x", "ua", max_retries=3)
        mock_sleep.assert_not_called()

    def test_gives_up_after_max_retries(self) -> None:
        error = HTTPError("https://example/x", 429, "Too Many Requests", {}, None)
        with patch("build_wikidata_api_index.urlopen") as mock_urlopen, patch(
            "build_wikidata_api_index.time.sleep"
        ):
            mock_urlopen.side_effect = error
            with self.assertRaises(HTTPError):
                request_json("https://example/x", "ua", max_retries=2)
        self.assertEqual(mock_urlopen.call_count, 3)  # initial + 2 retries

    def test_connection_error_is_retried_too(self) -> None:
        with patch("build_wikidata_api_index.urlopen") as mock_urlopen, patch(
            "build_wikidata_api_index.time.sleep"
        ) as mock_sleep:
            mock_urlopen.side_effect = [
                URLError("connection reset"),
                _managed(_fake_response({"ok": True})),
            ]
            result = request_json("https://example/x", "ua", max_retries=3)
        self.assertEqual(result, {"ok": True})
        mock_sleep.assert_called_once()


class _managed:
    """Wrap a plain file-like object so it works as urlopen's context manager."""

    def __init__(self, response) -> None:
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, *exc_info) -> bool:
        return False


if __name__ == "__main__":
    unittest.main()
