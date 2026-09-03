from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))

from extract_promotion_candidates import extract  # noqa: E402


class ExtractPromotionCandidatesTests(unittest.TestCase):
    def test_extracts_only_matching_ablation_preference_abstentions(self) -> None:
        predictions = [
            {
                "id": "a",
                "ablation": "full",
                "status": "abstain",
                "abstention_reason": (
                    "selectional-preference:the institution of Waterloo\tQ12345"
                ),
                "predicted_bridge": "location-for-institution",
            },
            {
                "id": "b",
                "ablation": "full",
                "status": "abstain",
                "abstention_reason": "target-not-found",
            },
            {
                "id": "c",
                "ablation": "no-types",
                "status": "abstain",
                "abstention_reason": "selectional-preference:x\tQ1",
            },
            {
                "id": "d",
                "ablation": "full",
                "status": "emitted",
                "prediction": "metonymic",
            },
        ]
        inputs_by_id = {
            "a": {
                "id": "a",
                "text": "Waterloo announced a new research programme",
                "target": "Waterloo",
            },
        }
        result = extract(predictions, inputs_by_id, "full")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "a")
        self.assertEqual(result[0]["target_entity_id"], "Q12345")
        self.assertEqual(result[0]["target_surface"], "the institution of Waterloo")
        self.assertEqual(
            result[0]["sentence"], "Waterloo announced a new research programme"
        )
        self.assertEqual(result[0]["family"], "location-for-institution")

    def test_skips_rows_without_a_matching_input(self) -> None:
        predictions = [
            {
                "id": "missing",
                "ablation": "full",
                "status": "abstain",
                "abstention_reason": "selectional-preference:x\tQ1",
            },
        ]
        self.assertEqual(extract(predictions, {}, "full"), [])

    def test_ignores_abstentions_without_a_target_id(self) -> None:
        # Guards against ever matching something that merely starts with
        # "selectional-preference:" but wasn't produced by the enriched
        # renderOpenBatchRow branch (no embedded tab -> no raw target id).
        predictions = [
            {
                "id": "a",
                "ablation": "full",
                "status": "abstain",
                "abstention_reason": "selectional-preference:no target id here",
            },
        ]
        inputs_by_id = {"a": {"id": "a", "text": "x", "target": "y"}}
        self.assertEqual(extract(predictions, inputs_by_id, "full"), [])


if __name__ == "__main__":
    unittest.main()
