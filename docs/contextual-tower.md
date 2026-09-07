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
via the RGL's `PassAgentVPSlash (SlashV2a verb) agent` -- `PassAgentVPSlash`
from `Extend`/`ExtendEng`, `SlashV2a` from `Verb`/`VerbEng` (a genuinely
separate module: `Extend`'s own abstract definition only extends `Cat`,
not `Verb`, so it does not re-export `Verb`'s functions; the first CI run
of this change confirmed `SlashV2a` was unreachable with only `SyntaxEng`/
`ExtendEng` opened, and `VerbEng` had to be added explicitly) -- and
predicated with the existing `Pred : NP -> VP -> S` -- the passive
clause's grammatical subject (semantically the patient) fills the same
slot an active subject does; no new `S`-level rule was needed.
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

### Coordination and arbitrary prepositions

`Metonymy.gf`'s abstract syntax previously had exactly one clause-level
category and no cross-sentence or coordination structure at all -- a
handful of `Pred`/`Compl`/`PassCompl`-style constructions and four
hardcoded prepositions (`InPP`/`AboutPP`/`WithPP`/`ForPP`). Locally
reproducing the real contextual-tower-evaluation.yml sample (see the
"Source-mention disambiguation" section above) confirmed this was the
dominant remaining bottleneck once the source-disambiguation and
gf_sentence-scoping fixes landed: `gf-parse-empty` accounted for the
large majority of both corpora's failures once other, earlier stages
stopped masking it, and it kept the pool constant even after scoping
gf_sentence down to a single sentence -- i.e. the failures were real
single-sentence construction/vocabulary gaps, not a paragraph-scoping
artifact.

Added `AndS`/`OrS : S -> S -> S`, `AndNP`/`OrNP : NP -> NP -> NP`, and
eight new fixed prepositions -- `OnPP`/`AtPP`/`FromPP`/`ByPP`/`OverPP`/
`UnderPP`/`DuringPP`/`NearPP : NP -> PP`, alongside the original
`InPP`/`AboutPP`/`WithPP`/`ForPP`. All linearize through RGL functions
already reachable via the existing `open SyntaxEng` (no new `open`
needed -- confirmed against the pinned gf-rgl commit's actual source:
`Syntax`'s own interface is `Constructors, Cat, Structural, Combinators`,
and `Constructors.gf` already carries the binary-coordination overloads
`mkS : Conj -> S -> S -> S` and `mkNP : Conj -> NP -> NP -> NP`, while
`and_Conj`/`or_Conj` live in `Structural.gf`): `AndS s1 s2 = mkS and_Conj
s1 s2`, `AndNP np1 np2 = mkNP and_Conj np1 np2`, `NearPP np = SyntaxEng.mkAdv
(mkPrep "near") np` (and so on for the other seven, exactly like the
original four already did). Because `lincat NP = NP`/`S = S` throughout,
an `AndNP`/`OrNP` result composes everywhere a plain `NP` already could
(as a `Compl` object, a `Pred` subject, ...) with no special-casing
elsewhere, and gets RGL's own plural-agreement handling for free --
unlike the hand-rolled `Open*` family, which fakes agreement via manual
string concatenation.

**A first attempt used one open-ended `PrepPP : String -> NP -> PP`**
instead of eight fixed ones, parsed the same open-vocabulary way
`OpenPN`/`EveryCN` already are -- reverted after the first real CI run
against it. GF's `String` category parses as "match any single token",
and combined with the grammar's own already-open `OpenPN`/`Open*`
family, this created a genuine new parse ambiguity: "the political
agreement" gained a spurious *second* reading as `OpenPN "the"` modified
by `PrepPP "political" (OpenPN "agreement")` (i.e. "the", reinterpreted
as an open proper noun, followed by "political" reinterpreted as an
open preposition governing "agreement") alongside its intended reading
as an adjective-modified definite NP -- and since `engine parse` returns
every alternative tree GF finds, `trees[0]` was no longer reliably the
intended one, breaking three existing tests
(`test_qid_fiber.py`'s `test_automatic_multi_source_pipelines`,
`test_unique_and_ambiguous_contextual_contraction`,
`test_unknown_gf_semantic_composition_fails_closed`) whose fixtures
depended on that specific sentence parsing unambiguously. A closed,
named preposition per function has no such ambiguity -- each only ever
matches its own fixed word, exactly like the original four already did;
this is why the list above is eight separate functions rather than one
parameterized one.

`scripts/contextual_rule_compiler.py`'s `compile_gf_constraints` tree
walker required no structural changes for coordination: `first_node`'s
recursion already walks into any constructor's arguments generically, so
it finds a `Compl` node nested inside an `AndS` exactly as it would
anywhere else, and `_noun_lemma`/`_proper_lemma` already degrade to a
safe no-op (no constraint, no crash) for a constructor shape they do not
recognize -- the same protection a bare-proper-noun object already
relied on -- which is what an `AndNP`/`OrNP` object gets today. The
eight new prepositions slot directly into the existing
`ModifyNP`+fixed-preposition composition-matrix table
(`InPP`/`AboutPP`/`WithPP`/`ForPP`'s hardcoded lookup) the same way the
original four already do; no `context_templates` data has entries keyed
by any of the eight yet, so none of them contribute an extra
`FrameModifier` constraint today, but the wiring is in place for when
such data is authored.

As with the passive-voice addition, the grammar edit and RGL function
names are verified against the pinned `gf-rgl` commit's actual source
but not locally compilable (no GF toolchain on this machine) --
`tests/evaluation/test_compile_gf_constraints_coordination.py` covers
the Python-side tree-walker contract against hand-built tree strings,
independent of whether the grammar itself compiles; that only happens
in CI/`.cursor`.

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

## Running WiMCor/ConMeC through the tower

`run_contextual_corpus.py` expects `{id, sentence, source, family}` rows, not
the flat pipeline's `{id, source, text, target, gold, gold_bridge, ...}` shape
(`scripts/evaluation/prepare_wimcor.py`/`prepare_conmec.py`).
`scripts/evaluation/adapt_metonymy_corpus_for_tower.py` converts one into the
other:

```bash
python3 scripts/evaluation/prepare_wimcor.py \
  --archive /path/to/wimcor-v1.1.tar.gz --split test \
  --output build/evaluation/wimcor-test.inputs.jsonl

python3 scripts/evaluation/adapt_metonymy_corpus_for_tower.py \
  --dataset build/evaluation/wimcor-test.inputs.jsonl \
  --sentences-output build/evaluation/wimcor-test.tower-sentences.jsonl \
  --gold-output build/evaluation/wimcor-test.tower-gold.jsonl

python3 scripts/evaluation/run_contextual_corpus.py \
  --dataset build/evaluation/wimcor-test.tower-sentences.jsonl \
  --engine build/metonymy \
  --snapshot data/wikidata-openalex-snapshot \
  --output build/evaluation/wimcor-test.tower-inference.jsonl

python3 scripts/evaluation/score_contextual_detection.py \
  --inference build/evaluation/wimcor-test.tower-inference.jsonl \
  --gold build/evaluation/wimcor-test.tower-gold.jsonl \
  --output build/evaluation/wimcor-test.tower-report.json
```

**The adapter is lossy by construction, not by oversight**: WiMCor and
ConMeC only ever annotate metonymic-vs-literal plus a bridge-family type
(e.g. `location-for-institution`); neither names a specific correct
Wikidata entity. `score_qid_fibers.py`'s exact-QID-in-fiber metric --
the one the `contextual-multidomain` audited/silver fixtures above use --
cannot be computed for these corpora at all, since there is no
`gold_qids` to compare against. `score_contextual_detection.py` scores
the weaker claim these corpora actually support instead: for a
gold-metonymic mention, did the tower run successfully and end with a
non-empty final fiber (some bridged reading survived every stage); for a
gold-literal mention, did it correctly end with none. This mapping ("ok
+ non-empty fiber" = predicted metonymic) is a design choice documented
in that script's own docstring, not something the engine reports as a
native flag -- read it before citing precision/recall/F1 from this path.

**Coverage caveat**: the frozen `data/wikidata-openalex-snapshot` and the
current `composition_matrix`/`context_templates` coverage are both still
narrow (a handful of adjective×noun sorts, a curated multi-domain entity
set). Running the full WiMCor/ConMeC corpora through this path today will
mostly abstain (`gf-parse-failed`/`semantic-composition-failed`/
`source-qid-unresolved`) rather than produce a large, representative
sample of genuine tower-verified endpoints -- `literal_prediction_reasons`
in the score report shows exactly which. Scaling this up further is
Items 2-4's job (`scripts/build_wikidata_api_index.py` run at real
corpus scale, more `composition_matrix`/`context_templates` coverage,
more GF grammar constructions), not this adapter's.

### Source-mention disambiguation via the tower itself

An exact-alias match against a corpus-scale snapshot (see
`data/SOURCES.md`'s "Wikidata live-API runtime index" section) very often
yields more than one QID for one surface -- ordinary place names are the
worst offender: a live-API snapshot built from a 300-sentence WiMCor/
ConMeC sample resolved `"Liverpool"` to 12 distinct QIDs, `"Boston"` to
10, `"Santiago"` to 17, almost all of them identically-named minor US
census-designated places/unincorporated communities rather than the
entity the sentence actually means. `propose_contextual_scenario.py` does
not try to pick one: it hands the full candidate list to
`run_automatic_contextual_pipeline.py`, which runs the (candidate-
independent) action/GF-parse/constraint-compilation stages exactly once
and then the tower's own existing per-layer narrowing -- unmodified,
still `contextLayerCheck`/`runtimeCheck`-verified -- once per candidate
QID. A candidate is confirmed only if its own run ends with a non-empty
final fiber, i.e. something reachable from *that* QID actually satisfies
every constraint the sentence's words imposed; a same-named township with
no matching institution nearby simply dead-ends. Exactly one confirmed
candidate is the answer; zero is a legitimate literal prediction (no
candidate identity supports a metonymic reading); two or more is reported
as `source-disambiguation-ambiguous` (`SystemExit(6)`) rather than guessed
-- the same exact-match-or-abstain policy the entity linker itself already
follows. This only touches the untrusted proposer side of the trust
boundary (`docs/architecture.md`: "Hard search results are untrusted
until `runtimeCheck` succeeds"); no formal theorem changed. `--contract-target`
keeps the older, stricter single-candidate requirement, since a
contraction can be *correctly* rejected by the formal checker and that
must not be confused with a disambiguation failure.
