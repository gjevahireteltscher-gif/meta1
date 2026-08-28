import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/evaluation/fixtures/framenet"


def jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


class FrameNetAdapterTests(unittest.TestCase):
    def test_imports_frames_fes_lus_and_valence_patterns_deterministically(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            command = [
                "python3",
                str(ROOT / "scripts/import_framenet_context.py"),
                "--framenet-dir",
                str(FIXTURE),
            ]
            subprocess.run(command + ["--output", str(first)], check=True)
            subprocess.run(command + ["--output", str(second)], check=True)

            self.assertEqual(
                (first / "manifest.json").read_bytes(),
                (second / "manifest.json").read_bytes(),
            )
            manifest = json.loads((first / "manifest.json").read_text())
            self.assertEqual(manifest["frames"], 1)
            self.assertEqual(manifest["frame_elements"], 3)
            self.assertEqual(manifest["lexical_units"], 1)
            self.assertEqual(manifest["valence_patterns"], 1)
            self.assertFalse(manifest["redistributed"])

            frame = jsonl(first / "frames.jsonl")[0]
            self.assertEqual(frame["name"], "Statement")
            self.assertEqual(
                [element["name"] for element in frame["frame_elements"]],
                ["Message", "Speaker", "Topic"],
            )
            lexical_unit = jsonl(first / "lexical-units.jsonl")[0]
            self.assertEqual(lexical_unit["name"], "declare.v")
            pattern = jsonl(first / "valence-patterns.jsonl")[0]
            self.assertEqual(pattern["frame"], "Statement")
            self.assertEqual(
                {unit["fe"] for unit in pattern["units"]},
                {"Speaker", "Message"},
            )

    def test_generates_bounded_preference_only_frame_capabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "capabilities.json"
            subprocess.run(
                [
                    "python3",
                    str(ROOT / "scripts/generate_framenet_capabilities.py"),
                    "--output",
                    str(output),
                    "--limit",
                    "32",
                ],
                check=True,
                cwd=ROOT,
            )
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["projection_count"], 32)
            self.assertEqual(len(result["projections"]), 32)
            self.assertTrue(
                all(
                    projection["strength"] == "SelectionalPreference"
                    for projection in result["projections"]
                )
            )
            self.assertTrue(
                all(projection["evidence_count"] > 0 for projection in result["projections"])
            )


if __name__ == "__main__":
    unittest.main()
