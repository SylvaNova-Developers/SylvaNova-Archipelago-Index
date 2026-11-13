#!/usr/bin/env bash
# Regression: shard runner fuzzes every assigned world and exits 1 if any failed.
set -euo pipefail

CASE_DIR="$(mktemp -d)"
trap 'rm -rf "$CASE_DIR"' EXIT

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cat > "$CASE_DIR/run_fuzz_variant.sh" <<'EOF'
#!/usr/bin/env bash
echo "ran:$APWORLD_NAME" >> "$CASE_LOG"
[ "$APWORLD_NAME" != "bad" ]
EOF
chmod +x "$CASE_DIR/run_fuzz_variant.sh"

cat > "$CASE_DIR/fuzz_shard.py" <<'EOF'
#!/usr/bin/env python3
import json, sys
worlds = json.loads(sys.argv[2])
for w in worlds:
    print(w)
EOF
chmod +x "$CASE_DIR/fuzz_shard.py"

cat > "$CASE_DIR/run_fuzz_shard.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mapfile -t WORLDS < <(python3 "$SCRIPT_DIR/fuzz_shard.py" x "$WORLDS_JSON")
shard_failures=0
for world in "${WORLDS[@]}"; do
  export APWORLD_NAME="$world"
  export VARIANT=baseline INDEX_ROOT=.
  if ! "$SCRIPT_DIR/run_fuzz_variant.sh"; then
    shard_failures=$((shard_failures + 1))
  fi
done
[ "$shard_failures" -eq 0 ]
EOF
chmod +x "$CASE_DIR/run_fuzz_shard.sh"

export CASE_LOG="$CASE_DIR/ran.log"
export WORLDS_JSON='["good1","bad","good2"]'
touch "$CASE_LOG"

set +e
"$CASE_DIR/run_fuzz_shard.sh"
status=$?
set -e

if [ "$status" -eq 0 ]; then
  echo "expected nonzero exit" >&2
  exit 1
fi

grep -q 'ran:good1' "$CASE_LOG"
grep -q 'ran:bad' "$CASE_LOG"
grep -q 'ran:good2' "$CASE_LOG" || {
  echo "good2 never fuzzed (fail-fast regression)" >&2
  cat "$CASE_LOG"
  exit 1
}

echo "test_run_fuzz_shard_aggregate: ok"
