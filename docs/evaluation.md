# Evaluation datasets and implemented harness

This document records dataset access, licensing constraints, and the
implemented data-free evaluation harness for empirical metonymy checks.

## SemEval-2007 Task 8

Authoritative description: [Markert & Nissim, 2007](https://aclanthology.org/S07-1007/).

Final official counts:

| Subtask      | Train | Test | Total |
|--------------|------:|-----:|------:|
| Location     |   925 |  908 | 1,833 |
| Organisation | 1,090 |  842 | 1,932 |
| Combined     | 2,015 | 1,750 | 3,765 |

Evaluation levels: coarse (literal vs non-literal), medium (literal /
metonymic / mixed), and fine-grained metonymy patterns plus `othermet`.
Official metrics: accuracy, coverage, and per-class precision/recall/F-score.

### Access and format

The archived official download page is unreliable for full data today.
The best maintained scholarly copy for the **location** subtask is the
ACL-2017 replication package:

- [Cambridge Apollo record](https://www.repository.cam.ac.uk/items/8bf4c3c5-af2a-4c8d-84d2-badb4466b6d4)
- [Author GitHub repository](https://github.com/milangritta/Minimalist-Location-Metonymy-Resolution)
- [Location train XML](https://github.com/milangritta/Minimalist-Location-Metonymy-Resolution/blob/master/data/SemEval.train.xml)
- [Location test XML](https://github.com/milangritta/Minimalist-Location-Metonymy-Resolution/blob/master/data/SemEval.test.xml)

Verified file identities:

- Train: 925 samples, SHA-256 `bba7ac28250b1e79921022ace6e2049ed20332c2fc0369ce563f80154c5d09e0`
- Test: 908 samples, SHA-256 `1dc771c9fbee5a6c2cd0cab38b26d3b2a65a637828b602110387656280c8871e`

No active authoritative download was found for the organisation files.

### Licensing

Do **not** commit SemEval contexts to a public repository without written
confirmation from the task organizers / BNC Consortium. The task paper
acknowledges BNC permission for the original distribution, but current BNC
terms restrict redistribution of processed material.

Safe model:

- keep loaders, schemas, scorer, hashes, and acquisition instructions in Git;
- treat SemEval as an opt-in local dataset supplied by the user;
- verify exact hashes and sample counts before scoring;
- do not upload or cache the XML in CI artifacts.

## Open alternatives

### WiMCor (recommended redistributable default)

- [Repository](https://github.com/nlpAThits/WiMCor)
- [LREC 2020 paper](https://aclanthology.org/2020.lrec-1.697/)
- 206k location instances from English Wikipedia
- Data licensed **CC BY-SA 3.0**; code GPLv3
- Best openly redistributable successor for location-metonymy evaluation

### ConMeC (complementary common-noun track)

- [GitHub](https://github.com/SaptGhosh/ConMeC)
- [Hugging Face](https://huggingface.co/datasets/Rey97/ConMeC)
- [NAACL 2025 paper](https://aclanthology.org/2025.naacl-long.330/)
- 6,000 English Wikipedia examples, Apache-2.0
- Covers causer/container/location/possessed/producer/product; not a
  drop-in SemEval replacement

## Harness implementation

The repository now contains:

- `scripts/evaluation/prepare_semeval2007.py`: local XML adapter with
  optional SHA-256 enforcement;
- `scripts/evaluation/score_predictions.py`: independent precision, recall,
  F1, coverage, selective accuracy, and confusion matrices;
- `scripts/evaluation/analyze_false_paths.py`: deterministic error
  categories and path records;
- `scripts/evaluation/run_experiment.py`: fixed five-condition experiment,
  input hashes, Git revision, and separate expansion/contraction reports;
- `tests/evaluation/`: independent adapter, scorer, abstention, and
  false-path tests;
- `evaluation/README.md`: schemas, commands, and contraction-adjudication
  policy.

The five required conditions are `full`, `no-types`, `no-ontology`,
`no-context`, and `no-verbnet`. Every instance must have an explicit result
for every condition; missing rows fail the experiment instead of silently
changing a denominator. Agda verification remains enabled in every
condition.

Run metric tests with:

```bash
make evaluation-test
```

Run a complete locally supplied experiment with:

```bash
make experiment \
  EVALUATION_DATASET=/path/to/dataset.jsonl \
  EVALUATION_PREDICTIONS=/path/to/predictions.jsonl
```

## Relation to this prototype

The current engine is a controlled-language proof-carrying resolver, not an
open-domain classifier. The harness should therefore evaluate:

- whether admissible expansions/contractions align with gold labels on
  overlapping phenomena;
- certificate rejection on non-metonymic or lossy cases;
- coverage and precision of bridge selection under bounded ontology search.

Statistical ranking or LLM reordering may sit outside the trusted kernel and
must not establish formal admissibility.

The open-domain corpus frontend that proposes candidates for this harness is
itself swappable without touching the trusted kernel: `run_engine_predictions.py
--frontend {legacy,dependency}` selects between the original positional
string heuristic and an offline Universal Dependencies parse
(`scripts/annotate_dependency_hints.py`); both route through the same
compiled Agda `runtimeCheck`. Comparing the two frontends' recall/precision
at fixed, unchanged safety guarantees — rather than reporting only one
frontend's numbers — is the intended way to attribute the residual gap
between coverage and the checked construction vocabulary. See
`evaluation/README.md`'s "UD dependency-hint frontend" section for the
commands.

SemEval itself cannot measure endpoint correctness or contraction safety
because it contains neither explicit referents nor safe-forgetting labels.
Those numbers are therefore reported only for independently adjudicated
rows and never presented as official SemEval scores.

The available 908-instance location test split has been run through all five
conditions. The controlled grammar abstained on every instance: coverage
and recall are zero, while precision and F1 are undefined because there are
no submitted predictions. See
`evaluation/semeval-location-test-summary.json`. This negative result
quantifies the open-domain coverage gap rather than hiding it. A complete
organisation result remains blocked by the absence of a verifiable
distributable corpus file.

The later open-GF elaborator has been evaluated separately on redistributable
benchmarks:

- WiMCor v1.1 test, 41,200 rows: metonymic F1 `0.1895`, accuracy `0.7398`,
  bridge-family accuracy `0.4353`, seven exact endpoint recoveries;
- ConMeC, 5,999 valid rows plus one quarantined corrupt row: metonymic F1
  `0.0961`, accuracy `0.6989`;
- SafeCon-Mini, 24 independently authored contraction pairs: precision
  `1.0`, recall `0.6667`, F1 `0.8`, unsafe-contraction rate `0`.

Every emitted open rewrite passed the compiled Agda runtime checker.
Detection and family selection remain untrusted baseline heuristics; formal
acceptance establishes consistency with the audited runtime KB, not that a
heuristic selected the speaker's intended referent.
