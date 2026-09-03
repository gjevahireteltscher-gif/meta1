from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))

from adapt_metonymy_corpus_for_tower import adapt_row, jsonl, main  # noqa: E402


def wimcor_style_row(**overrides) -> dict:
    row = {
        "id": "wimcor:test:1",
        "source": "wimcor-v1.1",
        "source_sha256": "deadbeef",
        "source_row": 1,
        "split": "test",
        "direction": "expand",
        "category": "LOCATION",
        "text": "Waterloo announced a programme in physics",
        "target": "Waterloo",
        "target_span": [0, 8],
        "target_spans": [[0, 8]],
        "gold": "metonymic",
        "gold_fine": "Waterloo",
        "gold_bridge": "location-for-institution",
        "content_sha256": "cafebabe",
        "license": "CC-BY-SA-3.0",
    }
    row.update(overrides)
    return row


class AdaptRowTests(unittest.TestCase):
    def test_metonymic_row_carries_its_bridge_family(self) -> None:
        sentence_row, gold_row = adapt_row(wimcor_style_row())
        self.assertEqual(
            sentence_row,
            {
                "id": "wimcor:test:1",
                "sentence": "Waterloo announced a programme in physics",
                "source": "Waterloo",
                "direction": "expand",
                "family": "location-for-institution",
            },
        )
        self.assertEqual(
            gold_row,
            {
                "id": "wimcor:test:1",
                "gold_label": "metonymic",
                "gold_bridge_family": "location-for-institution",
            },
        )

    def test_literal_row_has_no_gold_bridge_but_still_gets_a_family_placeholder(
        self,
    ) -> None:
        row = wimcor_style_row(
            id="wimcor:test:2",
            text="Waterloo is a small city in Belgium",
            gold="literal",
            gold_bridge=None,
        )
        sentence_row, gold_row = adapt_row(row)
        # run_contextual_corpus.py's run_one accesses row["family"] directly
        # (not .get), so this key must never be absent, even when there is
        # no real gold bridge to report.
        self.assertEqual(sentence_row["family"], "none")
        self.assertIsNone(gold_row["gold_bridge_family"])
        self.assertEqual(gold_row["gold_label"], "literal")

    def test_sentence_row_never_carries_gold_label_or_correctness_information(
        self,
    ) -> None:
        sentence_row, _ = adapt_row(wimcor_style_row())
        self.assertNotIn("gold", sentence_row)
        self.assertNotIn("gold_label", sentence_row)


class MainCliTests(unittest.TestCase):
    def test_writes_both_output_files_with_matching_ids_in_order(self) -> None:
        rows = [
            wimcor_style_row(id="wimcor:test:1"),
            wimcor_style_row(
                id="wimcor:test:2",
                text="Waterloo is a small city",
                gold="literal",
                gold_bridge=None,
            ),
        ]
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "dataset.jsonl"
            dataset.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            sentences_output = Path(directory) / "sentences.jsonl"
            gold_output = Path(directory) / "gold.jsonl"
            sys.argv = [
                "adapt_metonymy_corpus_for_tower.py",
                "--dataset",
                str(dataset),
                "--sentences-output",
                str(sentences_output),
                "--gold-output",
                str(gold_output),
            ]
            main()
            sentences = list(jsonl(sentences_output))
            golds = list(jsonl(gold_output))
        self.assertEqual([row["id"] for row in sentences], ["wimcor:test:1", "wimcor:test:2"])
        self.assertEqual([row["id"] for row in golds], ["wimcor:test:1", "wimcor:test:2"])

    def test_sample_size_shrinks_output_deterministically(self) -> None:
        rows = [wimcor_style_row(id=f"wimcor:test:{index}") for index in range(50)]
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "dataset.jsonl"
            dataset.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )

            def run(seed: int) -> list[str]:
                sentences_output = Path(directory) / f"sentences-{seed}.jsonl"
                gold_output = Path(directory) / f"gold-{seed}.jsonl"
                sys.argv = [
                    "adapt_metonymy_corpus_for_tower.py",
                    "--dataset",
                    str(dataset),
                    "--sentences-output",
                    str(sentences_output),
                    "--gold-output",
                    str(gold_output),
                    "--sample-size",
                    "5",
                    "--seed",
                    str(seed),
                ]
                main()
                return [row["id"] for row in jsonl(sentences_output)]

            first = run(seed=0)
            second = run(seed=0)
            third = run(seed=1)
        self.assertEqual(len(first), 5)
        self.assertEqual(first, second)  # same seed -> same sample
        self.assertNotEqual(first, third)  # different seed -> (almost certainly) different

    def test_sample_size_larger_than_dataset_keeps_everything(self) -> None:
        rows = [wimcor_style_row(id=f"wimcor:test:{index}") for index in range(3)]
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "dataset.jsonl"
            dataset.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            sentences_output = Path(directory) / "sentences.jsonl"
            gold_output = Path(directory) / "gold.jsonl"
            sys.argv = [
                "adapt_metonymy_corpus_for_tower.py",
                "--dataset",
                str(dataset),
                "--sentences-output",
                str(sentences_output),
                "--gold-output",
                str(gold_output),
                "--sample-size",
                "1000",
            ]
            main()
            sentences = list(jsonl(sentences_output))
        self.assertEqual(len(sentences), 3)


if __name__ == "__main__":
    unittest.main()
