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
from contextlib import redirect_stderr, redirect_stdout
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

    def test_zero_candidates_is_still_source_qid_unresolved(self) -> None:
        # The pre-existing "no candidate resolved at all" case (formerly
        # len(candidates) != 1, now len(candidates) == 0) must still exit 2
        # with the same status string, unaffected by the new multi-
        # candidate disambiguation loop below.
        ready_proposal = json.dumps(
            {
                "status": "ready",
                "source_surface": "Southern Cal",
                "source_qid_candidates": [],
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
            "Southern Cal confabulates a treaty",
            "--source",
            "Southern Cal",
        ]
        stdout = io.StringIO()
        with patch("subprocess.run", return_value=completed):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as raised:
                    run_automatic_contextual_pipeline.main()
        self.assertEqual(raised.exception.code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "source-qid-unresolved")

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


def propose_proposal(candidates: list[str]) -> subprocess.CompletedProcess:
    payload = {
        "status": "ready",
        "gf_sentence": "Liverpool announced a new programme",
        "action": "announce",
        "role": "SubjectHole",
        "max_depth": 1,
        "bridge_relations": ["InstitutionOf"],
        "constraints": [],
        "source_qid_candidates": candidates,
        "source_surface": "Liverpool",
    }
    return subprocess.CompletedProcess(
        args=["python3", "scripts/propose_contextual_scenario.py"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )


def gf_parse_result() -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["build/metonymy", "parse", "Liverpool announced a new programme"],
        returncode=0,
        # A single 0-arity, unparenthesized token is already a complete,
        # parseable GF tree (contextual_rule_compiler.parse_gf_tree) --
        # --ablation no-wordnet (used throughout this test class) makes
        # compile_gf_constraints return immediately after parsing it, so
        # its actual shape past being parseable is never inspected.
        stdout="DummyTree\n",
        stderr="",
    )


def engine_trace(final_survivors: list[str]) -> str:
    return "\n".join(
        [
            "graph_sha256=deadbeef",
            "source=Q0 action=announce role=SubjectHole",
            "stage=0 constraint=graph-related",
            "  survivors=[Q0]",
            "  agda-layer-check=true",
            "stage=1 constraint=Requires (HasSort Organization)@announce",
            "  survivors=[" + ",".join(final_survivors) + "]",
            "  agda-layer-check=true",
        ]
    ) + "\n"


def engine_result(
    returncode: int, stdout: str, stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["build/metonymy", "contextual-fiber", "..."],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def make_fake_run(candidates: list[str], engine_results_by_qid: dict):
    def fake_run(command, **kwargs):
        if command[0] == "python3":
            return propose_proposal(candidates)
        if command[1] == "parse":
            return gf_parse_result()
        # A per-candidate engine invocation: [engine, "contextual-fiber",
        # scenario_name, "--snapshot", ..., "--scenarios", ...] where
        # scenario_name is f"{qid.lower()}-{action}" (see run_engine in
        # run_automatic_contextual_pipeline.py).
        scenario_name = command[2]
        qid = scenario_name.split("-", 1)[0].upper()
        return engine_results_by_qid[qid]

    return fake_run


class SourceDisambiguationTests(unittest.TestCase):
    """The candidate list this class exercises is exactly the "Liverpool"
    situation found by locally reproducing the real contextual-tower-
    evaluation.yml sample: many exact-alias Wikidata matches for one
    surface, only some of which bridge to anything satisfying the
    sentence's own constraints once the tower's existing per-layer
    narrowing actually runs against each of them.
    """

    def _run_main(self, candidates: list[str], engine_results_by_qid: dict) -> tuple[str, int]:
        sys.argv = [
            "run_automatic_contextual_pipeline.py",
            "--engine",
            "build/metonymy",
            "--snapshot",
            "data/wikidata-openalex-snapshot",
            "--sentence",
            "Liverpool announced a new programme",
            "--source",
            "Liverpool",
            "--ablation",
            "no-wordnet",
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("subprocess.run", side_effect=make_fake_run(candidates, engine_results_by_qid)):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as raised:
                    run_automatic_contextual_pipeline.main()
        return stdout.getvalue() + stderr.getvalue(), raised.exception.code

    def test_exactly_one_surviving_candidate_is_the_answer(self) -> None:
        printed, code = self._run_main(
            ["Q24826", "Q2252369"],
            {
                "Q24826": engine_result(0, engine_trace(["Q145"])),
                "Q2252369": engine_result(0, engine_trace([])),
            },
        )
        self.assertEqual(code, 0)
        self.assertIn("survivors=[Q145]", printed)

    def test_zero_surviving_candidates_is_a_literal_prediction_not_a_failure(
        self,
    ) -> None:
        printed, code = self._run_main(
            ["Q24826", "Q2252369"],
            {
                "Q24826": engine_result(0, engine_trace([])),
                "Q2252369": engine_result(0, engine_trace([])),
            },
        )
        self.assertEqual(code, 0)
        self.assertIn("survivors=[]", printed)

    def test_two_surviving_candidates_is_reported_as_ambiguous_not_guessed(
        self,
    ) -> None:
        printed, code = self._run_main(
            ["Q24826", "Q1189030"],
            {
                "Q24826": engine_result(0, engine_trace(["Q145"])),
                "Q1189030": engine_result(0, engine_trace(["Q999"])),
            },
        )
        self.assertEqual(code, 6)
        # printed also carries the earlier "gf-tree=..." progress line
        # (main() prints it before the candidate loop runs); the ambiguity
        # report is the JSON object after it.
        payload = json.loads(printed[printed.index("{") :])
        self.assertEqual(payload["status"], "source-disambiguation-ambiguous")
        self.assertEqual(
            payload["confirmed_source_qid_candidates"], ["Q1189030", "Q24826"]
        )

    def test_a_genuine_engine_rejection_among_zero_survivors_still_surfaces(
        self,
    ) -> None:
        # If every candidate's own engine run failed outright (not just an
        # empty fiber), that is a real error and must not be silently
        # treated as a clean "no metonymic reading" result. The engine's
        # own `die` (engine/app/Main.hs) writes to stderr, not stdout.
        printed, code = self._run_main(
            ["Q24826"],
            {
                "Q24826": engine_result(
                    1, "", "contextual fiber failed: bad snapshot\n"
                )
            },
        )
        self.assertEqual(code, 1)
        self.assertIn("bad snapshot", printed)

    def test_contract_target_keeps_requiring_exactly_one_candidate(self) -> None:
        sys.argv = [
            "run_automatic_contextual_pipeline.py",
            "--engine",
            "build/metonymy",
            "--snapshot",
            "data/wikidata-openalex-snapshot",
            "--sentence",
            "The university announced a new programme",
            "--source",
            "Liverpool",
            "--contract-target",
            "the university",
        ]
        stdout = io.StringIO()
        with patch(
            "subprocess.run",
            return_value=propose_proposal(["Q24826", "Q2252369"]),
        ):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as raised:
                    run_automatic_contextual_pipeline.main()
        self.assertEqual(raised.exception.code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "source-qid-unresolved")


class GfParseEmptyTests(unittest.TestCase):
    """Regression test for a real bug found via a real
    contextual-tower-evaluation.yml run: the "no lexicalized trees"
    branch used a bare `raise SystemExit("some string")`, which prints
    that string and exits 1 without the JSON-"status" convention every
    sibling failure in this function follows. That made it invisible to
    score_contextual_detection.py's exit-1 token search -- two full CI
    rounds of guessing new KNOWN_FAILURE_TOKENS/GENERIC_RUNTIME_CRASH_TOKENS
    entries found nothing, because the actual message was never among
    them, until fingerprint_failure_text's safe hashing (no content, just
    a SHA-256 prefix and a length) matched a locally-reproduced
    fingerprint of this exact 32-character string. Fixed by giving it its
    own exit code (7), JSON-wrapped like gf-parse-failed/
    semantic-composition-failed/contract-target-qid-unresolved.
    """

    def test_gf_parse_producing_no_trees_gets_its_own_exit_code(self) -> None:
        sys.argv = [
            "run_automatic_contextual_pipeline.py",
            "--engine",
            "build/metonymy",
            "--snapshot",
            "data/wikidata-openalex-snapshot",
            "--sentence",
            "Liverpool announced a new programme",
            "--source",
            "Liverpool",
        ]

        def fake_run(command, **kwargs):
            if command[0] == "python3":
                return propose_proposal(["Q24826"])
            if command[1] == "parse":
                return subprocess.CompletedProcess(
                    args=command, returncode=0, stdout="", stderr=""
                )
            raise AssertionError(f"unexpected command: {command}")

        stdout = io.StringIO()
        with patch("subprocess.run", side_effect=fake_run):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as raised:
                    run_automatic_contextual_pipeline.main()
        self.assertEqual(raised.exception.code, 7)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "gf-parse-empty")

    def test_a_parser_failed_message_also_counts_as_no_trees(self) -> None:
        sys.argv = [
            "run_automatic_contextual_pipeline.py",
            "--engine",
            "build/metonymy",
            "--snapshot",
            "data/wikidata-openalex-snapshot",
            "--sentence",
            "Liverpool announced a new programme",
            "--source",
            "Liverpool",
        ]

        def fake_run(command, **kwargs):
            if command[0] == "python3":
                return propose_proposal(["Q24826"])
            if command[1] == "parse":
                return subprocess.CompletedProcess(
                    args=command,
                    returncode=0,
                    stdout="The parser failed at token 3\n",
                    stderr="",
                )
            raise AssertionError(f"unexpected command: {command}")

        stdout = io.StringIO()
        with patch("subprocess.run", side_effect=fake_run):
            with redirect_stdout(stdout):
                with self.assertRaises(SystemExit) as raised:
                    run_automatic_contextual_pipeline.main()
        self.assertEqual(raised.exception.code, 7)


if __name__ == "__main__":
    unittest.main()
