# Independent ConMeC-300 test selection

This is a frozen 300-instance evaluation selection from the independently
annotated ConMeC corpus. It contains 25 hash-ranked examples for every
`category × {literal, metonymic}` stratum across the six ConMeC categories.
The selection was made by stable ID hashing, not model output.

Corpus text is not committed. The manifest records source rows and content
hashes. Reproduce the local, physically separated inputs and gold files:

```bash
curl --fail --location \
  "https://raw.githubusercontent.com/SaptGhosh/ConMeC/ec6914770b86eb82347724e22c7b627598644ba4/DATASET.csv" \
  --output /tmp/conmec.csv

python3 scripts/evaluation/prepare_conmec.py \
  --csv /tmp/conmec.csv \
  --output build/evaluation/conmec.combined.jsonl \
  --quarantine build/evaluation/conmec-quarantine.json

python3 scripts/evaluation/select_independent_300.py \
  --combined build/evaluation/conmec.combined.jsonl \
  --selection-manifest evaluation/independent-conmec-300/selection-manifest.json \
  --output-dir build/evaluation/independent-conmec-300
```

The labels were produced by ConMeC annotators and are independent of this
system's rules and snapshots. This does not make endpoint-QID evaluation
independent: ConMeC supplies metonymy and category labels, not explicit entity
expansion targets.

## Recorded result

The full condition covers 115/300 instances (`0.3833`) with selective
accuracy `0.5304`. Metonymic recall is `0.0067` (1/150) and metonymic F1 is
`0.0130`. These independently annotated results are deliberately retained
despite being weak: the expanded formal machinery does not by itself solve
open-domain frame selection or entity linking. See `result-summary.json`.
