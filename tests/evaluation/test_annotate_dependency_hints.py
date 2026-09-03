from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from annotate_dependency_hints import (  # noqa: E402
    annotate,
    classify_word,
    find_governing_structure,
    validate_row,
)


class FakeToken:
    def __init__(self, start_char: int, end_char: int) -> None:
        self.start_char = start_char
        self.end_char = end_char


class FakeWord:
    def __init__(
        self,
        word_id: int,
        text: str,
        lemma: str,
        upos: str,
        deprel: str,
        head: int,
        start_char: int,
        end_char: int,
    ) -> None:
        self.id = word_id
        self.text = text
        self.lemma = lemma
        self.upos = upos
        self.deprel = deprel
        self.head = head
        self.parent = FakeToken(start_char, end_char)


class FakeSentence:
    def __init__(self, words: list[FakeWord]) -> None:
        self.words = words


class FakeDocument:
    def __init__(self, sentences: list[FakeSentence]) -> None:
        self.sentences = sentences


def moscow_signed_document() -> FakeDocument:
    # "Moscow signed the agreement"
    #  0     7      14  18
    words = [
        FakeWord(1, "Moscow", "Moscow", "PROPN", "nsubj", 2, 0, 6),
        FakeWord(2, "signed", "sign", "VERB", "root", 0, 7, 13),
        FakeWord(3, "the", "the", "DET", "det", 4, 14, 17),
        FakeWord(4, "agreement", "agreement", "NOUN", "obj", 2, 18, 27),
    ]
    return FakeDocument([FakeSentence(words)])


class ClassifyWordTests(unittest.TestCase):
    def test_subject_of_a_verb_is_a_direct_argument(self) -> None:
        document = moscow_signed_document()
        sentence = document.sentences[0]
        target_word = sentence.words[0]
        self.assertEqual(
            classify_word(sentence, target_word),
            ("direct-argument", "Subject", "sign", 7, 13),
        )

    def test_object_of_a_verb_is_a_direct_argument(self) -> None:
        document = moscow_signed_document()
        sentence = document.sentences[0]
        target_word = sentence.words[3]
        self.assertEqual(
            classify_word(sentence, target_word),
            ("direct-argument", "Object", "sign", 7, 13),
        )

    def test_oblique_with_case_child_reconstructs_a_phrasal_verb_lemma(self) -> None:
        # "The teenager listened to Mozart"
        #  0   4        13       22 25
        words = [
            FakeWord(1, "The", "the", "DET", "det", 2, 0, 3),
            FakeWord(2, "teenager", "teenager", "NOUN", "nsubj", 3, 4, 12),
            FakeWord(3, "listened", "listen", "VERB", "root", 0, 13, 21),
            FakeWord(4, "to", "to", "ADP", "case", 5, 22, 24),
            FakeWord(5, "Mozart", "Mozart", "PROPN", "obl", 3, 25, 31),
        ]
        sentence = FakeSentence(words)
        self.assertEqual(
            classify_word(sentence, words[4]),
            ("direct-argument", "Object", "listen to", 13, 24),
        )

    def test_nested_possessive_modifier_is_not_a_direct_argument(self) -> None:
        # "Anna reads Tolstoy's books"
        words = [
            FakeWord(1, "Anna", "Anna", "PROPN", "nsubj", 2, 0, 4),
            FakeWord(2, "reads", "read", "VERB", "root", 0, 5, 10),
            FakeWord(3, "Tolstoy", "Tolstoy", "PROPN", "nmod:poss", 5, 11, 18),
            FakeWord(4, "'s", "'s", "PART", "case", 3, 18, 20),
            FakeWord(5, "books", "book", "NOUN", "obj", 2, 21, 26),
        ]
        sentence = FakeSentence(words)
        self.assertEqual(
            classify_word(sentence, words[2]),
            ("nested-modifier", "", "", None, None),
        )

    def test_no_governing_verb_for_an_unhandled_relation(self) -> None:
        words = [
            FakeWord(1, "Yesterday", "yesterday", "ADV", "advmod", 2, 0, 9),
            FakeWord(2, "left", "leave", "VERB", "root", 0, 10, 14),
        ]
        sentence = FakeSentence(words)
        self.assertEqual(
            classify_word(sentence, words[0]),
            ("no-governing-verb", "", "", None, None),
        )


class FindGoverningStructureTests(unittest.TestCase):
    def test_single_token_span_resolves_directly(self) -> None:
        document = moscow_signed_document()
        self.assertEqual(
            find_governing_structure(document, 0, 6),
            ("direct-argument", "Subject", "sign", 7, 13),
        )

    def test_multi_token_span_resolves_to_the_phrase_internal_root(self) -> None:
        # "Anna visited New York"
        #  0    5       14  18
        words = [
            FakeWord(1, "Anna", "Anna", "PROPN", "nsubj", 2, 0, 4),
            FakeWord(2, "visited", "visit", "VERB", "root", 0, 5, 12),
            FakeWord(3, "New", "New", "PROPN", "compound", 4, 13, 16),
            FakeWord(4, "York", "York", "PROPN", "obj", 2, 17, 21),
        ]
        document = FakeDocument([FakeSentence(words)])
        self.assertEqual(
            find_governing_structure(document, 13, 21),
            ("direct-argument", "Object", "visit", 5, 12),
        )

    def test_span_with_no_covering_token_is_a_parse_error(self) -> None:
        document = moscow_signed_document()
        self.assertEqual(
            find_governing_structure(document, 100, 110),
            ("parse-error", "", "", None, None),
        )


class ValidateRowTests(unittest.TestCase):
    def test_valid_row_returns_text_and_span(self) -> None:
        row = {
            "id": "wimcor:test:0",
            "text": "Moscow signed the agreement",
            "target": "Moscow",
            "target_span": [0, 6],
        }
        self.assertEqual(validate_row(row), ("Moscow signed the agreement", 0, 6))

    def test_span_not_matching_target_text_is_invalid(self) -> None:
        row = {
            "id": "wimcor:test:1",
            "text": "Moscow signed the agreement",
            "target": "Moscow",
            "target_span": [7, 13],  # actually covers "signed", not "Moscow"
        }
        self.assertIsNone(validate_row(row))

    def test_missing_text_or_span_is_invalid(self) -> None:
        self.assertIsNone(
            validate_row({"id": "x", "text": "", "target": "Moscow", "target_span": [0, 1]})
        )
        # No target_span at all, and "Moscow" is genuinely absent from the
        # text -- the word-boundary fallback must not match anything.
        self.assertIsNone(
            validate_row({"id": "x", "text": "Anna reads Tolstoy", "target": "Moscow"})
        )

    def test_missing_span_falls_back_to_word_boundary_match(self) -> None:
        # The contextual-tower corpus format (evaluation/contextual-multidomain/)
        # supplies only a plain mention string, no character span --
        # mirrors scripts/contextual_rule_compiler.py's _mention_span.
        row = {
            "id": "ctx:0",
            "text": "Waterloo announced a new research programme",
            "target": "Waterloo",
        }
        self.assertEqual(
            validate_row(row),
            ("Waterloo announced a new research programme", 0, 8),
        )

    def test_fallback_match_is_case_insensitive_and_word_bounded(self) -> None:
        row = {"id": "ctx:1", "text": "the waterloo team won", "target": "Waterloo"}
        self.assertEqual(validate_row(row), ("the waterloo team won", 4, 12))
        # "Water" must not match inside "Waterloo" (word-boundary required).
        row_partial = {"id": "ctx:2", "text": "the waterloo team won", "target": "Water"}
        self.assertIsNone(validate_row(row_partial))

    def test_alternate_field_names(self) -> None:
        row = {
            "id": "ctx:3",
            "sentence": "Waterloo announced a new research programme",
            "source": "Waterloo",
        }
        self.assertEqual(
            validate_row(row, text_field="sentence", target_field="source"),
            ("Waterloo announced a new research programme", 0, 8),
        )
        # Default field names do not see these rows at all.
        self.assertIsNone(validate_row(row))


class AnnotateTests(unittest.TestCase):
    """``annotate`` batches every distinct valid sentence text through one
    (or a few) calls to a batch-callable pipeline, per Stanza's own
    guidance that calling the pipeline once per short text is very slow --
    see the module docstring. These tests use a batch-callable
    ``pipeline_batch(texts: list[str]) -> list[FakeDocument]`` mock rather
    than a real Stanza pipeline.
    """

    def test_span_not_matching_target_is_a_parse_error_without_parsing(self) -> None:
        calls: list[list[str]] = []

        def pipeline_batch(texts: list[str]) -> list[FakeDocument]:
            calls.append(list(texts))
            return [moscow_signed_document() for _ in texts]

        row = {
            "id": "wimcor:test:0",
            "text": "Moscow signed the agreement",
            "target": "Moscow",
            "target_span": [7, 13],
        }
        hints = list(annotate(pipeline_batch, [row]))
        self.assertEqual(
            hints,
            [
                {
                    "id": "wimcor:test:0",
                    "dep_status": "parse-error",
                    "hole_role": "",
                    "governing_lemma": "",
                    "governing_start": None,
                    "governing_end": None,
                }
            ],
        )
        self.assertEqual(calls, [])  # nothing valid to parse, pipeline never called

    def test_valid_row_resolves_through_the_pipeline(self) -> None:
        def pipeline_batch(texts: list[str]) -> list[FakeDocument]:
            return [moscow_signed_document() for _ in texts]

        row = {
            "id": "wimcor:test:1",
            "text": "Moscow signed the agreement",
            "target": "Moscow",
            "target_span": [0, 6],
        }
        hints = list(annotate(pipeline_batch, [row]))
        self.assertEqual(
            hints,
            [
                {
                    "id": "wimcor:test:1",
                    "dep_status": "direct-argument",
                    "hole_role": "Subject",
                    "governing_lemma": "sign",
                    "governing_start": 7,
                    "governing_end": 13,
                }
            ],
        )

    def test_batch_pipeline_exception_degrades_that_batch_to_parse_error(self) -> None:
        def failing_pipeline(texts: list[str]) -> list[FakeDocument]:
            raise RuntimeError("boom")

        row = {
            "id": "wimcor:test:2",
            "text": "Moscow signed the agreement",
            "target": "Moscow",
            "target_span": [0, 6],
        }
        hints = list(annotate(failing_pipeline, [row]))
        self.assertEqual(hints[0]["dep_status"], "parse-error")

    def test_identical_sentence_text_is_parsed_only_once(self) -> None:
        calls: list[list[str]] = []

        def pipeline_batch(texts: list[str]) -> list[FakeDocument]:
            calls.append(list(texts))
            return [moscow_signed_document() for _ in texts]

        rows = [
            {
                "id": "wimcor:test:0",
                "text": "Moscow signed the agreement",
                "target": "Moscow",
                "target_span": [0, 6],
            },
            {
                "id": "wimcor:test:1",
                "text": "Moscow signed the agreement",
                "target": "agreement",
                "target_span": [18, 27],
            },
        ]
        hints = list(annotate(pipeline_batch, rows))
        self.assertEqual(len(hints), 2)
        self.assertEqual(calls, [["Moscow signed the agreement"]])
        self.assertEqual(hints[0]["hole_role"], "Subject")
        self.assertEqual(hints[1]["hole_role"], "Object")

    def test_batch_size_chunks_distinct_texts(self) -> None:
        calls: list[list[str]] = []

        def pipeline_batch(texts: list[str]) -> list[FakeDocument]:
            calls.append(list(texts))
            return [moscow_signed_document() for _ in texts]

        rows = [
            {
                "id": f"wimcor:test:{index}",
                "text": f"Moscow signed the agreement {index}",
                "target": "Moscow",
                "target_span": [0, 6],
            }
            for index in range(3)
        ]
        list(annotate(pipeline_batch, rows, batch_size=2))
        self.assertEqual([len(chunk) for chunk in calls], [2, 1])

    def test_progress_callback_receives_batch_counts(self) -> None:
        progress: list[tuple[int, int]] = []

        def pipeline_batch(texts: list[str]) -> list[FakeDocument]:
            return [moscow_signed_document() for _ in texts]

        rows = [
            {
                "id": f"wimcor:test:{index}",
                "text": f"Moscow signed the agreement {index}",
                "target": "Moscow",
                "target_span": [0, 6],
            }
            for index in range(3)
        ]
        list(
            annotate(
                pipeline_batch,
                rows,
                batch_size=2,
                on_progress=lambda done, total: progress.append((done, total)),
            )
        )
        self.assertEqual(progress, [(1, 2), (2, 2)])

    def test_alternate_field_names_reach_the_pipeline(self) -> None:
        # The contextual-tower corpus shape: {"sentence", "source"}, no span.
        def pipeline_batch(texts: list[str]) -> list[FakeDocument]:
            return [moscow_signed_document() for _ in texts]

        row = {
            "id": "ctx:0",
            "sentence": "Moscow signed the agreement",
            "source": "Moscow",
        }
        hints = list(
            annotate(
                pipeline_batch, [row], text_field="sentence", target_field="source"
            )
        )
        self.assertEqual(hints[0]["dep_status"], "direct-argument")
        self.assertEqual(hints[0]["hole_role"], "Subject")
        self.assertEqual(hints[0]["governing_lemma"], "sign")


if __name__ == "__main__":
    unittest.main()
