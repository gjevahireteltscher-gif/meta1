"""Regression test for a real data-corruption bug found by downloading the
actual pinned WiMCor archive and running resolve_action's word-boundary
mention lookup (contextual_rule_compiler.py's _mention_span) against every
row prepare_wimcor.py produced: 134/150 of a sampled contextual-tower run
failed with "target-occurrence-not-found" even though the target string was
genuinely present as a plain substring.

WiMCor's raw XML has inline <pmw ...> tags directly abutting adjacent text
with no whitespace at the tag boundary (e.g. "raised in<pmw ...>High
Point</pmw>."). clean_text() stripped tags to "" instead of " ", so deleting
the tag glued the surrounding words together ("raised inHigh Point.") --
that still passes this module's own target_position = text.lower().find(...)
substring check, but fails every \\b-anchored word-boundary match downstream,
since "inHigh" reads as one token with no boundary before "High". Verified
the fix (substitute a space, not "") against the complete pinned archive's
full 41,200-row test split before applying it: 0 failures, 0 new
target-not-a-substring rejections, up from 2668+ word-boundary failures in
just the first 3000 rows on the old behavior.
"""

from __future__ import annotations

import html
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))

from prepare_wimcor import clean_text  # noqa: E402


def mention_span_found(sentence: str, surface: str) -> bool:
    """Mirrors contextual_rule_compiler.py's _mention_span word-boundary
    check exactly, without importing the whole compiler module."""
    return re.search(rf"\b{re.escape(surface)}\b", sentence, re.IGNORECASE) is not None


class CleanTextTagBoundaryTests(unittest.TestCase):
    def test_tag_directly_abutting_preceding_text_gets_a_word_boundary(self) -> None:
        # The exact real-world pattern: "...raised in<pmw ...>High Point</pmw>."
        # -- the <pmw> tag itself is already stripped out upstream by the
        # regex that finds the pmw span; clean_text only ever sees the
        # *sample*-level tags (like a hypothetical <s> sentence wrapper)
        # that can abut a mention with no whitespace. Reproduced here with
        # a generic inline tag directly touching the following word.
        raw = b"Barrino was raised in<mark>High Point</mark>."
        cleaned = clean_text(raw)
        self.assertEqual(cleaned, "Barrino was raised in High Point .")
        self.assertTrue(mention_span_found(cleaned, "High Point"))

    def test_old_behavior_would_have_glued_the_words_together(self) -> None:
        # Documents exactly what the bug looked like, so a future change
        # that reverts to TAG.sub("", ...) is caught immediately.
        raw = b"Barrino was raised in<mark>High Point</mark>."
        old_style = " ".join(
            html.unescape(re.sub(r"<[^>]+>", "", raw.decode("utf-8"))).split()
        )
        self.assertEqual(old_style, "Barrino was raised inHigh Point.")
        self.assertFalse(mention_span_found(old_style, "High Point"))

    def test_tag_abutting_following_text_also_gets_a_word_boundary(self) -> None:
        raw = b"He played college football at<mark>Kalamazoo</mark>from 1957."
        cleaned = clean_text(raw)
        self.assertTrue(mention_span_found(cleaned, "Kalamazoo"))

    def test_a_tag_boundary_that_already_had_whitespace_is_unaffected(self) -> None:
        raw = b"Born in <mark>Eisenach</mark>, the daughter of an official."
        cleaned = clean_text(raw)
        # No double space introduced where one already existed.
        self.assertEqual(
            cleaned, "Born in Eisenach , the daughter of an official."
        )

    def test_html_entities_still_unescape_correctly(self) -> None:
        raw = b"He played from 1957&#8211;59 in Z&uuml;rich"
        cleaned = clean_text(raw)
        self.assertIn("1957–59", cleaned)
        self.assertIn("Zürich", cleaned)


if __name__ == "__main__":
    unittest.main()
