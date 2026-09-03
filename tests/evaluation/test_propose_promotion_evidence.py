from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from propose_promotion_evidence import build_prompt, propose  # noqa: E402


class BuildPromptTests(unittest.TestCase):
    def test_prompt_includes_all_candidate_fields(self) -> None:
        candidate = {
            "id": "a",
            "sentence": "Waterloo announced a new research programme",
            "target": "Waterloo",
            "target_surface": "the institution of Waterloo",
            "family": "location-for-institution",
        }
        prompt = build_prompt(candidate)
        self.assertIn("Waterloo announced a new research programme", prompt)
        self.assertIn("the institution of Waterloo", prompt)
        self.assertIn("location-for-institution", prompt)
        self.assertIn('"salient"', prompt)


class ProposeTests(unittest.TestCase):
    CANDIDATE = {
        "id": "a",
        "sentence": "s",
        "target": "t",
        "target_surface": "x",
        "family": "f",
        "target_entity_id": "Q1",
    }

    def test_salient_judgment_becomes_evidence(self) -> None:
        evidence = propose(
            [self.CANDIDATE],
            lambda prompt: {"salient": True, "justification": "ok"},
            "llm:test:pilot",
        )
        self.assertEqual(
            evidence,
            [{"id": "a", "target_entity_id": "Q1", "source": "llm:test:pilot"}],
        )

    def test_non_salient_judgment_produces_no_evidence(self) -> None:
        evidence = propose(
            [self.CANDIDATE],
            lambda prompt: {"salient": False, "justification": "no"},
            "llm:test:pilot",
        )
        self.assertEqual(evidence, [])

    def test_query_failure_defaults_to_no_evidence(self) -> None:
        def failing_query(prompt: str) -> dict:
            raise RuntimeError("boom")

        evidence = propose([self.CANDIDATE], failing_query, "llm:test:pilot")
        self.assertEqual(evidence, [])

    def test_malformed_response_defaults_to_no_evidence(self) -> None:
        # Missing "salient" key entirely -- .get(...) is None -> falsy.
        evidence = propose(
            [self.CANDIDATE], lambda prompt: {"justification": "oops"}, "llm:test:pilot"
        )
        self.assertEqual(evidence, [])


if __name__ == "__main__":
    unittest.main()
