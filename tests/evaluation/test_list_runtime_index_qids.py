from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from list_runtime_index_qids import list_qids, main  # noqa: E402


def build_index(database: Path, qids: list[str]) -> None:
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE entities (qid TEXT PRIMARY KEY, label TEXT NOT NULL)")
    connection.executemany(
        "INSERT INTO entities VALUES (?, ?)", [(qid, qid) for qid in qids]
    )
    connection.commit()
    connection.close()


class ListQidsTests(unittest.TestCase):
    def test_returns_every_qid_sorted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "index.sqlite"
            build_index(database, ["Q649", "Q2", "Q1049470"])
            self.assertEqual(list_qids(database), ["Q1049470", "Q2", "Q649"])

    def test_empty_index_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "index.sqlite"
            build_index(database, [])
            self.assertEqual(list_qids(database), [])


class MainCliTests(unittest.TestCase):
    def test_writes_one_qid_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "index.sqlite"
            build_index(database, ["Q649", "Q2"])
            output = Path(directory) / "qids.txt"
            sys.argv = [
                "list_runtime_index_qids.py",
                "--database",
                str(database),
                "--output",
                str(output),
            ]
            main()
            self.assertEqual(output.read_text(encoding="utf-8"), "Q2\nQ649\n")


if __name__ == "__main__":
    unittest.main()
