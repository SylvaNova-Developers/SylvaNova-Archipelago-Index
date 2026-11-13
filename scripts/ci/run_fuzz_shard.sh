#!/usr/bin/env bash
# Run one fuzz variant for all apworlds assigned to a matrix shard (CI).
#
# Env:
#   WORLDS_JSON   JSON array of changed world ids (discover output)
#   SHARD         matrix shard index
#   VARIANT       fuzz variant name (see run_fuzz_variant.sh)
#   INDEX_ROOT    index repo checkout
set -euo pipefail

: "${WORLDS_JSON:?WORLDS_JSON required}"
: "${SHARD:?SHARD required}"
: "${VARIANT:?VARIANT required}"
INDEX_ROOT="${INDEX_ROOT:-$(pwd)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mapfile -t WORLDS < <(
  python3 "$SCRIPT_DIR/fuzz_shard.py" --worlds-json "$WORLDS_JSON" --shard "$SHARD"
)

if [ "${#WORLDS[@]}" -eq 0 ]; then
  echo "No worlds for shard=$SHARD; nothing to fuzz"
  exit 0
fi

chmod +x "$SCRIPT_DIR"/*.sh
shard_failures=0
for world in "${WORLDS[@]}"; do
  echo "=== shard=$SHARD variant=$VARIANT world=$world ==="
  export APWORLD_NAME="$world"
  export VARIANT
  export INDEX_ROOT
  if ! "$SCRIPT_DIR/run_fuzz_variant.sh"; then
    shard_failures=$((shard_failures + 1))
    echo "::error::shard=$SHARD variant=$VARIANT world=$world fuzz failed" >&2
  fi
done

if [ "$shard_failures" -gt 0 ]; then
  echo "::error::shard=$SHARD variant=$VARIANT: $shard_failures of ${#WORLDS[@]} world(s) failed" >&2
  exit 1
fi
