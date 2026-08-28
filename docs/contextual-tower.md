# Lexicalized contextual fiber tower

The contextual pipeline computes every snapshot-witnessed interpretation rather
than selecting a top-1 endpoint:

```text
local Wikidata dump
  → deterministic QID snapshot + graph_sha256
  → lexicalized GF application tree
  → ordered ContextConstraint tower
  → survivors and structured obstructions at every stage
  → compiled Agda contextualRuntimeCheck
  → cubical path for every accepted stage certificate
```

Concrete entities are QIDs loaded from `data/wikidata-qid-snapshot`. The
fixed code contains only the ontology vocabulary and the generic algorithms.
Property projections, type mappings, queries, and lexical constraints are
versioned data in `rules.json` and `data/contextual-scenarios.tsv`.

## Reproduce the Waterloo slice

```bash
./build/metonymy contextual-fiber waterloo

python3 scripts/evaluation/extract_qid_fibers.py \
  --dataset evaluation/qid-fiber/waterloo-dataset.jsonl \
  --engine build/metonymy \
  --output build/evaluation/waterloo-contextual-inference.jsonl

python3 scripts/evaluation/score_qid_fibers.py \
  --inference build/evaluation/waterloo-contextual-inference.jsonl \
  --gold evaluation/qid-fiber/waterloo-gold.jsonl \
  --output build/evaluation/waterloo-contextual-report.json
```

The final Waterloo layer contains `Q1049470` and `Q2004561`. `Q7974219`
is removed by a `MissingRelation Conducts Q413` obstruction. The two survivors
remain distinct unless an explicit compatibility witness is supplied.

Unique-fiber contraction of `Q1049470` is therefore rejected: the reverse
path exists for each survivor, but `UniqueEntity` fails. The CLI
`contextual-contract` authorizes contraction only when the explicit target is
the unique final survivor or a `GenericReading`.

## Formal witnesses

`Metonymy.ContextualTower` provides:

- `elaborationBindsLexemes`;
- `fiberRestriction`;
- `extensionSound` and `extensionComplete`;
- `obstructionSound`, `extensionOrObstruction`, and
  `obstructionTerminatesPath`;
- `stagePath`;
- `towerPathStability`;
- `compatibleCandidatesGlue`;
- `emptyFiberNoRewrite`.
- `FilteredContext.UniqueEntity`, `safeContraction`, and
  `uniqueEntityStrengthens`.

Path stability requires explicit equality of the underlying checked runtime
cell. It does not claim that arbitrary discourse extension preserves a
metonymic license.

## Scope

All results are relative to the finite snapshot hash and supplied lexicalized
GF tree. Parsing coverage, Wikidata completeness, intended-reference
uniqueness, and factual correctness of external data are not proved. A missing
snapshot witness is an obstruction for that run, not impossibility in natural
language.

## Full dump runtime index

For a full local Wikidata dump, build the offline SQLite index once:

```bash
python3 scripts/build_wikidata_runtime_index.py build \
  --dump /data/latest-all.json.bz2 \
  --database /data/wikidata-runtime.sqlite
```

Then materialize a bounded, hash-bound snapshot for one source QID:

```bash
python3 scripts/build_wikidata_runtime_index.py materialize \
  --database /data/wikidata-runtime.sqlite \
  --source-qid Q639408 --depth 2 \
  --rules evaluation/qid-fiber/rules.json \
  --output data/wikidata-qid-snapshot
```

The SQLite index is an untrusted offline retrieval structure. The materialized
finite snapshot—not the mutable index—is the runtime KB passed to the checker
and bound into certificates through `graph_sha256`.

## Automatic language-database pipeline

The automatic proposer combines:

- GF-compatible lexical anchors and spans;
- versioned VerbNet/action rules from `data/contextual-language-rules.json`;
- 5,001 lexical projections generated from Princeton WordNet;
- QID aliases and graph claims from the frozen Wikidata snapshot;
- optional OpenAlex institution-topic evidence in
  `data/wikidata-openalex-snapshot/evidence.jsonl`.

Adjective–noun semantics are compiled bottom-up from the actual GF subtree.
For example, WordNet supplies `Political` and `Agreement`, the versioned
composition matrix derives `PoliticalAgreement`, and the action/object rule
adds the corresponding signer requirement. Unknown compositions fail closed.
After every cumulative constraint prefix, Haskell calls compiled Agda
`contextLayerCheck` for every survivor and every obstruction before advancing
to the next stage.

Run the complete proposal-to-tower path without writing a scenario manually:

```bash
python3 scripts/run_automatic_contextual_pipeline.py \
  --engine build/metonymy \
  --snapshot data/wikidata-openalex-snapshot \
  --sentence "Waterloo announced a programme in physics" \
  --source Waterloo

python3 scripts/run_automatic_contextual_pipeline.py \
  --engine build/metonymy \
  --snapshot data/wikidata-openalex-snapshot \
  --sentence "John reads Masnavi" \
  --source Rumi \
  --contract-target Masnavi
```

WordNet and OpenAlex adapters operate on local/versioned artifacts:

```bash
python3 scripts/import_wordnet_context.py \
  --wordnet-dir /usr/share/wordnet \
  --output data/wordnet-context-rules.json

python3 scripts/import_openalex_context.py \
  --snapshot data/wikidata-multidomain-snapshot \
  --source-qids Q1049470,Q2004561 \
  --output build/openalex-context-evidence.jsonl
```

External evidence is merged by `merge_context_evidence.py`, which recomputes
`graph_sha256`. It cannot silently mutate an already certified snapshot.
