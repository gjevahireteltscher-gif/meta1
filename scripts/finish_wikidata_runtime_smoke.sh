#!/usr/bin/env bash
set -euo pipefail

# Runs after the full offline index exists. Does not require the dump itself.
# The certified runtime artifact remains a bounded snapshot, not runtime.sqlite.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${WIKIDATA_CACHE:-$HOME/.cache/metonymy/wikidata}"
DB="${WIKIDATA_RUNTIME_DB:-$CACHE/runtime.sqlite}"
INDEX_LOG="${WIKIDATA_INDEX_LOG:-$ROOT/build/wikidata-runtime-index.log}"
STATUS="${WIKIDATA_SMOKE_STATUS:-$ROOT/build/wikidata-runtime-smoke.json}"
SNAPSHOT="${WIKIDATA_SMOKE_SNAPSHOT:-$ROOT/build/wikidata-qid-snapshot}"
LINKER="${WIKIDATA_SMOKE_LINKER:-$ROOT/build/evaluation/wikidata-linker-cache.json}"
WAIT_PID="${WIKIDATA_INDEX_PID:-}"

mkdir -p "$ROOT/build/evaluation"

if [[ -n "$WAIT_PID" ]]; then
  while kill -0 "$WAIT_PID" 2>/dev/null; do
    sleep 60
  done
fi

if [[ ! -s "$DB" ]]; then
  printf '{"status":"failed","reason":"missing-runtime-sqlite"}\n' > "$STATUS"
  exit 1
fi

if [[ -f "$INDEX_LOG" ]] && rg -q '^exit=[1-9]' "$INDEX_LOG"; then
  printf '{"status":"failed","reason":"index-nonzero-exit"}\n' > "$STATUS"
  exit 1
fi

python3 "$ROOT/scripts/build_wikidata_runtime_index.py" lookup \
  --database "$DB" \
  --alias Waterloo > "$ROOT/build/wikidata-lookup-waterloo.json"

python3 "$ROOT/scripts/build_wikidata_runtime_index.py" materialize \
  --database "$DB" \
  --source-qid Q639408 \
  --source-qid Q1049470 \
  --source-qid Q2004561 \
  --source-qid Q7974219 \
  --source-qid Q413 \
  --depth 2 \
  --rules "$ROOT/data/wikidata-runtime-rules.json" \
  --output "$SNAPSHOT"

python3 "$ROOT/scripts/build_wikidata_linker_cache.py" \
  --database "$DB" \
  --inputs "$ROOT/evaluation/contextual-multidomain/audited-inputs.jsonl" \
  --output "$LINKER"

python3 "$ROOT/scripts/run_automatic_contextual_pipeline.py" \
  --engine "$ROOT/build/metonymy" \
  --snapshot "$SNAPSHOT" \
  --sentence "Waterloo announced a programme in physics" \
  --source Waterloo \
  > "$ROOT/build/wikidata-runtime-waterloo.txt"

python3 - <<PY
import json
from pathlib import Path
root = Path("$ROOT")
lookup = json.loads((root / "build/wikidata-lookup-waterloo.json").read_text())
linker = json.loads(Path("$LINKER").read_text())
manifest = json.loads((Path("$SNAPSHOT") / "manifest.json").read_text())
tower = (root / "build/wikidata-runtime-waterloo.txt").read_text()
status = {
    "status": "ok",
    "database": "$DB",
    "lookup_waterloo_ids": [row["id"] for row in lookup.get("matches", [])],
    "snapshot_graph_sha256": manifest.get("graph_sha256"),
    "snapshot_index_sha256": manifest.get("source", {}).get("index_sha256"),
    "linker_resolved": linker.get("counts", {}).get("resolved"),
    "linker_ambiguous": linker.get("counts", {}).get("ambiguous"),
    "linker_unresolved": linker.get("counts", {}).get("unresolved"),
    "waterloo_survivors_present": "survivors=[Q1049470,Q2004561]" in tower,
    "waterloo_agda_checks": tower.count("agda-layer-check=true"),
}
Path("$STATUS").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
print(json.dumps(status, indent=2, sort_keys=True))
PY
