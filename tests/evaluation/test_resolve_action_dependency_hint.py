"""Unit tests for the optional dependency_hint fast path in resolve_action.

These tests deliberately construct a sentence where the legacy
character-offset heuristic (target before the verb => SubjectHole, target
after => ObjectHole) gives the WRONG role, so that a passing hint-driven
test actually exercises the fix rather than coincidentally agreeing with
the old behaviour.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from annotate_dependency_hints import classify_word  # noqa: E402
from contextual_rule_compiler import ActionRole, resolve_action  # noqa: E402

# Fronted-object construction: "Tolstoy" is textually BEFORE the verb
# "praised" but is grammatically its OBJECT, not its subject. The legacy
# offset heuristic assigns SubjectHole (wrong); a UD-derived hint --
# hole_role="Object", the exact string annotate_dependency_hints.py
# actually emits, not the ActionRole-internal "ObjectHole" spelling --
# assigns ObjectHole (right).
SENTENCE = "Tolstoy, the critics praised generously"
VERB_START = SENTENCE.index("praised")
VERB_END = VERB_START + len("praised")

ROLES = [
    ActionRole(
        lemma="praise",
        hole_role="SubjectHole",
        requirement="HasSort Person",
        strength="HardRequirement",
        provenance="test",
        identity="test:praise:subject",
    ),
    ActionRole(
        lemma="praise",
        hole_role="ObjectHole",
        requirement="HasSort Person",
        strength="HardRequirement",
        provenance="test",
        identity="test:praise:object",
    ),
]


class ResolveActionDependencyHintTests(unittest.TestCase):
    def test_legacy_offset_heuristic_gets_this_sentence_wrong(self) -> None:
        result = resolve_action(SENTENCE, ["Tolstoy"], ROLES, {})
        self.assertEqual(result["role"], "SubjectHole")

    def test_direct_argument_hint_overrides_position_with_the_correct_role(
        self,
    ) -> None:
        hint = {
            "dep_status": "direct-argument",
            "hole_role": "Object",
            "governing_lemma": "praise",
            "governing_start": VERB_START,
            "governing_end": VERB_END,
        }
        result = resolve_action(
            SENTENCE, ["Tolstoy"], ROLES, {}, dependency_hint=hint
        )
        self.assertEqual(result["role"], "ObjectHole")
        self.assertEqual(result["surface"], "praised")
        self.assertEqual(result["start"], VERB_START)
        self.assertEqual(result["end"], VERB_END)

    def test_nested_modifier_hint_raises_regardless_of_other_fields(self) -> None:
        hint = {
            "dep_status": "nested-modifier",
            "hole_role": "Subject",
            "governing_lemma": "praise",
            "governing_start": VERB_START,
            "governing_end": VERB_END,
        }
        with self.assertRaisesRegex(ValueError, "nested-modifier-unsupported"):
            resolve_action(SENTENCE, ["Tolstoy"], ROLES, {}, dependency_hint=hint)

    def test_dependency_hint_none_matches_no_hint_argument_at_all(self) -> None:
        without_argument = resolve_action(SENTENCE, ["Tolstoy"], ROLES, {})
        with_none = resolve_action(
            SENTENCE, ["Tolstoy"], ROLES, {}, dependency_hint=None
        )
        self.assertEqual(without_argument, with_none)

    def test_no_governing_verb_status_degrades_to_legacy_behaviour(self) -> None:
        hint = {
            "dep_status": "no-governing-verb",
            "hole_role": None,
            "governing_lemma": None,
            "governing_start": None,
            "governing_end": None,
        }
        legacy = resolve_action(SENTENCE, ["Tolstoy"], ROLES, {})
        hinted = resolve_action(
            SENTENCE, ["Tolstoy"], ROLES, {}, dependency_hint=hint
        )
        self.assertEqual(legacy, hinted)

    def test_parse_error_status_degrades_to_legacy_behaviour(self) -> None:
        hint = {
            "dep_status": "parse-error",
            "hole_role": None,
            "governing_lemma": None,
            "governing_start": None,
            "governing_end": None,
        }
        legacy = resolve_action(SENTENCE, ["Tolstoy"], ROLES, {})
        hinted = resolve_action(
            SENTENCE, ["Tolstoy"], ROLES, {}, dependency_hint=hint
        )
        self.assertEqual(legacy, hinted)

    def test_direct_argument_without_governing_span_degrades_to_legacy(
        self,
    ) -> None:
        hint = {
            "dep_status": "direct-argument",
            "hole_role": "Object",
            "governing_lemma": "praise",
            "governing_start": None,
            "governing_end": None,
        }
        legacy = resolve_action(SENTENCE, ["Tolstoy"], ROLES, {})
        hinted = resolve_action(
            SENTENCE, ["Tolstoy"], ROLES, {}, dependency_hint=hint
        )
        self.assertEqual(legacy, hinted)


class _FakeToken:
    def __init__(self, start_char: int, end_char: int) -> None:
        self.start_char = start_char
        self.end_char = end_char


class _FakeWord:
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
        self.parent = _FakeToken(start_char, end_char)


class _FakeSentence:
    def __init__(self, words: list[_FakeWord]) -> None:
        self.words = words


class DependencyHintIntegrationTests(unittest.TestCase):
    def test_a_real_classify_word_output_actually_drives_resolve_action(self) -> None:
        # Same fronted-object sentence, but this time the hint comes from
        # a real classify_word() call rather than a hand-typed dict --
        # hole_role is spelled "Object" here (annotate_dependency_hints.py's
        # own convention), not ActionRole's internal "ObjectHole". A
        # hand-typed hint using the wrong spelling would not have caught
        # the "+Hole"-suffix mismatch this module once shipped with.
        words = [
            _FakeWord(1, "Tolstoy", "Tolstoy", "PROPN", "obj", 4, 0, 7),
            _FakeWord(2, "the", "the", "DET", "det", 3, 9, 12),
            _FakeWord(3, "critics", "critic", "NOUN", "nsubj", 4, 13, 20),
            _FakeWord(4, "praised", "praise", "VERB", "root", 0, VERB_START, VERB_END),
            _FakeWord(5, "generously", "generously", "ADV", "advmod", 4, 29, 39),
        ]
        sentence = _FakeSentence(words)
        dep_status, hole_role, governing_lemma, g_start, g_end, voice = classify_word(
            sentence, words[0]
        )
        self.assertEqual(hole_role, "Object")  # sanity check on the fixture itself
        hint = {
            "dep_status": dep_status,
            "hole_role": hole_role,
            "governing_lemma": governing_lemma,
            "governing_start": g_start,
            "governing_end": g_end,
            "voice": voice,
        }
        result = resolve_action(SENTENCE, ["Tolstoy"], ROLES, {}, dependency_hint=hint)
        self.assertEqual(result["role"], "ObjectHole")


if __name__ == "__main__":
    unittest.main()
