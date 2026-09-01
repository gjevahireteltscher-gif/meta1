#!/usr/bin/env bash
# Opt-in installer for the UD dependency-parser frontend
# (scripts/annotate_dependency_hints.py). This is a research/evaluation-only
# preprocessor for the open-domain corpus frontend, not part of the
# certified Agda/GF pipeline: scripts/bootstrap.sh and make test/verify do
# not call this script, so the base reproducibility guarantee never depends
# on network access to PyPI or Stanza's model registry.
#
# Pinned versions live in toolchain.lock.json under "stanza". Re-run this
# script after a toolchain.lock.json update to pick up a new pin.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE_DIR="${STANZA_CACHE_DIR:-$HOME/.cache/metonymy/stanza}"
LOCK_FILE="$ROOT/toolchain.lock.json"

lock_field() {
  python3 -c '
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["stanza"][sys.argv[2]])
' "$LOCK_FILE" "$1"
}

STANZA_VERSION="$(lock_field package_version)"
STANZA_SDIST_SHA256="$(lock_field sdist_sha256)"
UD_PACKAGE="$(lock_field ud_package)"

mkdir -p "$CACHE_DIR/dist"

echo "Installing stanza==$STANZA_VERSION (pinned in toolchain.lock.json)" >&2
python3 -m pip install --no-deps "stanza==$STANZA_VERSION"

echo "Fetching stanza==$STANZA_VERSION sdist to verify its checksum" >&2
python3 -m pip download --no-deps --no-binary :all: \
  -d "$CACHE_DIR/dist" "stanza==$STANZA_VERSION"
DOWNLOADED_SDIST="$CACHE_DIR/dist/stanza-$STANZA_VERSION.tar.gz"
ACTUAL_SDIST_SHA256="$(sha256sum "$DOWNLOADED_SDIST" | cut -d' ' -f1)"
if [[ "$ACTUAL_SDIST_SHA256" != "$STANZA_SDIST_SHA256" ]]; then
  printf 'stanza sdist sha256 mismatch: expected %s, got %s\n' \
    "$STANZA_SDIST_SHA256" "$ACTUAL_SDIST_SHA256" >&2
  exit 1
fi

echo "Downloading Stanza '$UD_PACKAGE' English UD models to $CACHE_DIR/models" >&2
python3 -c "
import stanza
stanza.download('en', package='$UD_PACKAGE', model_dir='$CACHE_DIR/models',
                 processors='tokenize,mwt,pos,lemma,depparse')
"
# stanza.download verifies each downloaded model file's MD5 against the
# resources manifest for the installed package version before accepting it
# (see toolchain.lock.json's "stanza".note) — no separate check is
# duplicated here.

cat >&2 <<EOF
Dependency-hint frontend ready.

Run it with:
  STANZA_MODEL_DIR="$CACHE_DIR/models" python3 scripts/annotate_dependency_hints.py \\
    --dataset build/evaluation/<dataset>.inputs.jsonl \\
    --output build/evaluation/<dataset>.dependency-hints.jsonl
EOF
