from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))

from estimate_action_vocabulary_coverage import (  # noqa: E402
    compiled_lemma_vocabulary,
    estimate,
    governing_verb_lemmas,
)


def fake_tag_fn(sentence: str):
    # A trivial stand-in for nltk.pos_tag: every capitalized word is a
    # noun (NNP), everything else is tagged as a verb (VB) -- enough to
    # exercise the VB*-filtering logic without needing real NLTK models.
    tagged = []
    for word in sentence.split():
        tag = "NNP" if word[0].isupper() else "VB"
        tagged.append((word, tag))
    return tagged


def identity_lemmatize(word: str) -> str:
    return word


class CompiledLemmaVocabularyTests(unittest.TestCase):
    def test_combines_predicates_and_compiled_roles_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            predicates = Path(directory) / "predicates.tsv"
            predicates.write_text(
                "predicate_id\tlemma\tgf_function\tsubject_sort\tobject_sort\tstrength\tgf_expression\tprovenance\n"
                "read\tread\tRead\tHuman\tReadable\tHardRequirement\t"
                'mkV2 "read"\tlocal:selectional-lexicon\n',
                encoding="utf-8",
            )
            roles = Path(directory) / "roles.tsv"
            roles.write_text(
                "action_id\tlemma\tframe_id\tthematic_role\thole_role\trequirement\tstrength\tmapping_status\tprovenance\n"
                "a1\tannounce\tf1\tAgent\tSubjectHole\tHasSort Agent\tSelectionalPreference\tcompiled\tp\n"
                "a2\tvanish\tf2\tAgent\tSubjectHole\tnull\tSelectionalPreference\tuncompiled\tp\n",
                encoding="utf-8",
            )
            vocab = compiled_lemma_vocabulary(predicates, roles)
        self.assertEqual(vocab, {"read", "announce"})
        self.assertNotIn("vanish", vocab)  # uncompiled must not count


class GoverningVerbLemmasTests(unittest.TestCase):
    def test_extracts_only_verb_tagged_tokens(self) -> None:
        result = governing_verb_lemmas(
            "Waterloo announced a programme", fake_tag_fn, identity_lemmatize
        )
        self.assertEqual(result, ["announced", "a", "programme"])
        # (fake_tag_fn's crude capitalization heuristic is deliberately
        # dumb -- this test is about the VB*-filtering plumbing, not about
        # getting real POS tags right, which is NLTK's job not ours.)


class EstimateTests(unittest.TestCase):
    def test_missing_fraction_and_top_lists_are_computed_correctly(self) -> None:
        sentences = [
            {"id": "a", "sentence": "Waterloo announced peace"},
            {"id": "b", "sentence": "Waterloo vanished quietly"},
        ]
        vocabulary = {"announced", "peace"}
        report = estimate(sentences, vocabulary, fake_tag_fn, identity_lemmatize)
        # verb tokens: "announced","peace" (from a) + "vanished","quietly" (from b) = 4
        self.assertEqual(report["verb_tokens"], 4)
        self.assertEqual(report["missing_verb_tokens"], 2)
        self.assertAlmostEqual(report["missing_fraction"], 0.5)
        self.assertIn(("vanished", 1), report["missing_lemmas"])
        self.assertIn(("quietly", 1), report["missing_lemmas"])
        self.assertIn(("announced", 1), report["covered_lemmas"])

    def test_no_verb_tokens_gives_none_fraction_not_a_crash(self) -> None:
        report = estimate([], set(), fake_tag_fn, identity_lemmatize)
        self.assertEqual(report["verb_tokens"], 0)
        self.assertIsNone(report["missing_fraction"])


if __name__ == "__main__":
    unittest.main()
