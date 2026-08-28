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

For a full local Wikidata dump, build the offline SQLite index once. The
current entity dump is over 100 GB compressed, so it is deliberately an
explicit operation, outside CI and the Cloud Agent install:

```bash
./scripts/download_wikidata_dump.sh \
  https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.json.bz2 \
  ~/.cache/metonymy/wikidata/latest-all.json.bz2

python3 scripts/build_wikidata_runtime_index.py build \
  --dump ~/.cache/metonymy/wikidata/latest-all.json.bz2 \
  --database ~/.cache/metonymy/wikidata/runtime.sqlite
```

The index retains English labels/aliases and the projected relation/type
properties, along with the exact dump SHA-256. Resolve a textual mention using
only the frozen index:

```bash
python3 scripts/build_wikidata_runtime_index.py lookup \
  --database ~/.cache/metonymy/wikidata/runtime.sqlite \
  --alias "Waterloo"
```

Build a batch linker cache from unlabelled inference inputs; ambiguous aliases
are recorded as ambiguity rather than guessed:

```bash
python3 scripts/build_wikidata_linker_cache.py \
  --database ~/.cache/metonymy/wikidata/runtime.sqlite \
  --inputs evaluation/contextual-multidomain/audited-inputs.jsonl \
  --output build/evaluation/wikidata-linker-cache.json
```

Then materialize a bounded, hash-bound snapshot for one or more resolved QIDs:

```bash
python3 scripts/build_wikidata_runtime_index.py materialize \
  --database ~/.cache/metonymy/wikidata/runtime.sqlite \
  --source-qid Q639408 --source-qid Q649 --depth 2 \
  --rules data/wikidata-runtime-rules.json \
  --output build/wikidata-qid-snapshot
```

The SQLite index is an untrusted offline retrieval structure. The materialized
finite snapshot—not the mutable index—is the runtime KB passed to the checker
and bound into certificates through `graph_sha256`. Its manifest records both
the bounded materialization parameters and the immutable source-index hash.

## Automatic language-database pipeline

The automatic proposer combines:

- GF-compatible lexical anchors and spans;
- hard action roles from `data/predicates.tsv` and all compiled Action×Role
  projections from `data/verbnet-action-roles.tsv`;
- 5,001 lexical projections generated from Princeton WordNet;
- QID aliases and graph claims from the frozen Wikidata snapshot;
- optional OpenAlex institution-topic evidence in
  `data/wikidata-openalex-snapshot/evidence.jsonl`.

Action senses that share a lemma and hole are alternatives, so their distinct
requirements are compiled into one disjunction rather than intersected as
separate layers. Audited hard requirements take precedence; otherwise the
layer is represented by `Prefers`/`PrefersSome`/`PrefersRelation`. A
preference records its matching subset and misses but does not remove
candidates from the hard fiber. Agda independently verifies both partitions.
Bridge relations are selected by a global requirement-sort schema and then
intersected with the active snapshot's `rules.json`, rather than being listed
per action or scenario. `data/contextual-language-rules.json` now retains only
irregular morphology overrides and sort-level bridge, composition, and
construction schemas.

Adjective–noun semantics are compiled bottom-up from the actual GF subtree.
For example, WordNet supplies `Political` and `Agreement`, the versioned
composition matrix derives `PoliticalAgreement`, and the action/object rule
adds the corresponding signer requirement. Unknown compositions fail closed.
The same tree walker recognizes `in/about/with/for` PP modifiers and
WordNet-generated common nouns inside relative clauses. The generic
Programme/ResearchProgramme template derives `Conducts(_, topic-QID)` without
matching the words `programme` or `physics` in code.

### Cumulative constituent layers

Supported positive constituents are elaborated in their semantic composition
order rather than as a flat token list:

```text
verb
verb + object head
verb + composed adjective/object
verb + object modifier
```

The lexical anchor of each constraint spans the cumulative surface phrase, so
the CLI exposes labels such as `declare`, `declare programme`, and
`declare programme in physics`. VerbNet supplies action roles, its pinned
FrameNet links supply frame identities, and WordNet supplies argument sorts.

`RequiresSome relation requirement` is the executable existential fragment:
it holds for candidate `x` exactly when the frozen snapshot contains some
`relation(x, y)` and `y` satisfies `requirement`. Both Haskell and the
independently compiled Agda checker evaluate this witness at every prefix.
Frame/argument combinations without an audited entity-level capability
projection still receive a compatibility layer, but that layer cannot claim
or invent a capability fact. Capability projections are global,
sort-and-frame-level rules, not sentence scenarios.
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

The complete FrameNet XML adapter imports frame definitions, FEs, lexical
units, and FE/GF/PT valence patterns from a user-supplied 1.7 distribution:

```bash
python3 scripts/import_framenet_context.py \
  --framenet-dir /path/to/fndata-1.7 \
  --output build/framenet-context
```

Pass `--framenet-snapshot build/framenet-context` to the automatic pipeline.
When the licensed XML is absent, pinned VerbNet FrameNet links remain a
metadata fallback. The 32 evidence-ranked role-capability projections in
`data/framenet-role-capabilities.json` are generated reproducibly and remain
preferences.

External evidence is merged by `merge_context_evidence.py`, which recomputes
`graph_sha256`. It cannot silently mutate an already certified snapshot.
