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

### Live-API runtime index (no dump download)

For entity linking at the scale of one corpus's distinct mention surfaces
(not the whole graph), `scripts/build_wikidata_api_index.py` populates the
same SQLite schema directly from Wikidata's live API, so the dump download
above can be skipped entirely:

```bash
python3 scripts/build_wikidata_api_index.py \
  --database build/wikidata-api-runtime.sqlite \
  --dataset evaluation/contextual-multidomain/audited-inputs.jsonl \
  --dataset-field source \
  --depth 1 --max-entities 5000
```

The resulting `.sqlite` file is a drop-in replacement for the dump-built
index above: `lookup`, `build_wikidata_linker_cache.py`, and `materialize`
(both shown next) all work against it unchanged. It only ever knows about
entities reachable within `--depth` hops of the corpus's own mention
surfaces, so it is deliberately narrower than a full-dump index; see
data/SOURCES.md for the reproducibility caveat that comes with sourcing it
live instead of from a pinned dump file.

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

### Passive voice

`Metonymy.gf`/`MetonymyEng.gf` add `PassCompl : V2 -> NP -> VP`, linearized
via the RGL's `PassAgentVPSlash (SlashV2a verb) agent` (from `Extend`/
`ExtendEng`) and predicated with the existing `Pred : NP -> VP -> S` --
the passive clause's grammatical subject (semantically the patient) fills
the same slot an active subject does; no new `S`-level rule was needed.
`scripts/annotate_dependency_hints.py` reports a passive subject
(`nsubj:pass`) as `hole_role="Object"` (it is the patient, not the agent)
and the "by"-agent phrase (`obl` + `case="by"` on a verb with an
`aux:pass` child) as `hole_role="Subject"`, both with a `voice="passive"`
field and a governing span covering the auxiliary too ("was captured",
not just "captured"). `resolve_action` uses that to substitute a full
present-passive form ("is captured") rather than the active third-person
form, always assuming a singular subject -- the same implicit convention
the existing active-voice substitution already relies on (a genuine
plural/collective subject is out of scope here; see below).

This is the one part of this session's changes that cannot be verified
locally: there is no GF toolchain on this development machine, so the
grammar edit and the RGL function names (confirmed against the pinned
`gf-rgl` commit's actual source, not guessed) are unverified until
`make test`/`make formal-artifact` run in CI or the `.cursor` container.
The Python-side dependency-hint classification, `resolve_action`'s
`gf_form` selection, and `compile_gf_constraints`' handling of a
`PassCompl` tree node are all covered by local unit tests against
hand-built inputs (`tests/evaluation/test_compile_gf_constraints_passive.py`
and the passive cases in `test_annotate_dependency_hints.py`/
`test_resolve_action_dependency_hint.py`), independent of whether the
grammar itself compiles.

Deliberately out of scope for this pass: plural/collective subjects
(a "the players" bridge onto one collective entity, staying inside the
accepted one-entity-per-hole boundary), tense/aspect beyond present, and
further PP/modifier stacking beyond what the existing recursive
`ModifyNP` walker already handles structurally.

Adjective–noun semantics are compiled bottom-up from the actual GF subtree.
WordNet now projects `political`, `commercial`, `educational`, and
`scientific` as modifier sorts. The composition matrix covers agreement,
programme, organization, and institution heads; unknown pairs still fail
closed. The same tree walker recognizes `in/about/with/for` PP modifiers and
WordNet-generated common nouns inside relative clauses. Programme heads still
derive hard `Conducts(_, topic-QID)`; institution/organization locatives and
partner PPs are preferences.

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
