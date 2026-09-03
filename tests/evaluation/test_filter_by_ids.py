from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))

from filter_by_ids import filter_jsonl  # noqa: E402


class FilterJsonlTests(unittest.TestCase):
    def test_keeps_only_rows_with_a_matching_id(self) -> None:
        rows = [{"id": "a", "x": 1}, {"id": "b", "x": 2}, {"id": "c", "x": 3}]
        self.assertEqual(
            filter_jsonl(rows, {"a", "c"}), [{"id": "a", "x": 1}, {"id": "c", "x": 3}]
        )

    def test_empty_id_set_keeps_nothing(self) -> None:
        rows = [{"id": "a"}, {"id": "b"}]
        self.assertEqual(filter_jsonl(rows, set()), [])

    def test_rows_without_an_id_are_never_kept(self) -> None:
        rows = [{"not_id": "a"}]
        self.assertEqual(filter_jsonl(rows, {"a"}), [])


if __name__ == "__main__":
    unittest.main()
