#!/usr/bin/env bash
set -euo pipefail

# Download only when explicitly invoked. The entity dump is currently ~103 GB
# compressed, so it is intentionally not part of Cloud Agent install/CI.
URL="${1:-https://dumps.wikimedia.org/wikidatawiki/entities/latest-all.json.bz2}"
OUTPUT="${2:-${WIKIDATA_DUMP:-$HOME/.cache/metonymy/wikidata/latest-all.json.bz2}}"

mkdir -p "$(dirname "$OUTPUT")"
curl --fail --location --continue-at - --retry 5 --retry-all-errors \
  "$URL" --output "$OUTPUT"
sha256sum "$OUTPUT" > "${OUTPUT}.sha256"
printf 'downloaded=%s\nsha256_file=%s\n' "$OUTPUT" "${OUTPUT}.sha256"
