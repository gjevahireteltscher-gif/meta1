# Cubical GF for proof-carrying metonymy

Research prototype positioning metonymy processing as an application of a
**Cubical extension of Grammatical Framework**. Metonymic compression is
treated as a context-indexed quotient of explicit meanings. The system
combines:

- Grammatical Framework (GF) with its standard English Resource Grammar
  Library for parsing, morphology, agreement, and linearization;
- a Haskell engine for typed ontology queries, bridge search, expansion,
  contraction, and proof-carrying certificates;
- Cubical Agda for the higher-inductive quotient, metonymic path
  constructor, homotopy fiber of expansions, and round-trip results.

GF and the deterministic open frontend propose typed grammatical
elaborations. Haskell proposes ontology bridges. The compiled Agda checker
is the authorization boundary: only accepted certificates induce cubical
paths and equality in the independent quotient semantics.

The checked-in knowledge snapshots currently cover 33 imported authors,
92 named literary works, 10 local predicates, 41 legacy GF predicates,
6,739 VerbNet action senses, and 55,024 Action×Role realizations. Of those
role rows, 17,006 have an audited executable projection; the rest remain
lossless provenance records rather than being silently discarded.

```text
Anna reads Tolstoy.
  → Anna reads Tolstoy's works.

Anna drinks a glass.
  → Anna drinks the contents of a glass.

Moscow signs the agreement.
  → The Russian government signs the agreement.

John reads Rumi.
  → John reads Rumi's works.
  → John reads Masnavi.

John studies Rumi.
  → John studies Rumi's works.

Alice listens to Mozart.
  → Alice listens to Mozart's music.

Bob watches Spielberg.
  → Bob watches Spielberg's films.

John eats a plate.
  → John eats the food on the plate.

Mary wears Chanel.
  → Mary wears Chanel clothing.

John scrutinizes Rumi.
  → John scrutinizes Rumi's works.

Alice hears Mozart.
  → Alice hears Mozart's music.

John devours a plate.
  → John devours the food on the plate.
```

It also contracts generic explicit readings:

```text
Anna reads Tolstoy's works.
  → Anna reads Tolstoy.
```

Contraction of a specific work is deliberately rejected because it loses
information:

```text
Anna reads War and Peace.
  ↛ Anna reads Tolstoy.
```

## Architecture

```text
English text
  → GF abstract syntax
  → typed predicate requirement
  → proof-producing ontology query
  → admissible semantic fiber
  → expansion or safe contraction
  → checked certificate
  → GF linearization
  → English text
```

The runtime distinguishes two notions:

- `BridgePath x y` is a directed ontological relation such as
  `Authored`, `Contains`, or `GovernedBy`;
- a cubical path connects the implicit and explicit grammatical
  derivations after an admissibility certificate has been constructed.

The Haskell `Certificate` mirrors the Agda `Admissible` type. Search and
ranking may be heuristic, while certificate verification rechecks every
relation and selectional requirement.

See [docs/architecture.md](docs/architecture.md) for module boundaries and
the trust model.

## Prerequisites

- GHC 9.4 or newer;
- GF 3.12;
- GF Resource Grammar Library tag `20260403`;
- Agda 2.6.3;
- `agda/cubical` v0.5.

The checked-in Cursor environment installs compatible versions. On Ubuntu
24.04, `./scripts/bootstrap.sh` clones the pinned Cubical and GF Resource
Grammar libraries, compiles the English GF grammar, checks the Agda
development, builds the Haskell executables, and runs all tests.

```bash
./scripts/bootstrap.sh
```

After bootstrapping:

```bash
./scripts/check.sh
```

If Cubical is installed in a custom location:

```bash
CUBICAL_LIB=/path/to/cubical ./scripts/check.sh
```

The English RGL location can likewise be overridden:

```bash
RGL_LIB=/path/to/compiled-rgl ./scripts/check.sh
```

## Running the prototype

List scenarios:

```bash
./build/metonymy list
```

Expand metonymic expressions:

```bash
./build/metonymy expand "Anna reads Tolstoy"
./build/metonymy expand "Anna drinks a glass"
./build/metonymy expand "Moscow signs the agreement"
./build/metonymy expand "John reads Rumi"
./build/metonymy expand "John studies Rumi"
./build/metonymy expand "Alice listens to Mozart"
./build/metonymy expand "Bob watches Spielberg"
./build/metonymy expand "John eats a plate"
./build/metonymy expand "Mary wears Chanel"
./build/metonymy expand "John scrutinizes Rumi"
./build/metonymy expand "Alice hears Mozart"
./build/metonymy expand "John devours a plate"
```

VerbNet preferences remain candidates unless matching discourse evidence is
provided:

```bash
./build/metonymy expand "John scrutinizes Rumi"
# status=candidate-only path=False

./build/metonymy expand "John scrutinizes Rumi" \
  --discourse-salient works-of-Q43347 \
  --evidence-source conversation:turn-4
# the matching generic reading has status=promoted-preference path=True
```

The Agda runtime checker binds every authorized path to the exact source and
target GF trees, predicate, hole, direction, lexeme/entity mapping, and
certificate. A checked preference without validated evidence does not
generate a path.

Contract a generic explicit expression:

```bash
./build/metonymy contract "Anna reads Tolstoy's works"
```

Observe rejection of lossy contraction:

```bash
./build/metonymy contract "Anna reads War and Peace"
```

Exercise GF parsing:

```bash
./build/metonymy parse "Anna reads Tolstoy"
```

Scenario identifiers remain available as a lower-level debugging interface:

```bash
./build/metonymy expand read-tolstoy
./build/metonymy contract read-tolstoy works-of-tolstoy
```

## Knowledge data

`data/wikidata-author-works.tsv` is an offline, testable snapshot generated
from Wikidata. Every row retains its source relation provenance. The query
requires:

```text
author occupation/subclass → writer (P106/P279)
author notable work         → work (P800)
work instance/subclass      → literary work (P31/P279)
```

Refresh it explicitly:

```bash
./scripts/import_wikidata.py --limit 100
make grammar
```

The build runs `generate_gf_lexicon.py`, producing GF abstract and English
lexicon modules for every imported author, generic works class, and named
work. The Haskell engine loads the same TSV, so parsing and semantic
certificates share entity identifiers.

Wikidata structured data is CC0. The snapshot is intentionally committed so
tests do not depend on a live SPARQL endpoint. `P800` records notable works,
not a complete bibliography; candidate coverage must not be interpreted as
exhaustive.

The automatic resolver also loads:

```text
data/predicates.tsv          argument types for verbs
data/verbnet-predicates.tsv  imported selectional preferences
data/verbnet-actions.tsv     sense-preserving VerbNet action identities
data/verbnet-action-roles.tsv  structured Action×Role requirements
data/semantic-entities.tsv   typed ontology nodes
data/semantic-relations.tsv  directed bridge edges
data/subsorts.tsv            ontology inheritance tree
```

## Scaling entity linking and evidence

The committed snapshots are deliberately small regression artifacts. For
open-domain coverage, use the explicit offline Wikidata runtime pipeline:

```bash
./scripts/download_wikidata_dump.sh \
  https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.json.bz2 \
  /data/wikidata/latest-all.json.bz2
python3 scripts/build_wikidata_runtime_index.py build \
  --dump /data/wikidata/latest-all.json.bz2 \
  --database /data/wikidata-runtime.sqlite
```

The database supports exact normalized label/alias lookup and materializes
bounded, hash-bound QID neighborhoods. It does not perform live API lookup
during inference, silently choose ambiguous names, or bypass the Agda checker.
See `docs/contextual-tower.md` for batch linker-cache and materialization
commands.

For every parsed `subject–verb–object` tree, it:

1. looks up the predicate's required subject and object types;
2. checks whether each supplied entity already inhabits its required type;
3. when it does not, searches outgoing ontology paths of bounded length;
4. retains endpoints that prove the required type through the subsort tree;
5. builds and verifies expansion certificates from those paths.

There are no verb-specific metonymy rules in this algorithm. For example,
`read`, `study`, `review`, and `translate` independently request
`Readable`; consequently they reuse the same author-to-work bridge.
`listen to`, `watch`, `eat`, and `wear` select different endpoint types and
therefore activate different bridges.

Adding a manually audited verb is a data operation: add its GF expression
and argument types to `data/predicates.tsv`, then run `make grammar`. The
open frontend also indexes every executable subject/object realization in
the pinned VerbNet Action×Role snapshot. Multiple senses are preserved and
searched rather than collapsed to one lemma-level row.

Refresh the pinned VerbNet snapshot:

```bash
./scripts/import_verbnet.py
make grammar
```

VerbNet restrictions are tendencies rather than logical impossibility
claims. Imported rows are therefore explicitly marked
`SelectionalPreference`, while manually audited entries may use
`HardRequirement`. Nested AND/OR and negative restrictions are preserved;
negative requirements use closed-world checking against the frozen local
ontology. See [data/SOURCES.md](data/SOURCES.md) for provenance,
licensing, and extraction policy.

## Formal model

`formal/Metonymy/Core.agda` defines:

```text
BridgePath     directed semantic transitions
Admissible     bridge evidence × contextual requirement
Fine           explicit meanings in one admissible fiber
Coarse         a higher-inductive quotient of that fiber
contract       Fine → Coarse
Expansion      the homotopy fiber of contract
Derivation     implicit and explicit grammatical derivations
metonymy       a path from the implicit to an explicit derivation
```

`formal/Metonymy/Soundness.agda` checks:

- admissible fine meanings have the same compressed image;
- the original fine meaning remains an expansion after contraction;
- metonymic paths are preserved by grammatical contexts.

`formal/Metonymy/Checker.agda` is the executable trusted kernel. It
independently checks:

```text
non-empty and connected bridge paths
existence of every ontology edge
predicate identity, argument sort, strength, and provenance
target typing through the imported subsort tree
```

The checker is compiled through MAlonzo and called through a generated,
stable project facade; numbered MAlonzo identifiers do not escape that
adapter. Candidates rejected by Agda are never emitted.
`RuntimeBridge.agda` proves:

```text
runtimeCheck KB beforeGF afterGF certificate = true
  → RuntimeAdmissible
  → HardCell
  → Path in Completion
  → equality in independent quotient semantics
```

Haskell search is therefore outside the trusted computing base: it proposes
certificates but cannot authorize one.

The strengthened publication-oriented development—raw grammar, directed
bridges, coherent 2-cells, witnessed compression, semantic factorization,
checker reflection, preference promotion, conservativity, and
non-collapse—is indexed in `formal/Metonymy/PublicationTheorems.agda`.
See [docs/mathematics.md](docs/mathematics.md) for the exact theorem-to-file
map and assumptions.

The self-contained formal source directory is
[`formal/Metonymy`](formal/Metonymy). Its publication-facing theorem index is
[`formal/Metonymy/THEOREMS.md`](formal/Metonymy/THEOREMS.md); verify all source
hashes and safe Agda checks with:

```bash
make formal-artifact
```

## Publication artifact

On the pinned Ubuntu 24.04 toolchain, reproduce theorem checking, GF
generation, the stable MAlonzo adapter, Haskell integration tests, and the
independent evaluation tests with:

```bash
make reproduce
```

CI runs the same command. Exact commits and artifact hashes are recorded in
[`toolchain.lock.json`](toolchain.lock.json); third-party terms are listed
in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). The paper-facing
claim map is [`docs/claims.md`](docs/claims.md).

## Open-domain GF elaboration

The GF grammar includes open proper-name/common-noun constructors and a
small audited family of open transitive predicates. When the closed grammar
cannot cover a corpus sentence, `Metonymy.OpenDomain` performs a
target-aware, construction-bounded elaboration into genuine GF constructor
names:

```text
Pred OpenSourceNP (Compl OpenAgentive OpenContextNP)
→
Pred OpenTargetNP (Compl OpenAgentive OpenContextNP)
```

The open frontend first finds the nearest VerbNet/local action realization,
infers subject or object from the marked target position, and runs the same
typed `expandFiber` search as the controlled GF path. Legacy lexical triggers
are untrusted ranking hints between type-compatible bridge paths, not the
primary search gate. `runtimeCheck` still checks the structured requirement,
GF terms, endpoint types, ontology edge, direction, and certificate.

Corpus batch inputs now carry a designated character span for the target
occurrence. Action matching and legacy path-ranking hints are bounded around
that span; an invalid or absent span fails closed. The endpoint layer first uses
an independently sourced, frozen linker cache when one exists (the included
CC0-style fixture resolves Moscow → Government of Russia), and otherwise
emits a generic class endpoint. WiMCor gold `fine` labels are never supplied
to the frontend.

```bash
./build/metonymy open-evaluate \
  full wimcor LOCATION Moscow "Moscow signed the agreement"
```

Historical hard family-trigger baseline results:

- WiMCor test (41,200): metonymic F1 `0.1895`, accuracy `0.7398`;
- ConMeC (5,999 valid): metonymic F1 `0.0961`, accuracy `0.6989`;
- SafeCon-Mini: precision `1.0`, recall `0.6667`, F1 `0.8`,
  unsafe-contraction rate `0`.

The integrated Action×Role search is deliberately stricter: WiMCor
metonymic F1 is `0.0518` and ConMeC metonymic F1 is `0.0220`. It discovers
many more VerbNet preferences but abstains unless they have promotion
evidence, instead of silently turning them into hard paths. Its frozen linker
recovers one exact WiMCor endpoint (`recall@1 = 0.000095`). These are
baseline, not state-of-the-art, claims; improving them requires dependency
bindings, independently sourced discourse evidence, and a substantially
larger entity linker. Gold remains physically separated from inference.

## Current scope

This is a formally checked GF extension with a deterministic open-domain
elaboration baseline, not a general semantic parser. The proof-producing
core combines hand-audited bridge schemas with a generated Wikidata entity
layer. WordNet and FrameNet can be additional adapters. VerbNet is already
imported as a preference source; no external source bypasses Agda
certificate checking.

Candidate ranking is intentionally deterministic in this slice. A future
statistical or LLM scorer may reorder already admissible candidates but
must not establish formal admissibility.

## Contextual QID fiber prototype

The contextual prototype computes a set-valued fiber over a frozen QID
snapshot. It preserves lexical origins for every constraint and applies them
in order; a candidate that does not extend to the next layer receives a
snapshot-relative obstruction rather than a fallback endpoint.

```bash
./build/metonymy contextual-fiber waterloo
./build/metonymy contextual-contract waterloo Q1049470
```

The second command is rejected on the Waterloo fixture: the physics layer
contains both `Q1049470` and `Q2004561`, so unique-fiber contraction is
unsafe. A later constraint that leaves a singleton licenses the reverse
path from that unique survivor back to the source QID.

The Waterloo fixture starts from `Q639408`, retains organization-compatible
institutions for `announce`, and then applies the lexical `physics` constraint
as `Conducts(_, Q413)`. It returns both University of Waterloo and Perimeter
Institute when their facts are present, while Waterloo City Council receives a
`MissingRelation` obstruction. This is a finite-snapshot result, not a claim
that the fiber is complete in Wikidata or that its surviving candidates are
semantically equal.

The full data flow, tower invariants, obstruction interpretation, and formal
witness map are documented in
[`docs/contextual-tower.md`](docs/contextual-tower.md). Additional scenarios
can be added as data rows in `data/contextual-scenarios.tsv`; the runtime and
scorer are not Waterloo-specific.

For the implemented independent scorer, SemEval adapter, five ablations,
separate expansion/contraction reporting, false-path analysis, and dataset
licensing policy, see [evaluation/README.md](evaluation/README.md) and
[docs/evaluation.md](docs/evaluation.md).
