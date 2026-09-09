"""Decisive, non-corpus diagnostic for what actually blocks GF parsing.

Three consecutive contextual-tower-evaluation.yml runs against verified,
CI-compiled grammar additions (S-coordination+8 prepositions, then VP
coordination, then copula+generalized-relative-clauses+genitive) measured
*zero* effect on the real corpus sample -- byte-identical
literal_prediction_reasons every time. Guessing another construction to
add without direct evidence would just be a fourth blind round. This
file exists to stop guessing: every sentence below is *our own*, written
for this test, never corpus text -- so, unlike anything drawn from
WiMCor/ConMeC, it is safe to print in full in a CI log or a test failure
message. Each test isolates exactly one hypothesis and prints a plain
PASS/FAIL verdict, so a single failing test name in the CI log is
decisive, the same way `test_wordnet_cn_relative_clause_parses_in_gf`
was decisive for the which_RP collision -- no corpus-derived guessing
required.

Leading hypothesis this batch is built to confirm or refute: `OpenPN :
String -> NP` is the only way this grammar represents a proper noun, and
every *proven*-working example sentence anywhere in this project's tests
so far ("Waterloo announces...", "Moscow signs...", "Anna examines...")
uses a single-word subject. Most real WiMCor/ConMeC source mentions are
multi-word ("Henry County", "The Shipley School", "Vilas County"). If
GF's String-category parsing cannot cleanly span multiple tokens for an
OpenPN slot in this grammar, no amount of additional sentence-level
grammar (coordination, copula, relative clauses, genitive -- all already
added and all measuring zero effect) can matter, because the subject NP
itself never parses in the first place.

**Verb tense correction from this file's own first CI run**: every
sentence below uses present tense, third person singular
("announces"/"is", never "announced"/"was"). The first version of this
file used past tense and every single test failed, including the
single-word baseline -- not evidence the grammar is broken, but a bug in
the test itself: `contextual_rule_compiler.py`'s `resolve_action` always
substitutes the active (non-passive) verb with `third_person(lemma)`
regardless of the original sentence's own tense, so present tense,
third-person-singular is the *only* active-Compl surface form the real
pipeline (and therefore this grammar's tense-unspecified default `mkS :
Cl -> S`) actually ever asks GF to parse -- confirmed directly from
`resolve_action`'s source, not guessed. Every prior "proven working"
example sentence cited above went through that same substitution before
reaching GF, so it was never literally parsed in the past-tense surface
form its own `--sentence` argument displayed either.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class GfParseDiagnosticMatrix(unittest.TestCase):
    engine: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = ROOT / "build" / "metonymy"
        if not cls.engine.exists():
            raise unittest.SkipTest("build/metonymy is not built")

    def parse(self, sentence: str) -> str:
        completed = subprocess.run(
            [str(self.engine), "parse", sentence],
            check=True,
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        return completed.stdout

    def assert_parses(self, sentence: str) -> str:
        output = self.parse(sentence)
        if output.startswith("The parser failed"):
            self.fail(
                f"expected a successful parse of {sentence!r}, "
                f"got: {output.strip()!r}"
            )
        return output

    def assert_fails(self, sentence: str) -> str:
        output = self.parse(sentence)
        self.assertTrue(
            output.startswith("The parser failed"),
            f"expected {sentence!r} to fail to parse (documenting a known "
            f"gap), but it parsed as: {output.strip()!r} -- if this is a "
            f"deliberate improvement, update this test's expectation, "
            f"don't just note the surprise",
        )
        return output

    # -- Baseline: known-working shape, single-word subject and object.
    # Present tense, third person singular ("announces", not "announced")
    # -- confirmed from contextual_rule_compiler.py's own resolve_action:
    # the active (non-passive) gf_form always defaults to
    # third_person(lemma), regardless of the original sentence's own
    # tense, so this is the *only* surface verb form the pipeline (and
    # therefore this grammar's default, tense-unspecified `mkS : Cl ->
    # S`) ever actually asks GF to parse for an active Compl. --

    def test_baseline_single_word_subject_and_object_parses(self) -> None:
        self.assert_parses("Waterloo announces a programme")

    # -- The core hypothesis: multi-word OpenPN --

    def test_two_word_proper_noun_subject(self) -> None:
        """"Henry County" as a subject -- the single most common real
        source-mention shape (place names, institution names) this
        project's live-API-snapshot corpus sample actually contains."""
        self.assert_parses("Henry County announces a programme")

    def test_two_word_proper_noun_object(self) -> None:
        """Same question, object position instead of subject, in case
        OpenPN's token-span behavior differs by grammatical position."""
        self.assert_parses("Waterloo announces Henry County")

    def test_three_word_proper_noun_subject(self) -> None:
        """A longer multi-word name ("Shipley School" is two words on
        its own; kept to two here to isolate word-count from any
        confound with a leading article-like word, which OpenDefCN/
        OpenIndefCN's own literal "the"/"a" prefixes could otherwise
        interact with)."""
        self.assert_parses("Shipley School announces a programme")

    # -- Combined with the newest additions, to see whether multi-word
    # subjects specifically break the *newest* constructions even if they
    # already work with the older Compl-only shape above. --

    def test_copula_with_single_word_subject(self) -> None:
        self.assert_parses("Waterloo is a programme")

    def test_copula_with_two_word_subject(self) -> None:
        self.assert_parses("Henry County is a programme")


if __name__ == "__main__":
    unittest.main()
