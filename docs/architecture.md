# Architecture and trust boundaries

## Pipeline

### 1. Grammatical analysis

`grammar/Metonymy.gf` defines a compact abstract syntax.
`grammar/MetonymyEng.gf` is implemented with the standard GF English
Resource Grammar Library (`SyntaxEng` and `ParadigmsEng`). The RGL supplies
English inflection, agreement, noun phrase construction, parsing, and clause
linearization. GF parses surface text into abstract trees and regenerates
surface text after transformation.

GF deliberately uses the broad category `NP`. Semantic sorts such as
`Human`, `Readable`, and `Agent` belong to the elaboration layer.

The CLI accepts surface sentences. It asks GF for all abstract parses and
passes every `Pred subject (Compl verb object)` tree to the generic
type-directed resolver. Scenario identifiers remain only for regression
tests and debugging; free-text resolution does not select a predeclared
metonymy scenario.

For corpus evaluation, the open-GF elaborator is target-aware and
construction-bounded. It maps unknown lexical material to the declared
`OpenSourceNP`, `OpenTargetNP`, and `OpenContextNP` constructors. The marked
target position is paired with the nearest matching local or VerbNet action
realization to infer `SubjectHole` or `ObjectHole`; every compatible sense is
then passed to the generic typed fiber search. This is not an unrestricted
dependency parser: coordination, passives, and long-distance dependencies
remain fail-closed or heuristic. Legacy lexical triggers only rank
type-compatible bridge paths.

An alternative frontend, `analyzeOpenAtWithDependencyHint`, replaces this
positional heuristic with an offline Universal Dependencies parse
(`scripts/annotate_dependency_hints.py`) for locating the governing verb and
determining subject/object role, rather than comparing character offsets.
It is exactly as untrusted as the legacy frontend: it only ever proposes a
candidate, and `runtimeCheck` re-derives admissibility identically for
either frontend's output. It abstains explicitly, rather than guessing,
when the target is a modifier nested inside a noun phrase (e.g. the
possessor in "Tolstoy's books") rather than a direct clause argument —
correctly resolving that case requires widening the checked construction
vocabulary below, which remains future work. A parser failure on a given
sentence falls back to the legacy frontend for that sentence, so a
dependency-frontend run is never worse than the legacy baseline on
sentences the parser cannot handle. See `evaluation/README.md` for the
parallel evaluation pipeline and `data/SOURCES.md` for parser/model
provenance and licensing.

### 2. Semantic elaboration

`Metonymy.Types` associates each predicate argument with a `Requirement`.
For example:

```text
Read.object = HasSort Readable
Sign.subject = HasSort Agent
```

A `HoleRole` identifies whether the metonymic phrase fills the subject or
object position. The same resolution engine therefore handles both
`read Tolstoy` and `Moscow signs the agreement`.

The production predicate table combines manually audited
`data/predicates.tsv` entries with generated
`data/verbnet-predicates.tsv` entries. `Metonymy.Automatic` compares both
supplied arguments with their requested types. It launches bridge search
only at positions whose literal entity does not already prove the
requirement or preference.

Manual requirements and imported VerbNet preferences remain distinguished
by `RequirementStrength`. VerbNet tendencies can propose and rank a
metonymic path, but are not represented as claims that all other objects are
grammatically impossible. Requirements support nested `AllOf`, `AnyOf`, and
`Not`; the Agda checker evaluates the same structure. Negative requirements
use a closed-world interpretation over the frozen knowledge base. Every
action sense and role stores its source provenance.

### 3. Proof-producing ontology

`Metonymy.Ontology` stores:

- named entities and their GF terms;
- typed assertions with provenance;
- relation assertions with provenance;
- subsort rules.

`proveRequirement` returns a `Proof`, not a Boolean. Derived type evidence
retains the rule and premise provenance.

External knowledge sources should be translated into these assertions:

```text
WordNet/RuWordNet → lexical sorts and subsort rules
FrameNet/VerbNet  → predicate requirements and semantic roles
Wikidata          → named relation assertions
discourse         → temporary assertions and salience
```

Small regression fixtures remain in `Metonymy.Examples`. Larger entity and
predicate layers are loaded from
`data/wikidata-author-works.tsv`; `Metonymy.Data` turns each row into:

```text
author       : Writer
named work   : LiteraryWork
generic works class : LiteraryWork
author --Authored--> named work
author --Authored--> generic works class
```

The same snapshot generates `GeneratedMetonymy.gf` and
`GeneratedMetonymyEng.gf`. GF and the semantic engine therefore share
Wikidata QIDs instead of attempting label-based joins at runtime.

`semantic-entities.tsv` and `semantic-relations.tsv` exercise additional
ontology branches:

```text
Mozart    --Created--> MusicalWork --subsort--> Audible
Spielberg --Created--> Film        --subsort--> Watchable
plate     --Contains--> Food       --subsort--> Edible
Chanel    --ProducedBy--> Clothing --subsort--> Wearable
```

The arrows marked `subsort` are loaded from `data/subsorts.tsv`; adding an
ontology inheritance edge does not require recompiling the Haskell source.

### 4. Fiber search

`Metonymy.Resolution.expandFiber` evaluates:

```text
Σ y.
  BridgePath(source,y)
  × Requirement(hole,y)
```

Search is bounded by `fiberMaxDepth`, tracks visited entities, and pushes
the type requirement onto each endpoint. Automatic resolution currently
uses paths of at most two bridge edges.

### 5. Expansion

Expansion fixes the coarse source and enumerates admissible fine targets:

```text
Tolstoy --Authored--> works-of-tolstoy : Readable
Tolstoy --Authored--> war-and-peace    : Readable
Tolstoy --Authored--> anna-karenina    : Readable
```

The generic target receives the highest deterministic score. A contextual
ranker can later prefer a named work without changing validity.

### 6. Contraction

Contraction performs the inverse graph query: it fixes an explicit target
and searches incoming bridge paths. Graph reversibility does not imply
safe linguistic contraction.

The Haskell `certificateSafeToForget` precheck permits generic class
representatives and rejects named works. The Agda `runtimeCheck`
independently re-derives this condition by requiring the contraction target
to inhabit `GenericReading`. It also checks structured flags for
quantification, restrictive modification, polarity, focus, anaphora, and
temporal restriction. Those flags are supplied by the frontend: the checker
proves safety relative to them, not that they were correctly extracted from
arbitrary English syntax.

### 7. Certificate verification

Haskell `verifyCertificate` is a non-authoritative fast precheck. The
runtime then converts the complete KB, predicate table, lexeme/entity
bindings, source and target GF clauses, direction, and raw certificate to
the types generated from `Metonymy.Checker` and invokes the MAlonzo
function compiled from Agda.

The Agda kernel independently checks:

- that the bridge starts and ends at the claimed entities;
- every step exists in the knowledge base;
- that the path is non-empty and connected;
- the target still inhabits the hole requirement.
- predicate identity, selected argument type, strength, and provenance.
- source/target GF functions denote the certificate endpoints;
- the predicate and unchanged argument agree in both trees;
- contraction forgets only a checked generic reading.

Hard search results are untrusted until `runtimeCheck` succeeds. Preference
results use `preferenceRuntimeCheck` and remain candidate-only until
`checkPromotion` validates matching target salience with non-empty
discourse provenance.

### 8. Cubical interpretation

`formal/Metonymy/Core.agda` is the mathematical kernel:

```text
Fine Γ K x
  = Σ y. Admissible Γ K x y

Coarse Γ K x
  = Fine Γ K x / SameMetonymicClass

Expansion coarse
  = Σ fine. contract fine = coarse
```

The quotient path constructor glues admissible fine meanings only after
compression. It never asserts equality between the original entities.

`Derivation` is a higher-inductive type with:

```text
implicit
explicit y certificate
metonymy y certificate : implicit = explicit y certificate
```

`Checker.agda` implements the decidable certificate checker.
`EndToEnd.agda` proves that `check kb raw ≡ true` constructs an
`Admissible kb raw` witness and hence a path between the corresponding
implicit and explicit derivations. The executable checker is compiled
through MAlonzo and called directly by Haskell.

## Trust model

Formally checked:

- the definition of the quotient and its path constructor;
- contraction round-trip membership;
- compositional propagation of a metonymic path;
- runtime certificate consistency against the loaded knowledge base;
- rejection of forged targets, relations, requirements, provenance, and
  empty paths.

Not formally claimed:

- completeness of the knowledge base;
- linguistic correctness of external facts;
- uniqueness of a metonymic reading;
- optimality of candidate ranking;
- safety of arbitrary open-domain contraction.

This boundary prevents a statistical scorer from inventing a path, while
avoiding the false claim that type checking alone resolves pragmatics.
