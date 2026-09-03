from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))

from score_contextual_detection import predict, score  # noqa: E402


def ok_row(id_: str, fiber: list[str]) -> dict:
    return {"id": id_, "status": "ok", "fiber": fiber, "stages": []}


def failed_row(id_: str, exit_code: int = 3) -> dict:
    return {"id": id_, "status": "failed", "exit_code": exit_code, "fiber": [], "stages": []}


class PredictTests(unittest.TestCase):
    def test_ok_with_nonempty_fiber_is_metonymic(self) -> None:
        self.assertEqual(predict(ok_row("a", ["Q1"])), "metonymic")

    def test_ok_with_empty_fiber_is_literal(self) -> None:
        self.assertEqual(predict(ok_row("a", [])), "literal")

    def test_failed_run_is_literal_regardless_of_fiber_field(self) -> None:
        self.assertEqual(predict(failed_row("a")), "literal")


class ScoreTests(unittest.TestCase):
    def test_true_positive_true_negative_false_positive_false_negative(self) -> None:
        inference = [
            ok_row("tp", ["Q1"]),
            ok_row("tn", []),
            ok_row("fp", ["Q2"]),
            failed_row("fn"),
        ]
        gold = [
            {"id": "tp", "gold_label": "metonymic", "gold_bridge_family": "x"},
            {"id": "tn", "gold_label": "literal", "gold_bridge_family": None},
            {"id": "fp", "gold_label": "literal", "gold_bridge_family": None},
            {"id": "fn", "gold_label": "metonymic", "gold_bridge_family": "x"},
        ]
        report = score(inference, gold)
        self.assertEqual(
            report["confusion"],
            {
                "true_positive": 1,
                "false_positive": 1,
                "true_negative": 1,
                "false_negative": 1,
            },
        )
        self.assertEqual(report["precision"], 0.5)
        self.assertEqual(report["recall"], 0.5)
        self.assertEqual(report["f1"], 0.5)

    def test_missing_inference_row_is_counted_not_silently_dropped(self) -> None:
        gold = [{"id": "missing", "gold_label": "metonymic", "gold_bridge_family": "x"}]
        report = score([], gold)
        self.assertEqual(report["missing_inference_rows"], 1)
        self.assertEqual(
            report["confusion"],
            {
                "true_positive": 0,
                "false_positive": 0,
                "true_negative": 0,
                "false_negative": 0,
            },
        )

    def test_perfect_score_has_no_undefined_precision_or_recall(self) -> None:
        inference = [ok_row("a", ["Q1"]), ok_row("b", [])]
        gold = [
            {"id": "a", "gold_label": "metonymic", "gold_bridge_family": "x"},
            {"id": "b", "gold_label": "literal", "gold_bridge_family": None},
        ]
        report = score(inference, gold)
        self.assertEqual(report["precision"], 1.0)
        self.assertEqual(report["recall"], 1.0)
        self.assertEqual(report["f1"], 1.0)

    def test_zero_positive_predictions_gives_none_precision_not_a_crash(self) -> None:
        inference = [ok_row("a", [])]
        gold = [{"id": "a", "gold_label": "metonymic", "gold_bridge_family": "x"}]
        report = score(inference, gold)
        self.assertIsNone(report["precision"])
        self.assertEqual(report["recall"], 0.0)
        self.assertIsNone(report["f1"])

    def test_literal_prediction_reasons_are_tallied_by_status(self) -> None:
        inference = [failed_row("a"), failed_row("b"), ok_row("c", [])]
        gold = [
            {"id": "a", "gold_label": "literal", "gold_bridge_family": None},
            {"id": "b", "gold_label": "metonymic", "gold_bridge_family": "x"},
            {"id": "c", "gold_label": "literal", "gold_bridge_family": None},
        ]
        report = score(inference, gold)
        self.assertEqual(
            report["literal_prediction_reasons"], {"failed": 2, "ok": 1}
        )


if __name__ == "__main__":
    unittest.main()
