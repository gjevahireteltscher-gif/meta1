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
        self.assertIn(
            "constraint=Prefers (AnyOf [HasSort Animate,HasSort Organization])"
            "@declare",
            completed.stdout,
        )
        self.assertIn("preferred=[Q1049470,Q2004561]", completed.stdout)
        self.assertIn("survivors=[Q1049470,Q2004561]", completed.stdout)
        self.assertIn(
            "constraint=RequiresSome Conducts (HasSort ScientificDiscipline)"
            "@declare programme",
            completed.stdout,
        )
        self.assertIn(
            "constraint=RequiresRelation Conducts Q413"
            "@declare programme in physics",
            completed.stdout,
        )
        self.assertEqual(
            completed.stdout.count("stage="),
            completed.stdout.count("agda-layer-check=true"),
        )

    def test_existential_capability_layer_emits_checked_obstructions(self):
        completed = subprocess.run(
            [
                "python3",
                str(ROOT / "scripts/run_automatic_contextual_pipeline.py"),
                "--engine",
                str(ROOT / "build/metonymy"),
                "--snapshot",
                str(ROOT / "data/wikidata-openalex-snapshot"),
                "--sentence",
                "Stavropol declared a program",
                "--source",
                "Stavropol",
            ],
            check=True,
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertIn(
            "constraint=RequiresSome Conducts (HasSort ScientificDiscipline)"
            "@declare program",
            completed.stdout,
        )
        self.assertIn("obstruction=MissingRelated", completed.stdout)
        self.assertIn("survivors=[]", completed.stdout)
        self.assertTrue(completed.stdout.rstrip().endswith("ScientificDiscipline)"))
        self.assertEqual(
            completed.stdout.count("stage="),
            completed.stdout.count("agda-layer-check=true"),
        )

    def test_closed_gf_noun_still_builds_cumulative_frame_layer(self):
        completed = subprocess.run(
            [
                "python3",
                str(ROOT / "scripts/run_automatic_contextual_pipeline.py"),
                "--engine",
                str(ROOT / "build/metonymy"),
                "--snapshot",
                str(ROOT / "data/wikidata-openalex-snapshot"),
                "--sentence",
                "Moscow signed the agreement",
                "--source",
                "Moscow",
            ],
            check=True,
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertIn(
            "constraint=Requires (HasSort Agent)@sign agreement",
            completed.stdout,
        )
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
        self.assertEqual(
            proposal["bridge_relations"],
            ["InstitutionOf", "AffiliatedWith"],
        )

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
                "frames": [{"frame": "Statement"}],
                "provenance": {"action": "test:VerbNet:announce"},
                "constraints": [
                    {
                        "origin": {
                            "constructor": "Verb",
                            "lemma": "announce",
                            "surface": "announced",
                            "start": 9,
                            "end": 18,
                        },
                        "payload": {
                            "requires": (
                                "AnyOf [HasSort Animate,HasSort Organization]"
                            )
                        },
                        "provenance": "test:VerbNet:announce",
                    }
                ],
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
        self.assertEqual(len(constraints), 2)
        self.assertEqual(
            constraints[0]["payload"]["requires_some"],
            {
                "relation": "Conducts",
                "requirement": "HasSort ScientificDiscipline",
            },
        )
        self.assertEqual(
            constraints[0]["origin"]["lemma"],
            "announce program",
        )
        self.assertEqual(
            constraints[1]["payload"]["requires_relation"],
            {"relation": "Conducts", "target": "Q413"},
        )
        self.assertIn(
            "PrincetonWordNet:data.noun:",
            constraints[1]["provenance"],
        )
        self.assertEqual(
            constraints[1]["origin"]["lemma"],
            "announce program in physics",
        )

    def test_positive_pp_constructions_compile_from_sort_templates(self):
        language_rules = json.loads(
            (ROOT / "data/contextual-language-rules.json").read_text(
                encoding="utf-8"
            )
        )
        wordnet_rules = json.loads(
            (ROOT / "data/wordnet-context-rules.json").read_text(encoding="utf-8")
        )
        cases = [
            ("book", "AboutPP", "physics", "About"),
            ("agreement", "WithPP", "Chanel", "AffiliatedWith"),
            ("program", "ForPP", "physics", "About"),
        ]
        for head, pp_constructor, target, relation in cases:
            sentence = f"Paris signed a {head} {pp_constructor[:-2].lower()} {target}"
            proposal = {
                "action": "sign",
                "role": "SubjectHole",
                "sentence": sentence,
                "frames": [{"frame": "Sign_agreement"}],
                "frame_role_projections": [],
                "provenance": {"action": "test:VerbNet:sign"},
                "constraints": [
                    {
                        "origin": {
                            "constructor": "Verb",
                            "lemma": "sign",
                            "surface": "signed",
                            "start": 6,
                            "end": 12,
                        },
                        "payload": {"requires": "HasSort Agent"},
                        "provenance": "test:VerbNet:sign",
                    }
                ],
            }
            constraints = compile_gf_constraints(
                proposal,
                (
                    'Pred (OpenPN "Paris") '
                    f'(Compl Sign (ModifyNP (OpenIndefCN "{head}" "?5") '
                    f'({pp_constructor} (OpenPN "{target}"))))'
                ),
                language_rules,
                wordnet_rules,
                {
                    "physics": ["Q413"],
                    "chanel": ["Q218115"],
                },
            )
            self.assertEqual(
                constraints[-1]["payload"]["prefers_relation"],
                {
                    "relation": relation,
                    "target": "Q218115" if target == "Chanel" else "Q413",
                },
            )

    def test_relative_clause_compiles_relation_lexicalization(self):
        language_rules = json.loads(
            (ROOT / "data/contextual-language-rules.json").read_text(
                encoding="utf-8"
            )
        )
        wordnet_rules = json.loads(
            (ROOT / "data/wordnet-context-rules.json").read_text(encoding="utf-8")
        )
        proposal = {
            "action": "examine",
            "role": "ObjectHole",
            "sentence": "Anna examines an institution that conducts physics",
            "frames": [],
            "frame_role_projections": [],
            "provenance": {"action": "test:VerbNet:examine"},
            "constraints": [
                {
                    "origin": {
                        "constructor": "Verb",
                        "lemma": "examine",
                        "surface": "examines",
                        "start": 5,
                        "end": 13,
                    },
                    "payload": {"prefers": "HasSort Organization"},
                    "provenance": "test:VerbNet:examine",
                }
            ],
            "lexical_evidence": [
                {
                    "surface": "institution",
                    "start": 17,
                    "end": 28,
                    "requirement": "HasSort Institution",
                    "provenance": "test:WordNet:institution",
                }
            ],
        }
        constraints = compile_gf_constraints(
            proposal,
            (
                'Pred (OpenPN "Anna") '
                '(Compl Examine '
                '(ModifyRel (OpenIndefCN "institution" "?5") '
                'Conduct (OpenPN "physics")))'
            ),
            language_rules,
            wordnet_rules,
            {"physics": ["Q413"]},
            gf_actions={"Conduct": "conduct"},
        )
        self.assertEqual(
            constraints[-1]["payload"]["requires_relation"],
            {"relation": "Conducts", "target": "Q413"},
        )
        self.assertEqual(
            constraints[-1]["origin"]["lemma"],
            "examine institution that conduct physics",
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
