"""Regression test for a real bug found via a live CI run: subprocess.run(...,
check=True) on the propose_contextual_scenario.py call silently discarded the
child's captured stdout/stderr when it failed. An uncaught CalledProcessError's
default traceback only prints "Command '...' returned non-zero exit status N"
-- never the child's own short, sentence-free error message (resolve_action's
target-occurrence-not-found/unsupported-action-role/nested-modifier-unsupported,
raised via `raise SystemExit(str(error))` and printed to *its own* stderr,
which capture_output=True redirects into an attribute nothing ever read).

This made every one of a real run's failures show up as
"failed:exit1:unrecognized" in score_contextual_detection.py's diagnostic --
technically correct (no sentence text leaked) but useless for telling apart
target-occurrence-not-found from unsupported-action-role from
nested-modifier-unsupported, exactly the distinction that diagnostic exists
to make. Fixed by checking the return code explicitly and printing the
child's combined output as a "detail" field, matching the same JSON-error
convention this script already uses for gf-parse-failed and
semantic-composition-failed.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_automatic_contextual_pipeline  # noqa: E402


def failing_propose(returncode: int, stderr: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["python3", "scripts/propose_contextual_scenario.py"],
        returncode=returncode,
        stdout="",
        stderr=stderr,
    )


class ProposeScenarioFailureSurfacingTests(unittest.TestCase):
    def _run_main_with(self, completed: subprocess.CompletedProcess) -> str:
        sys.argv = [
            "run_automatic_contextual_pipeline.py",
            "--engine",
            "build/metonymy",
            "--snapshot",
            "data/wikidata-openalex-snapshot",
            "--sentence",
            "Waterloo confabulates a treaty",
            "--source",
            "Waterloo",
        ]
        stdout = io.StringIO()
        with patch("subprocess.run", return_value=completed):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as raised:
                    run_automatic_contextual_pipeline.main()
        self.assertEqual(raised.exception.code, 1)
        return stdout.getvalue()

    def test_the_childs_actual_error_message_is_surfaced_not_swallowed(self) -> None:
        printed = self._run_main_with(
            failing_propose(1, "unsupported-action-role\n")
        )
        payload = json.loads(printed)
        self.assertEqual(payload["status"], "propose-scenario-failed")
        self.assertIn("unsupported-action-role", payload["detail"])

    def test_distinguishes_each_known_resolve_action_error(self) -> None:
        for token in (
            "target-occurrence-not-found",
            "unsupported-action-role",
            "nested-modifier-unsupported",
        ):
            with self.subTest(token=token):
                printed = self._run_main_with(failing_propose(1, token + "\n"))
                payload = json.loads(printed)
                self.assertIn(token, payload["detail"])

    def test_successful_propose_is_unaffected(self) -> None:
        # A returncode of 0 must still flow into the normal ready/not-ready
        # handling below, not the new failure branch.
        ready_proposal = json.dumps(
            {
                "status": "source-qid-unresolved",
                "source_surface": "Waterloo",
            }
        )
        completed = subprocess.CompletedProcess(
            args=["python3", "scripts/propose_contextual_scenario.py"],
            returncode=0,
            stdout=ready_proposal,
            stderr="",
        )
        sys.argv = [
            "run_automatic_contextual_pipeline.py",
            "--engine",
            "build/metonymy",
            "--snapshot",
            "data/wikidata-openalex-snapshot",
            "--sentence",
            "Waterloo confabulates a treaty",
            "--source",
            "Waterloo",
        ]
        stdout = io.StringIO()
        with patch("subprocess.run", return_value=completed):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as raised:
                    run_automatic_contextual_pipeline.main()
        # The *old* status-not-ready path (exit 2), not the new exit-1
        # propose-scenario-failed path.
        self.assertEqual(raised.exception.code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "source-qid-unresolved")


if __name__ == "__main__":
    unittest.main()
