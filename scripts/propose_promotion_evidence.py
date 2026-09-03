#!/usr/bin/env python3
"""LLM pilot: propose promotion evidence for a sample of SelectionalPreference
candidates extracted by scripts/evaluation/extract_promotion_candidates.py.

This is an UNTRUSTED proposer, architecturally identical in status to the
positional-heuristic and UD-dependency-parser open-domain frontends: the
compiled Agda checkPromotion (invoked through
engine/src/Metonymy/OpenDomain.hs's loadPromotionEvidence and Main.hs's
`open-batch --evidence`) independently re-verifies that any accepted
evidence's target matches the candidate's actual fine target and that its
source is non-empty, before promoting anything.

Crucially, unlike the type-theoretic guarantees elsewhere in this system,
Agda's checkPromotion does NOT and cannot verify that a discourse-salience
claim is actually TRUE -- that is not a formalizable property. So the
precision of promoted paths depends entirely on this script's (i.e. the
LLM's) judgment quality, not on anything the checker proves. Report this
pilot's results with that caveat explicit; see evaluation/README.md's "LLM
promotion-evidence pilot" section.

Talks to a local Ollama server by default -- no API key, no per-call cost,
nothing to add as a repository secret.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_MODEL = "llama3.2:3b-instruct"
DEFAULT_ENDPOINT = "http://localhost:11434/api/generate"

PROMPT_TEMPLATE = """You are judging whether a proposed metonymic reading is a plausible, contextually salient interpretation of a specific sentence. Answer conservatively: if genuinely unsure, answer false.

Sentence: {sentence}
Marked expression: {target}
Proposed reading: in this sentence, "{target}" stands for {target_surface} (relation type: {family}).

Is {target_surface} a plausible, contextually salient referent for "{target}" in this sentence?

Respond with strict JSON only, no other text: {{"salient": true or false, "justification": "<=200 characters"}}"""


def build_prompt(candidate: dict) -> str:
    return PROMPT_TEMPLATE.format(
        sentence=candidate["sentence"],
        target=candidate["target"],
        target_surface=candidate["target_surface"],
        family=candidate["family"],
    )


def query_ollama(
    prompt: str,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    timeout: float = 60.0,
) -> dict:
    payload = json.dumps(
        {"model": model, "prompt": prompt, "format": "json", "stream": False}
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return json.loads(body["response"])


def propose(
    candidates: list[dict],
    query: Callable[[str], dict],
    source_label: str,
) -> list[dict]:
    """Judge every candidate and return evidence rows for the salient ones.

    Any query failure (network error, malformed JSON, missing "salient"
    key) degrades to "not salient" -- the safe default is to leave the
    candidate abstained, never to promote on an uncertain judgment.
    """
    evidence: list[dict] = []
    for candidate in candidates:
        prompt = build_prompt(candidate)
        try:
            judgment = query(prompt)
            salient = bool(judgment.get("salient"))
        except Exception:  # noqa: BLE001 - any failure -> safe "not salient"
            salient = False
        if salient:
            evidence.append(
                {
                    "id": candidate["id"],
                    "target_entity_id": candidate["target_entity_id"],
                    "source": source_label,
                }
            )
    return evidence


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_evidence_tsv(path: Path, evidence: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        handle.write("id\ttarget_entity_id\tsource\n")
        for row in evidence:
            handle.write(f"{row['id']}\t{row['target_entity_id']}\t{row['source']}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--sample-ids-output",
        type=Path,
        help="optional: write the full sampled candidate id list (one per "
        "line, judged salient or not) -- the correct denominator for a "
        "paired before/after comparison, since --output only contains the "
        "ids judged salient",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=750,
        help="cap on how many candidates to judge (pilot scale, not the full corpus)",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    arguments = parser.parse_args()

    candidates = read_jsonl(arguments.candidates)
    rng = random.Random(arguments.seed)
    sample = (
        candidates
        if len(candidates) <= arguments.sample_size
        else rng.sample(candidates, arguments.sample_size)
    )
    sample.sort(key=lambda row: row["id"])  # deterministic output order

    if arguments.sample_ids_output is not None:
        arguments.sample_ids_output.parent.mkdir(parents=True, exist_ok=True)
        arguments.sample_ids_output.write_text(
            "".join(f"{row['id']}\n" for row in sample), encoding="utf-8"
        )

    def query(prompt: str) -> dict:
        return query_ollama(prompt, model=arguments.model, endpoint=arguments.endpoint)

    source_label = f"llm:{arguments.model}:pilot"
    evidence = propose(sample, query, source_label)
    write_evidence_tsv(arguments.output, evidence)
    print(
        f"promoted {len(evidence)}/{len(sample)} sampled candidates "
        f"(source={source_label})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
