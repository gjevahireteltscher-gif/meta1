# Contextual Multi-Domain evaluation

This artifact contains two physically separated evaluation strata:

- `silver-inputs.jsonl` / `silver-gold.jsonl`: deterministically generated from
  the frozen graph and type projections. This stratum tests implementation
  coverage, stage monotonicity, obstruction accounting, and Haskell/Agda
  agreement. It is not independent linguistic gold.
- `audited-inputs.jsonl` / `audited-gold.jsonl`: a small manually reviewed
  regression set covering author-for-work, location-for-institution,
  commercial/political adjective composition, topic-constrained
  institutional readings, unique-fiber contraction, and rejected unsafe
  contraction.

Inference receives only the input file. Gold is supplied later to the
independent scorer.

```bash
python3 scripts/evaluation/run_contextual_corpus.py \
  --dataset evaluation/contextual-multidomain/silver-inputs.jsonl \
  --engine build/metonymy \
  --snapshot data/wikidata-openalex-snapshot \
  --output build/evaluation/contextual-silver-inference.jsonl

python3 scripts/evaluation/score_qid_fibers.py \
  --inference build/evaluation/contextual-silver-inference.jsonl \
  --gold evaluation/contextual-multidomain/silver-gold.jsonl \
  --output build/evaluation/contextual-silver-report.json
```

The evaluated claim is finite-snapshot membership and exact reproduction of
the audited set. It is not completeness of Wikidata, WordNet, OpenAlex, or
arbitrary English interpretation.

## Recorded results

The frozen silver corpus contains 69 instances: 49 expansions and 20
contractions across one author-for-work pair and the location-for-institution
variants. All 69 reproduce the graph-derived target set exactly, including
20/20 contraction cases (12 unique-fiber acceptances and 8 unsafe
rejections). Non-empty gold hits are 34/34; all 35 expected-empty fibers
remain empty. Cardinalities are: 35 empty, 26 singleton, six of size two,
and two of size three. The tower records 47 `MissingRequirement`
obstructions.

The separately reviewed nine-instance set also reproduces all nine fibers
exactly: 6/6 non-empty gold hits, 9/9 QID micro recall, 5/5 expansions,
4/4 contractions, and 3/3 expected-empty fibers. This set is a regression
artifact, not yet a statistically meaningful external benchmark. A
publication should report it alongside—not instead of—the existing
WiMCor/ConMeC external results.
