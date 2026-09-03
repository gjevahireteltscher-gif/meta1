# Independent evaluation

This directory defines the reproducible evaluation interface. Corpus text is
not committed: SemEval-2007 Task 8 contains BNC-derived contexts whose
redistribution terms are not established by this project.

## Scope

SemEval-2007 Task 8 evaluates literal, metonymic, and mixed uses of location
and organisation names. It does **not** contain explicit expansion targets or
safe-contraction labels. Consequently:

- SemEval scores detection and bridge-family selection;
- endpoint accuracy requires separate blinded adjudication;
- contraction uses a separately annotated JSONL set and is reported apart
  from official SemEval results.

## Prepare licensed local data

```bash
python3 scripts/evaluation/prepare_semeval2007.py \
  --xml "$SEMEVAL2007_DIR/location-test.xml" \
  --domain location \
  --split test \
  --expected-sha256 EXPECTED_HASH \
  --output build/evaluation/dataset.combined.jsonl
```

The generated local rows contain the contexts needed by the engine. Keep
both the source XML and generated JSONL outside Git and CI artifacts.

Open redistributable benchmarks use pinned manifests in
`open-datasets.json`:

```bash
python3 scripts/evaluation/prepare_wimcor.py \
  --archive /path/to/wimcor-v1.1.tar.gz \
  --split test \
  --output build/evaluation/wimcor-test.combined.jsonl

python3 scripts/evaluation/prepare_conmec.py \
  --csv /path/to/DATASET.csv \
  --output build/evaluation/conmec.combined.jsonl \
  --quarantine build/evaluation/conmec-quarantine.json
```

The WiMCor adapter parses its known malformed XML representation without
extracting unsafe archive members. The ConMeC adapter validates the exact
header and quarantines the single corrupted target-absent record.

Safe contraction is evaluated independently with the CC0
`safecon-mini/dataset.jsonl`; neither WiMCor nor ConMeC supplies
safe-forgetting labels.

## Prediction contract

Every dataset ID must have one row for each condition:

```text
full
no-types
no-ontology
no-context
no-verbnet
```

Example:

```json
{
  "id": "location:test:s1",
  "ablation": "full",
  "status": "emitted",
  "prediction": "metonymic",
  "predicted_fine": "place-for-government",
  "path": ["GovernedBy"],
  "runtime_verified": true,
  "agda_verified": true
}
```

Statuses are `emitted`, `no_rewrite`, `abstain`, or `error`. Abstentions are
never silently converted to literal predictions.

Ablations have fixed meanings:

- `no-types`: runtime type assertions and subsort rules are removed;
- `no-ontology`: relation assertions are removed;
- `no-context`: discourse evidence is withheld;
- `no-verbnet`: predicates with VerbNet provenance are removed;
- Agda checking remains enabled in every condition.

Generate all five prediction conditions with the checked runtime:

```bash
python3 scripts/evaluation/split_inputs_gold.py \
  --combined build/evaluation/dataset.combined.jsonl \
  --inputs build/evaluation/dataset.inputs.jsonl \
  --gold build/evaluation/dataset.gold.jsonl

python3 scripts/evaluation/run_engine_predictions.py \
  --engine build/metonymy \
  --dataset build/evaluation/dataset.inputs.jsonl \
  --output build/evaluation/predictions.jsonl
```

The physical split is mandatory: the prediction runner rejects inference
files containing `gold`, `gold_fine`, `gold_bridge`, or `explicit_target`.
For WiMCor and ConMeC, the runner uses the streaming open-GF elaborator.
Every emitted rewrite is separately authorized by the compiled Agda
`runtimeCheck`; rejected candidates are recorded as abstentions.

### UD dependency-hint frontend (optional)

By default, `run_engine_predictions.py` builds `open-batch` rows through the
legacy family-trigger frontend
(`engine/src/Metonymy/OpenDomain.hs`'s `analyzeOpenAtWithEndpoints`), which
infers whether a marked target is a clause subject or object by comparing
character offsets rather than by parsing. `scripts/annotate_dependency_hints.py`
offline-annotates a dataset with an actual Universal Dependencies parse
(Stanza, pinned in `toolchain.lock.json`), and `run_engine_predictions.py
--frontend dependency` routes each row through
`analyzeOpenAtWithDependencyHint` instead — an equally untrusted proposer;
the compiled Agda `runtimeCheck` re-derives admissibility identically either
way. See `docs/architecture.md` for the trust boundary and
`scripts/bootstrap_dependency_frontend.sh` for the opt-in install step (not
part of the default `scripts/bootstrap.sh`/`make test` path).

```bash
python3 scripts/annotate_dependency_hints.py \
  --dataset build/evaluation/dataset.inputs.jsonl \
  --output build/evaluation/dataset.dependency-hints.jsonl

python3 scripts/evaluation/run_engine_predictions.py \
  --engine build/metonymy \
  --dataset build/evaluation/dataset.inputs.jsonl \
  --frontend dependency \
  --dependency-hints build/evaluation/dataset.dependency-hints.jsonl \
  --output build/evaluation/dependency-predictions.jsonl
```

The legacy 5/7-field `open-batch` TSV shape is unchanged; the dependency
frontend adds three trailing columns (`hole_role`, `governing_lemma`,
`dep_status`). A target that the parse places inside a noun-phrase modifier
(e.g. the possessor in "Tolstoy's books") rather than in a direct clause
argument position abstains with `nested-modifier-unsupported` instead of
guessing a role — this is a deliberate scope boundary of the current checked
construction vocabulary, not a parser failure, and the abstention rate for
that specific reason is a direct measure of how much residual gap is
attributable to it. A parser failure on a given sentence degrades that row
to the legacy frontend rather than producing a worse result than the
baseline. Score the resulting predictions file exactly like the legacy one
(below); commit results as a separate, parallel summary file
(e.g. `evaluation/wimcor-dependency-frontend-summary.json`) rather than
overwriting the existing legacy baselines, so the two frontends remain
independently comparable.

Recorded results (`evaluation/wimcor-dependency-frontend-summary.json`,
`evaluation/conmec-dependency-frontend-summary.json`), full condition,
expansion direction, against the identical legacy baseline in
`wimcor-typed-fiber-summary.json`/`conmec-typed-fiber-summary.json`:

| | WiMCor metonymic F1 | WiMCor coverage | ConMeC metonymic F1 | ConMeC coverage |
|---|---|---|---|---|
| legacy | `0.0518` | `0.391` | `0.0220` | `0.405` |
| dependency | `0.1158` | `0.597` | `0.0360` | `0.630` |

Metonymic precision improves alongside recall on both corpora (WiMCor
`0.386` → `0.429`; ConMeC `0.185` → `0.197`), so this is not a
precision/recall trade-off. Exact endpoint recall on WiMCor remains tiny in
absolute terms (`1` → `5` out of `10487`): entity linking is a separate,
still-unaddressed bottleneck (see `data/entity-link-snapshot.tsv`). The
`no-verbnet` ablation is byte-identical to `full` for both frontends on both
corpora, indicating VerbNet-imported Action×Role rows are not yet
contributing any successful rewrite here regardless of frontend.

### LLM promotion-evidence pilot

The dominant abstention reason after the dependency frontend is not a
missing bridge at all: it is a checked `SelectionalPreference` candidate
with no `PromotionEvidence` (WiMCor: `abstain=16602` vs `emitted=1638` in
the full-condition report above -- ten times more candidates stuck at this
stage than authorized). `Metonymy.Promotion.authorizeCandidate`
(`engine/src/Metonymy/Promotion.hs`) already accepts a list of
`DiscourseEvidence`; the compiled Agda `checkPromotion`
(`formal/Metonymy/Checker.agda`) independently re-verifies, for any
supplied evidence, that the candidate is a `SelectionalPreference`, that
the evidence's target string matches the candidate's actual fine target
exactly, and that its source is non-empty.

**`checkPromotion` cannot and does not verify that a discourse-salience
claim is true.** That is not a formalizable property. So unlike every
other guarantee in this system, the precision of evidence-promoted paths
depends entirely on the judgment quality of whatever proposed the
evidence -- here, a small local LLM (Ollama, no API key, no cost) judging
each candidate independently. Report pilot numbers with this caveat
attached; do not fold them into claims about the checker's soundness.

Two new scripts implement the untrusted proposer, in the same two-pass
style as the dependency-hint frontend:

```bash
python3 scripts/evaluation/extract_promotion_candidates.py \
  --predictions build/evaluation/dataset.dependency-predictions.jsonl \
  --inputs build/evaluation/dataset.inputs.jsonl \
  --output build/evaluation/dataset.promotion-candidates.jsonl

python3 scripts/propose_promotion_evidence.py \
  --candidates build/evaluation/dataset.promotion-candidates.jsonl \
  --output build/evaluation/dataset.evidence.tsv \
  --sample-ids-output build/evaluation/dataset.sample-ids.txt \
  --sample-size 750

python3 scripts/evaluation/run_engine_predictions.py \
  --engine build/metonymy --dataset build/evaluation/dataset.inputs.jsonl \
  --frontend dependency \
  --dependency-hints build/evaluation/dataset.dependency-hints.jsonl \
  --evidence build/evaluation/dataset.evidence.tsv \
  --output build/evaluation/dataset.promoted-predictions.jsonl
```

`--evidence` is a TSV, not JSON (`id`, `target_entity_id`, `source`),
deliberately: it is loaded by
`Metonymy.OpenDomain.loadPromotionEvidence`, which parses it without
pulling in a new Haskell JSON-parsing dependency, the same way
`loadEndpointSnapshot` already does for the entity-linker snapshot. The
`no-context` ablation withholds supplied evidence regardless of
`--evidence`, since it models "no discourse evidence available" — this is
the first time that ablation is not a no-op (previously evidence was
always empty everywhere, so `no-context` was byte-identical to `full`).

A pilot samples `--sample-size` candidates (not the full abstained pool)
and scores that exact sampled subset before and after evidence (paired
comparison via `scripts/evaluation/filter_by_ids.py` on
`--sample-ids-output`), rather than diluting the effect across the full
41k/6k corpus. See `.github/workflows/dependency-frontend-evaluation.yml`
for the complete pipeline including the paired before/after scoring; it
uploads only `evidence.tsv` (ids and entity ids, no sentence text) and
`metrics.json` files, never the corpus text extracted into
`promotion-candidates.jsonl`.

## Score the complete experiment

```bash
python3 scripts/evaluation/run_experiment.py \
  --dataset build/evaluation/dataset.inputs.jsonl \
  --gold build/evaluation/dataset.gold.jsonl \
  --predictions build/evaluation/predictions.jsonl \
  --metadata evaluation/toolchain.json \
  --output-dir build/evaluation/report
```

The report contains:

- per-class precision, recall, and F1;
- micro/macro F1, selective accuracy, and coverage;
- separate expansion and contraction results;
- all five ablations;
- confusion matrices and categorized false paths;
- Git revision and input hashes.

Metric code is Python standard-library code and does not import the Haskell
engine. Run its independent tests with `make evaluation-test`.

## Recorded open-domain baselines

Text-free aggregate reports are committed in:

- `wimcor-test-summary.json`;
- `conmec-summary.json`;
- `wimcor-typed-fiber-summary.json`;
- `conmec-typed-fiber-summary.json`;
- `safecon-mini/result-summary.json`;
- `contextual-multidomain/silver-summary.json`;
- `contextual-multidomain/audited-summary.json`.

The historical hard family-trigger baseline remains deliberately modest:
WiMCor metonymic F1 is `0.1895`, ConMeC metonymic F1 is `0.0961`, and the
small frozen linker snapshot recovers seven exact WiMCor endpoints. Inputs
and gold are physically separated by `split_inputs_gold.py`; the prediction
runner rejects files containing scoring-only fields by default.
Removing either types or ontology facts prevents every proposed rewrite
from receiving formal authorization.

The Action×Role reports record the stricter integrated search. They have
lower submitted coverage and F1 because imported VerbNet restrictions remain
`SelectionalPreference`: discovered fibers abstain without target-indexed
promotion evidence. This distinction is intentional and prevents an
empirical preference from becoming a hard formal path.

The contextual multi-domain artifact is a separate, snapshot-relative
fiber evaluation: 69 silver instances (49 expansions, 20 unique-fiber
contractions) and 9 reviewed regressions, all exact against frozen-graph
gold. See `contextual-multidomain/README.md`.

The independent ConMeC-300 selection freezes 300 externally human-annotated
instances (25 per category×label stratum) without committing corpus text.
It evaluates detection and bridge family, not endpoint QIDs. Reproduce it
using `evaluation/independent-conmec-300/README.md`.

Contextual reports additionally expose coverage, abstention, empty-fiber
rate, eliminations by cumulative layer, gold-in-fiber, preference-match rate,
and formal-stage verification rate. Run the fixed semantic-source ablations:

```bash
make contextual-ablations
```

The conditions are `full`, `no-wordnet`, `no-framenet`, `no-existential`,
and `no-formal-filtering`. The last condition retains Haskell evaluation but
deliberately bypasses the Agda layer authorization; reports therefore record
a zero formal-stage verification rate rather than presenting those results
as certified.

## Recorded SemEval location result

The verified 908-instance location test split was run at commit
`292da60cc4a6f258a044bea1e9b3d9f352e0756e`. Aggregate, text-free results
are committed in `semeval-location-test-summary.json`.

This historical result predates the open-GF elaborator: the closed grammar
abstained on all 908 instances. It remains committed to document why the
open frontend was necessary and must not be compared as a current baseline.

The organisation split is not reported because no complete, verifiable
currently distributable source was found. Contraction is also not reported
as a SemEval metric because the task has no explicit target or
safe-forgetting labels.
