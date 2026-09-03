"""Integration tests for `metonymy open-batch --evidence`, run against the
built engine binary (build/metonymy). Unlike the rest of tests/evaluation,
which deliberately never invoke the Haskell engine (see evaluation/README.md),
this specifically needs to: the code under test (Main.hs's
resolveOpenDecision, and its "no-context withholds evidence" branch) lives
in the app executable, not in a library module engine/test/Main.hs can
import, so it can only be exercised by actually running the compiled
binary. Skips entirely if build/metonymy has not been built (e.g. on a
machine with no Haskell toolchain) rather than failing.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "build" / "metonymy"

# Known, already-verified fixture: engine/test/Main.hs asserts that this
# exact sentence/target/span produces an OpenRewrite whose predicate is a
# checked SelectionalPreference (verifyPreferenceRuntimeWithAgda), i.e. it
# abstains with reason "selectional-preference:..." under the "full"
# ablation with no evidence supplied.
ROW = (
    "waterloo-programme\twimcor\tLOCATION\tWaterloo\t0\t8\t"
    "Waterloo announced a new research programme"
)


def run_open_batch(
    row: str, ablation: str = "full", evidence: Path | None = None
) -> tuple[str, str, str, str, str]:
    command = [str(ENGINE), "open-batch", ablation]
    if evidence is not None:
        command += ["--evidence", str(evidence)]
    process = subprocess.run(
        command,
        input=row + "\n",
        text=True,
        capture_output=True,
        cwd=ROOT,
        check=True,
    )
    lines = process.stdout.splitlines()
    assert len(lines) == 1, f"expected exactly one output row, got: {lines!r}"
    identifier, status, prediction, family, detail = lines[0].split("\t", 4)
    return identifier, status, prediction, family, detail


def write_evidence(directory: str, target_entity_id: str, source: str) -> Path:
    path = Path(directory) / "evidence.tsv"
    path.write_text(
        "id\ttarget_entity_id\tsource\n"
        f"waterloo-programme\t{target_entity_id}\t{source}\n",
        encoding="utf-8",
    )
    return path


@unittest.skipUnless(ENGINE.exists(), "requires a built engine (build/metonymy)")
class OpenBatchPromotionTests(unittest.TestCase):
    def test_selectional_preference_abstains_without_evidence(self) -> None:
        _, status, _, _, detail = run_open_batch(ROW)
        self.assertEqual(status, "abstain")
        self.assertTrue(detail.startswith("selectional-preference:"))
        # the raw target EntityId is appended as a trailing tab-separated
        # part of detail (engine/app/Main.hs's renderOpenBatchRow) --
        # required so evidence can reference the exact candidate target,
        # since candidateSurface is a human label, not the EntityId string
        # Agda's checkPromotion compares evidence against.
        self.assertIn("\t", detail)

    def test_matching_evidence_promotes_the_same_candidate(self) -> None:
        _, baseline_status, _, _, baseline_detail = run_open_batch(ROW)
        self.assertEqual(baseline_status, "abstain")
        _, target_id = baseline_detail.split("\t", 1)

        with tempfile.TemporaryDirectory() as directory:
            evidence_path = write_evidence(directory, target_id, "test:fixture")
            _, status, prediction, _, detail = run_open_batch(
                ROW, evidence=evidence_path
            )

        # This is the regression check for the latent bug fixed alongside
        # --evidence: resolveOpenDecision's authorization match previously
        # let its wildcard catch Just (PromotedPreferencePath _), so a
        # genuinely promoted candidate would have been reported "rejected"
        # instead of "emitted" here.
        self.assertEqual(status, "emitted")
        self.assertEqual(prediction, "metonymic")
        self.assertTrue(detail.startswith("promoted:test:fixture:"))

    def test_mismatched_evidence_does_not_promote(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            evidence_path = write_evidence(
                directory, "not-the-real-target", "test:fixture"
            )
            _, status, _, _, _ = run_open_batch(ROW, evidence=evidence_path)
        self.assertEqual(status, "abstain")

    def test_no_context_ablation_withholds_evidence(self) -> None:
        _, _, _, _, baseline_detail = run_open_batch(ROW)
        _, target_id = baseline_detail.split("\t", 1)

        with tempfile.TemporaryDirectory() as directory:
            evidence_path = write_evidence(directory, target_id, "test:fixture")
            _, promoted_status, _, _, _ = run_open_batch(ROW, evidence=evidence_path)
            _, no_context_status, _, _, _ = run_open_batch(
                ROW, ablation="no-context", evidence=evidence_path
            )

        self.assertEqual(promoted_status, "emitted")
        self.assertEqual(no_context_status, "abstain")


if __name__ == "__main__":
    unittest.main()
