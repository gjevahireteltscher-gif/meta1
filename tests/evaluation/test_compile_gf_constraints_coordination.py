"""compile_gf_constraints must safely traverse trees built with the new
grammar/Metonymy.gf constructors added to unblock the dominant
gf-parse-empty bottleneck (see docs/contextual-tower.md's "Source-mention
disambiguation" section and this session's history): AndS/OrS (sentence
coordination), AndNP/OrNP (NP coordination), and PrepPP (an
arbitrary-preposition PP, instead of the four hardcoded InPP/AboutPP/
WithPP/ForPP). Metonymy.gf's abstract syntax previously had exactly one
clause-level category with no cross-sentence or coordination structure at
all, so real corpus sentences using "and"/"or" or any preposition outside
those four could never produce a GF tree in the first place.

These are pure Python tests against hand-built GF tree strings -- they do
not require a compiled grammar. They exercise the tree-walker's contract
("if the compiler ever produces a tree shaped like this, does the Python
side handle it"), not whether MetonymyEng.gf's new rules actually compile
or parse real English (that needs the GF toolchain, verified only in
CI/.cursor).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from contextual_rule_compiler import ARITIES, compile_gf_constraints  # noqa: E402

WORDNET_RULES = {
    "lexical_sorts": {
        "general": {"requirement": "HasSort Military", "provenance": "test:wordnet"}
    },
    "adjective_sorts": {},
}

LANGUAGE_RULES = {
    "schema_version": "test-1",
    "frame_argument_capabilities": [],
}


def base_proposal(sentence: str, action: str = "capture") -> dict:
    return {
        "action": action,
        "sentence": sentence,
        "frames": [],
        "provenance": {"action": "test:VerbNet:" + action},
        "constraints": [
            {
                "origin": {
                    "constructor": "Verb",
                    "lemma": action,
                    "surface": "captured",
                    "start": 0,
                    "end": 8,
                },
                "payload": {"requires": "HasSort Place"},
                "provenance": "test:VerbNet:" + action,
            }
        ],
    }


class NewConstructorArityTests(unittest.TestCase):
    def test_and_s_or_s_take_two_sentences(self) -> None:
        self.assertEqual(ARITIES["AndS"], 2)
        self.assertEqual(ARITIES["OrS"], 2)

    def test_and_np_or_np_take_two_noun_phrases(self) -> None:
        self.assertEqual(ARITIES["AndNP"], 2)
        self.assertEqual(ARITIES["OrNP"], 2)

    def test_prep_pp_takes_a_preposition_and_a_noun_phrase(self) -> None:
        self.assertEqual(ARITIES["PrepPP"], 2)


class CompileGfConstraintsCoordinationTests(unittest.TestCase):
    def test_finds_a_compl_node_nested_inside_and_s(self) -> None:
        # "Waterloo captured a general and signed a treaty" -- first_node
        # must recurse into AndS's own arguments to find the first Compl,
        # exactly as it already does for any other wrapping constructor.
        proposal = base_proposal("Waterloo captured a general and signed a treaty")
        proposal["role"] = "SubjectHole"
        constraints = compile_gf_constraints(
            proposal,
            'AndS '
            '(Pred (OpenPN "Waterloo") '
            '(Compl Capture (OpenIndefCN "general" "generals"))) '
            '(Pred (OpenPN "Waterloo") '
            '(Compl Capture (OpenIndefCN "treaty" "treaties")))',
            LANGUAGE_RULES,
            WORDNET_RULES,
            {},
        )
        self.assertEqual(len(constraints), 1)
        self.assertEqual(constraints[0]["origin"]["constructor"], "FrameArgument")

    def test_a_coordinated_object_np_is_a_safe_no_op(self) -> None:
        # "Waterloo captured a general and an admiral" -- the object is
        # an AndNP, not a shape _noun_lemma/gf_nouns knows how to resolve
        # a lemma from. Must not crash; produces no constraint, the same
        # safe-degradation behavior already relied on for a bare proper
        # noun object.
        proposal = base_proposal("Waterloo captured a general and an admiral")
        proposal["role"] = "SubjectHole"
        constraints = compile_gf_constraints(
            proposal,
            'Pred (OpenPN "Waterloo") '
            '(Compl Capture '
            '(AndNP (OpenIndefCN "general" "generals") '
            '(OpenIndefCN "admiral" "admirals")))',
            LANGUAGE_RULES,
            WORDNET_RULES,
            {},
        )
        self.assertEqual(constraints, [])

    def test_or_np_subject_does_not_crash_the_walker(self) -> None:
        proposal = base_proposal("Waterloo or Napoleon captured a general")
        proposal["role"] = "SubjectHole"
        constraints = compile_gf_constraints(
            proposal,
            'Pred (OrNP (OpenPN "Waterloo") (OpenPN "Napoleon")) '
            '(Compl Capture (OpenIndefCN "general" "generals"))',
            LANGUAGE_RULES,
            WORDNET_RULES,
            {},
        )
        self.assertEqual(len(constraints), 1)

    def test_a_prep_pp_modifier_does_not_crash_the_walker(self) -> None:
        # PrepPP is deliberately not in compile_gf_constraints' fixed
        # InPP/AboutPP/WithPP/ForPP table (see the comment at its call
        # site) -- it should still be walked safely and simply not
        # contribute an extra FrameModifier constraint from this specific
        # modifier, while the Compl-derived constraint is unaffected.
        proposal = base_proposal("Waterloo captured a general near Brussels")
        proposal["role"] = "SubjectHole"
        constraints = compile_gf_constraints(
            proposal,
            'Pred (OpenPN "Waterloo") '
            '(Compl Capture (ModifyNP '
            '(OpenIndefCN "general" "generals") '
            '(PrepPP "near" (OpenPN "Brussels"))))',
            LANGUAGE_RULES,
            WORDNET_RULES,
            {},
        )
        self.assertEqual(len(constraints), 1)
        self.assertEqual(constraints[0]["origin"]["constructor"], "FrameArgument")


if __name__ == "__main__":
    unittest.main()
