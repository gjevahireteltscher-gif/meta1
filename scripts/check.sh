#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CUBICAL_DIR="${CUBICAL_LIB:-$HOME/.cache/metonymy/cubical-v0.5}"
RGL_DIR="${RGL_LIB:-$HOME/.cache/metonymy/gf-rgl-lib}"

if [[ ! -f "$CUBICAL_DIR/cubical.agda-lib" ]]; then
  echo "Cubical library not found at $CUBICAL_DIR" >&2
  echo "Run ./scripts/bootstrap.sh first." >&2
  exit 1
fi

if [[ ! -f "$RGL_DIR/alltenses/SyntaxEng.gfo" ]]; then
  echo "English GF Resource Grammar not found at $RGL_DIR" >&2
  echo "Run ./scripts/bootstrap.sh first." >&2
  exit 1
fi

cd "$ROOT"

make test CUBICAL_LIB="$CUBICAL_DIR" RGL_LIB="$RGL_DIR"
