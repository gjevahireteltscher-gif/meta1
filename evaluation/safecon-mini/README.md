# SafeCon-Mini 1.0

SafeCon-Mini is an independently authored contraction benchmark for the
proof-carrying metonymy prototype.

- 24 frozen test instances;
- 12 safe generic contractions;
- 12 matched unsafe named, restricted, or token-specific mentions;
- 16 controlled GF-overlap instances;
- 8 contextual open-domain instances.

Gold policy:

> Contraction is safe only when the explicit mention denotes the generic
> representative of the complete contextual fiber. It is unsafe when the
> mention preserves a named member, token, restricted subset, quantity,
> temporal subset, or other information unavailable after contraction.

The policy and dataset were authored before running the system. Runtime
code receives only `id` and `text`; gold fields are used solely by the
independent scorer.

Run:

```bash
python3 scripts/evaluation/safecon.py \
  --dataset evaluation/safecon-mini/dataset.jsonl \
  --engine build/metonymy \
  --predictions build/evaluation/safecon-predictions.jsonl \
  --report build/evaluation/safecon-report.json
```

Metrics are contraction precision, recall, F1, coverage, and unsafe
contraction rate. An abstention on an unsafe item is not counted as evidence
that the system understood why contraction was unsafe.

The runtime now also applies a fail-closed contextual gate before inverse
bridge search. It rejects restrictive modifiers, quantifiers, negation,
focus markers, anaphoric dependents, and temporal restrictions even when the
ontology target is generic. The same `ForgetContext` is embedded in the
runtime clause and raw certificate; Agda checks exact context binding and
reduces contextual safety before authorizing contraction. The theorem
fixture `quantifiedContractionRejected` machine-checks a negative case.

The benchmark text and annotations are released under CC0 1.0.
