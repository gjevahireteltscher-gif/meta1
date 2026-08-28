#!/usr/bin/env python3
"""Run a gold-free contextual corpus through GF and every Agda-checked layer."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

QID = re.compile(r"Q[0-9]+")


def run_one(engine: Path, snapshot: Path, row: dict) -> dict:
    command = [
        "python3",
        "scripts/run_automatic_contextual_pipeline.py",
        "--engine",
        str(engine),
        "--snapshot",
        str(snapshot),
        "--sentence",
        row["sentence"],
        "--source",
        row["source"],
    ]
    if row.get("direction") == "contract":
        command.extend(["--contract-target", row["contract_target"]])
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
    )
    combined = completed.stdout + completed.stderr
    expected_rejection = row.get("expected_status") == "rejected"
    rejected_by_safety = (
        completed.returncode != 0
        and "contextual contraction rejected" in combined
    )
    successful = rejected_by_safety if expected_rejection else completed.returncode == 0
    result = {
        "id": row["id"],
        "family": row["family"],
        "families": [row["family"]],
        "status": "ok" if successful else "failed",
        "exit_code": completed.returncode,
        "direction": row.get("direction", "expand"),
        "expected_status": row.get("expected_status", "accepted"),
        "stages": [],
    }
    current = None
    for line in completed.stdout.splitlines():
        if line.startswith("gf-tree="):
            result["gf_tree"] = line.split("=", 1)[1]
        elif line.startswith("graph_sha256="):
            result["graph_sha256"] = line.split("=", 1)[1]
        elif line.startswith("contract="):
            match = re.match(r"contract=(Q[0-9]+) -> (Q[0-9]+) safety=(.*)", line)
            if match:
                result["contracted_target"] = match.group(1)
                result["contracted_source"] = match.group(2)
                result["contraction_safety"] = match.group(3)
        elif line.startswith("stage="):
            match = re.match(r"stage=(\d+) constraint=(.*)", line)
            current = {
                "index": int(match.group(1)),
                "constraint": match.group(2),
                "survivors": [],
                "obstructions": [],
                "agda_checked": False,
            }
            result["stages"].append(current)
        elif current is not None and line.strip().startswith("survivors="):
            current["survivors"] = QID.findall(line)
        elif current is not None and line.strip() == "agda-layer-check=true":
            current["agda_checked"] = True
        elif current is not None and line.strip().startswith("obstruction="):
            current["obstructions"].append(line.strip().split("=", 1)[1])
    result["fiber"] = (
        [result["contracted_source"]]
        if "contracted_source" in result
        else (result["stages"][-1]["survivors"] if result["stages"] else [])
    )
    if completed.returncode != 0:
        result["failure"] = (completed.stdout + completed.stderr).strip()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    inputs = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = list(
            executor.map(
                lambda row: run_one(args.engine, args.snapshot, row),
                inputs,
            )
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in results),
        encoding="utf-8",
    )
    failures = sum(row["status"] != "ok" for row in results)
    print(f"instances={len(results)} failures={failures}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
