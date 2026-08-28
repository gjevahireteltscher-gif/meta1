from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_false_paths import analyze
from prepare_semeval2007 import prepare
from safecon import read_jsonl as read_safecon
from safecon import score_rows as score_safecon
from score_predictions import score, validate
from import_verbnet import render_requirement, restriction_expression


class EvaluationTests(unittest.TestCase):
    def test_verbnet_nested_role_requirements_are_preserved(self) -> None:
        node = ET.fromstring(
            """
            <SELRESTRS logic="or">
              <SELRESTR Value="+" type="animate" />
              <SELRESTR Value="+" type="organization" />
            </SELRESTRS>
            """
        )
        self.assertEqual(
            render_requirement(restriction_expression(node), "Agent"),
            "AnyOf [HasSort Animate,HasSort Organization]",
        )

    def test_verbnet_negative_role_requirement_is_preserved(self) -> None:
        node = ET.fromstring(
            """
            <SELRESTRS>
              <SELRESTR Value="-" type="location" />
            </SELRESTRS>
            """
        )
        self.assertEqual(
            render_requirement(restriction_expression(node), "Theme"),
            "Not (HasSort Place)",
        )

    def test_committed_action_roles_include_announce_subject(self) -> None:
        with (ROOT / "data" / "verbnet-action-roles.tsv").open(
            encoding="utf-8", newline=""
        ) as source:
            rows = csv.DictReader(source, delimiter="\t")
            matching = [
                row
                for row in rows
                if row["lemma"] == "announce"
                and row["hole_role"] == "SubjectHole"
                and row["mapping_status"] == "compiled"
            ]
        self.assertTrue(matching)
        self.assertIn(
            "AnyOf [HasSort Animate,HasSort Organization]",
            {row["requirement"] for row in matching},
        )

    def test_semeval_adapter_preserves_ids_targets_and_labels(self) -> None:
        rows = prepare(
            ROOT / "tests" / "evaluation" / "fixtures" / "semeval.xml",
            "location",
            "test",
        )
        self.assertEqual([row["target"] for row in rows], ["Paris", "Moscow", "Europe"])
        self.assertEqual(
            [row["gold"] for row in rows],
            ["literal", "metonymic", "mixed"],
        )
        self.assertEqual(rows[1]["id"], "location:test:s2")
        self.assertEqual(rows[1]["text"], "Moscow signed the agreement.")

    def test_metrics_separate_expansion_and_contraction(self) -> None:
        dataset = [
            {"id": "e1", "direction": "expand", "gold": "literal"},
            {"id": "e2", "direction": "expand", "gold": "metonymic"},
            {"id": "e3", "direction": "expand", "gold": "mixed"},
            {"id": "c1", "direction": "contract", "gold": "metonymic"},
            {"id": "c2", "direction": "contract", "gold": "literal"},
        ]
        predictions = [
            {
                "id": "e1",
                "ablation": "full",
                "status": "no_rewrite",
                "prediction": "literal",
            },
            {
                "id": "e2",
                "ablation": "full",
                "status": "emitted",
                "prediction": "literal",
            },
            {"id": "e3", "ablation": "full", "status": "abstain"},
            {
                "id": "c1",
                "ablation": "full",
                "status": "emitted",
                "prediction": "metonymic",
            },
            {
                "id": "c2",
                "ablation": "full",
                "status": "emitted",
                "prediction": "metonymic",
            },
        ]
        report = score(dataset, predictions)["full"]
        self.assertEqual(report["expand"]["instances"], 3)
        self.assertEqual(report["contract"]["instances"], 2)
        self.assertAlmostEqual(report["expand"]["coverage"], 2 / 3)
        self.assertAlmostEqual(report["expand"]["micro_precision"], 1 / 2)
        self.assertAlmostEqual(report["expand"]["micro_recall"], 1 / 3)
        self.assertAlmostEqual(report["contract"]["micro_f1"], 1 / 2)

    def test_false_path_categories_are_explicit(self) -> None:
        dataset = [
            {
                "id": "e1",
                "direction": "expand",
                "gold": "literal",
                "gold_fine": "literal",
            }
        ]
        predictions = [
            {
                "id": "e1",
                "ablation": "full",
                "status": "emitted",
                "prediction": "metonymic",
                "path": ["GovernedBy"],
                "runtime_verified": True,
                "agda_verified": True,
            }
        ]
        report = analyze(dataset, predictions)
        self.assertEqual(report["counts"], {"literal-trigger": 1})

    def test_duplicate_predictions_are_rejected(self) -> None:
        dataset = [{"id": "e1", "direction": "expand", "gold": "literal"}]
        prediction = {
            "id": "e1",
            "ablation": "full",
            "status": "no_rewrite",
            "prediction": "literal",
        }
        with self.assertRaisesRegex(ValueError, "duplicate prediction"):
            validate(dataset, [prediction, prediction])

    def test_safecon_dataset_is_balanced_and_paired(self) -> None:
        rows = read_safecon(
            ROOT / "evaluation" / "safecon-mini" / "dataset.jsonl"
        )
        self.assertEqual(len(rows), 24)
        self.assertEqual(
            sum(row["gold"]["action"] == "contract" for row in rows),
            12,
        )
        pairs: dict[str, list[dict]] = {}
        for row in rows:
            pairs.setdefault(row["pair"], []).append(row)
        self.assertEqual(len(pairs), 12)
        self.assertTrue(
            all(
                sorted(item["gold"]["action"] for item in pair)
                == ["contract", "no_contract"]
                for pair in pairs.values()
            )
        )

    def test_safecon_scorer_penalizes_unsafe_and_wrong_targets(self) -> None:
        dataset = [
            {
                "id": "safe",
                "stratum": "engine-overlap",
                "gold": {
                    "action": "contract",
                    "coarse_entity_id": "source",
                },
            },
            {
                "id": "unsafe",
                "stratum": "engine-overlap",
                "gold": {"action": "no_contract"},
            },
        ]
        predictions = [
            {
                "id": "safe",
                "status": "contracted",
                "coarse_entity_id": "wrong",
            },
            {
                "id": "unsafe",
                "status": "contracted",
                "coarse_entity_id": "source",
            },
        ]
        report = score_safecon(dataset, predictions)
        self.assertEqual((report["tp"], report["fp"], report["fn"]), (0, 2, 1))
        self.assertEqual(report["unsafe_contraction_rate"], 1.0)

    def test_endpoint_metrics_use_all_gold_endpoints_as_denominator(self) -> None:
        dataset = [
            {
                "id": "a",
                "direction": "expand",
                "gold": "metonymic",
                "explicit_target": "Endpoint A",
            },
            {
                "id": "b",
                "direction": "expand",
                "gold": "metonymic",
                "explicit_target": "Endpoint B",
            },
        ]
        predictions = [
            {
                "id": "a",
                "ablation": "full",
                "status": "emitted",
                "prediction": "metonymic",
                "predicted_endpoint": "Endpoint A",
            },
            {"id": "b", "ablation": "full", "status": "abstain"},
        ]
        endpoint = score(dataset, predictions)["full"]["expand"]["endpoint"]
        self.assertEqual(endpoint["selective_accuracy"], 1.0)
        self.assertEqual(endpoint["end_to_end_accuracy"], 0.5)
        self.assertEqual(endpoint["recall_at_1"], 0.5)


if __name__ == "__main__":
    unittest.main()
