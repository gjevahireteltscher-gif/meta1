import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from contextual_rule_compiler import compile_gf_constraints


class QidFiberTests(unittest.TestCase):
    def test_waterloo_extraction_and_set_valued_score(self):
        engine = ROOT / "build" / "metonymy"
        if not engine.exists():
            self.skipTest("build/metonymy is not built")
        with tempfile.TemporaryDirectory() as directory:
            inference = Path(directory) / "inference.jsonl"
            report = Path(directory) / "report.json"
            subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/evaluation/extract_qid_fibers.py"),
                    "--dataset",
                    str(ROOT / "evaluation/qid-fiber/waterloo-dataset.jsonl"),
                    "--engine",
                    str(engine),
                    "--output",
                    str(inference),
                ],
                check=True,
                cwd=ROOT,
            )
            subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/evaluation/score_qid_fibers.py"),
                    "--inference",
                    str(inference),
                    "--gold",
                    str(ROOT / "evaluation/qid-fiber/waterloo-gold.jsonl"),
                    "--output",
                    str(report),
                ],
                check=True,
                cwd=ROOT,
            )
            result = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(
                result["gold_in_fiber_hit_rate"],
                {"numerator": 1, "denominator": 1},
            )
            self.assertEqual(result["fiber_cardinality_histogram"], {"2": 1})
            self.assertEqual(result["obstruction_distribution"], {"MissingRelation": 1})
            self.assertEqual(
                result["family_micro_recall"],
                {"numerator": 1, "denominator": 1},
            )

    def test_automatic_multi_source_pipelines(self):
        engine = ROOT / "build" / "metonymy"
        if not engine.exists():
            self.skipTest("build/metonymy is not built")
        snapshot = ROOT / "data/wikidata-openalex-snapshot"
        examples = [
            ("John reads Rumi", "Rumi", "survivors=[Q6579646]"),
            ("Moscow signed the agreement", "Moscow", "survivors=[Q5281]"),
            (
                "Waterloo announced a programme in physics",
                "Waterloo",
                "survivors=[Q1049470,Q2004561]",
            ),
            ("Paris signed the political agreement", "Paris", "survivors=[]"),
            ("Paris signed the commercial agreement", "Paris", "survivors=[Q218115]"),
        ]
        for sentence, source, expected in examples:
            completed = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/run_automatic_contextual_pipeline.py"),
                    "--engine",
                    str(engine),
                    "--snapshot",
                    str(snapshot),
                    "--sentence",
                    sentence,
                    "--source",
                    source,
                ],
                check=True,
                text=True,
                capture_output=True,
                cwd=ROOT,
            )
            self.assertIn(expected, completed.stdout)
            self.assertNotIn("agda-layer-check=false", completed.stdout)
            self.assertEqual(
                completed.stdout.count("stage="),
                completed.stdout.count("agda-layer-check=true"),
            )

    def test_verbnet_only_action_builds_checked_layers(self):
        completed = subprocess.run(
            [
                "python3",
                str(ROOT / "scripts/run_automatic_contextual_pipeline.py"),
                "--engine",
                str(ROOT / "build/metonymy"),
                "--snapshot",
                str(ROOT / "data/wikidata-openalex-snapshot"),
                "--sentence",
                "Waterloo declared a programme in physics",
                "--source",
                "Waterloo",
            ],
            check=True,
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertIn("action=declare role=SubjectHole", completed.stdout)
        self.assertIn("survivors=[Q1049470,Q2004561]", completed.stdout)
        self.assertEqual(
            completed.stdout.count("stage="),
            completed.stdout.count("agda-layer-check=true"),
        )

    def test_proposer_does_not_require_manual_action_registry(self):
        rules = json.loads(
            (ROOT / "data/contextual-language-rules.json").read_text(
                encoding="utf-8"
            )
        )
        rules["morphology_overrides"] = {}
        with tempfile.TemporaryDirectory() as directory:
            rules_path = Path(directory) / "rules.json"
            rules_path.write_text(json.dumps(rules), encoding="utf-8")
            completed = subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/propose_contextual_scenario.py"),
                    "--snapshot",
                    str(ROOT / "data/wikidata-openalex-snapshot"),
                    "--sentence",
                    "Waterloo announced a programme in physics",
                    "--source",
                    "Waterloo",
                    "--rules",
                    str(rules_path),
                ],
                check=True,
                text=True,
                capture_output=True,
                cwd=ROOT,
            )
        proposal = json.loads(completed.stdout)
        self.assertEqual(proposal["status"], "ready")
        self.assertEqual(proposal["action"], "announce")
        self.assertTrue(
            proposal["constraints"][0]["provenance"].startswith(
                "compiled-action-role:v1:"
            )
        )
        self.assertIn("Conducts", proposal["bridge_relations"])

    def test_wordnet_sort_drives_generic_in_modifier_template(self):
        language_rules = json.loads(
            (ROOT / "data/contextual-language-rules.json").read_text(
                encoding="utf-8"
            )
        )
        wordnet_rules = json.loads(
            (ROOT / "data/wordnet-context-rules.json").read_text(encoding="utf-8")
        )
        constraints = compile_gf_constraints(
            {
                "action": "announce",
                "sentence": "Waterloo announced a program in physics",
            },
            (
                'Pred (OpenPN "Waterloo") '
                '(Compl Announce '
                '(ModifyNP (OpenIndefCN "program" "?5") '
                '(InPP (OpenPN "physics"))))'
            ),
            language_rules,
            wordnet_rules,
            {"physics": ["Q413"]},
        )
        self.assertEqual(len(constraints), 1)
        self.assertEqual(
            constraints[0]["payload"]["requires_relation"],
            {"relation": "Conducts", "target": "Q413"},
        )
        self.assertIn(
            "PrincetonWordNet:data.noun:",
            constraints[0]["provenance"],
        )

    def test_unique_and_ambiguous_contextual_contraction(self):
        engine = ROOT / "build" / "metonymy"
        if not engine.exists():
            self.skipTest("build/metonymy is not built")
        snapshot = ROOT / "data/wikidata-openalex-snapshot"
        pipeline = ROOT / "scripts/run_automatic_contextual_pipeline.py"

        unique = subprocess.run(
            [
                "python3",
                str(pipeline),
                "--engine",
                str(engine),
                "--snapshot",
                str(snapshot),
                "--sentence",
                "John reads Masnavi",
                "--source",
                "Rumi",
                "--contract-target",
                "Masnavi",
            ],
            check=True,
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertIn("contract=Q6579646 -> Q43347 safety=unique-contextual-fiber", unique.stdout)
        self.assertEqual(
            unique.stdout.count("stage="),
            unique.stdout.count("agda-layer-check=true"),
        )

        commercial = subprocess.run(
            [
                "python3",
                str(pipeline),
                "--engine",
                str(engine),
                "--snapshot",
                str(snapshot),
                "--sentence",
                "Chanel signed the commercial agreement",
                "--source",
                "Paris",
                "--contract-target",
                "Chanel",
            ],
            check=True,
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertIn("contract=Q218115 -> Q90 safety=unique-contextual-fiber", commercial.stdout)

        ambiguous = subprocess.run(
            [
                "python3",
                str(pipeline),
                "--engine",
                str(engine),
                "--snapshot",
                str(snapshot),
                "--sentence",
                "UWaterloo announced a programme in physics",
                "--source",
                "Waterloo",
                "--contract-target",
                "UWaterloo",
            ],
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertNotEqual(ambiguous.returncode, 0)
        self.assertIn(
            "unsafe-contextual-contraction-non-singleton-fiber",
            ambiguous.stdout + ambiguous.stderr,
        )

        mismatch = subprocess.run(
            [
                "python3",
                str(pipeline),
                "--engine",
                str(engine),
                "--snapshot",
                str(snapshot),
                "--sentence",
                "Chanel signed the political agreement",
                "--source",
                "Paris",
                "--contract-target",
                "Chanel",
            ],
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn(
            "explicit-target-not-in-final-fiber",
            mismatch.stdout + mismatch.stderr,
        )

    def test_unknown_gf_semantic_composition_fails_closed(self):
        completed = subprocess.run(
            [
                "python3",
                str(ROOT / "scripts/run_automatic_contextual_pipeline.py"),
                "--engine",
                str(ROOT / "build/metonymy"),
                "--snapshot",
                str(ROOT / "data/wikidata-openalex-snapshot"),
                "--sentence",
                "Paris signed the secret agreement",
                "--source",
                "Paris",
            ],
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertEqual(completed.returncode, 4)
        self.assertIn("semantic-composition-failed", completed.stdout)


if __name__ == "__main__":
    unittest.main()
