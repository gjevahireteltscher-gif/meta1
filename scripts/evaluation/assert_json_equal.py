#!/usr/bin/env python3
"""Compare two JSON files for exact equality, printing a readable diff on
mismatch instead of a bare AssertionError. Used by the Makefile targets that
check a freshly computed report against its committed golden summary."""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("actual", type=Path)
    parser.add_argument("expected", type=Path)
    arguments = parser.parse_args()

    actual = json.loads(arguments.actual.read_text(encoding="utf-8"))
    expected = json.loads(arguments.expected.read_text(encoding="utf-8"))
    if actual == expected:
        return

    actual_text = json.dumps(actual, indent=2, sort_keys=True).splitlines(
        keepends=True
    )
    expected_text = json.dumps(expected, indent=2, sort_keys=True).splitlines(
        keepends=True
    )
    diff = difflib.unified_diff(
        expected_text,
        actual_text,
        fromfile=str(arguments.expected),
        tofile=str(arguments.actual),
    )
    sys.stderr.writelines(diff)
    raise SystemExit(
        f"{arguments.actual} does not match {arguments.expected} (see diff above)"
    )


if __name__ == "__main__":
    main()
