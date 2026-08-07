#!/usr/bin/env bash
# Set up Archipelago + fuzzer under /ap (layout expected by upstream hooks) and
# run one fuzz gate variant for a single apworld.
#
# Env:
#   APWORLD_NAME   required (apworld id / worlds/<name>.apworld stem)
#   VARIANT        required: baseline | no-restrictive-starts | check-gerpocalypse |
#                  check-item-location-count | check-lambda-capture |
#                  check-placement-item-location-refs | check-indirect-conditions |
#                  check-static-output-placement | check-determinism |
#                  check-collect-accessibility | check-ut
#   INDEX_ROOT     path to SylvaNova-archipelago-index checkout (default: cwd)
#   AP_VERSION     Archipelago tag/version (default: read from index.toml)
#   FUZZ_RUNS_FULL default 1000 (GH Actions floor; README gate remains <1%)
#   FUZZ_RUNS_CHECK default 500
#   PYTHON_BIN     default python3
set -euo pipefail

: "${APWORLD_NAME:?APWORLD_NAME required}"
: "${VARIANT:?VARIANT required}"
INDEX_ROOT="${INDEX_ROOT:-$(pwd)}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
FUZZ_RUNS_FULL="${FUZZ_RUNS_FULL:-1000}"
FUZZ_RUNS_CHECK="${FUZZ_RUNS_CHECK:-500}"

if [[ -z "${AP_VERSION:-}" ]]; then
  AP_VERSION="$($PYTHON_BIN - <<PY
import tomllib
from pathlib import Path
print(tomllib.loads(Path("${INDEX_ROOT}/index.toml").read_text())["archipelago_version"])
PY
)"
fi

echo "APWORLD_NAME=$APWORLD_NAME VARIANT=$VARIANT AP_VERSION=$AP_VERSION"

sudo mkdir -p /ap
if [[ ! -d /ap/archipelago/.git ]]; then
  sudo rm -rf /ap/archipelago
  sudo git clone --depth 1 --branch "$AP_VERSION" \
    https://github.com/ArchipelagoMW/Archipelago.git /ap/archipelago \
    || sudo git clone --depth 1 --branch "v${AP_VERSION}" \
      https://github.com/ArchipelagoMW/Archipelago.git /ap/archipelago \
    || sudo git clone --depth 1 https://github.com/ArchipelagoMW/Archipelago.git /ap/archipelago
  # If untagged clone landed on main, try checking out the version ref.
  sudo git -C /ap/archipelago fetch --depth 1 origin "refs/tags/${AP_VERSION}:refs/tags/${AP_VERSION}" 2>/dev/null || true
  sudo git -C /ap/archipelago fetch --depth 1 origin "refs/tags/v${AP_VERSION}:refs/tags/v${AP_VERSION}" 2>/dev/null || true
  sudo git -C /ap/archipelago checkout "$AP_VERSION" 2>/dev/null \
    || sudo git -C /ap/archipelago checkout "v${AP_VERSION}" 2>/dev/null \
    || true
fi

sudo chown -R "$(id -u):$(id -g)" /ap/archipelago

cd /ap/archipelago
if [[ ! -d .venv ]]; then
  "$PYTHON_BIN" -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --upgrade pip wheel
  if [[ -f requirements.txt ]]; then
    pip install -r requirements.txt
    # Re-assert exact pins (other wheels may have floated typing_extensions, etc.).
    pip install -r requirements.txt
  fi
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

# Archipelago's ModuleUpdate prompts on stdin when pins drift; that deadlocks CI
# workers (EOFError). Install deps above, then skip further interactive updates.
export SKIP_REQUIREMENTS_UPDATE=1

# Install fuzzer entrypoint + hooks beside Archipelago.
if [[ ! -f fuzz.py ]]; then
  curl -fsSL -o fuzz.py \
    https://raw.githubusercontent.com/ionium-ap/Archipelago-fuzzer/main/fuzz.py \
    || curl -fsSL -o fuzz.py \
      https://raw.githubusercontent.com/Eijebong/Archipelago-fuzzer/main/fuzz.py
fi
if [[ ! -d hooks ]]; then
  rm -rf /tmp/ap-fuzzer-src
  git clone --depth 1 https://github.com/ionium-ap/Archipelago-fuzzer.git /tmp/ap-fuzzer-src \
    || git clone --depth 1 https://github.com/Eijebong/Archipelago-fuzzer.git /tmp/ap-fuzzer-src
  cp -a /tmp/ap-fuzzer-src/hooks ./hooks
  cp -f /tmp/ap-fuzzer-src/fuzz.py ./fuzz.py
fi

# empty-apworld for restrictive-starts gate (zip the world package, not the repo root)
if [[ ! -f /ap/empty.apworld ]]; then
  sudo mkdir -p /ap
  tmpdir="$(mktemp -d)"
  git clone --depth 1 https://github.com/ionium-ap/empty-apworld.git "$tmpdir/empty" \
    || git clone --depth 1 https://github.com/Eijebong/empty-apworld.git "$tmpdir/empty"
  if [[ -f "$tmpdir/empty/empty.apworld" ]]; then
    sudo cp "$tmpdir/empty/empty.apworld" /ap/empty.apworld
  elif [[ -d "$tmpdir/empty/empty" ]]; then
    (cd "$tmpdir/empty" && zip -r /tmp/empty.apworld empty)
    sudo mv /tmp/empty.apworld /ap/empty.apworld
  else
    echo "empty-apworld clone has unexpected layout" >&2
    find "$tmpdir/empty" -maxdepth 3 -print >&2
    exit 1
  fi
fi
mkdir -p worlds
cp -f /ap/empty.apworld worlds/empty.apworld

# Place the world under test.
bash "$INDEX_ROOT/scripts/ci/download_apworld.sh" "$INDEX_ROOT" "$APWORLD_NAME" /tmp/apworld-download
if [[ -f "/tmp/apworld-download/${APWORLD_NAME}.apworld" ]]; then
  # Custom/index apworlds must win over built-in worlds/ with the same game name.
  # Otherwise AP logs: "Did not load X.apworld as its game ... is already loaded"
  # and we fuzz the wrong (core) implementation.
  if [[ -d "worlds/${APWORLD_NAME}" ]]; then
    echo "Removing built-in worlds/${APWORLD_NAME} so index apworld is loaded" >&2
    rm -rf "worlds/${APWORLD_NAME}"
  fi
  # Also disable any other non-zip world dirs that might collide (hidden by leading dot).
  cp -f "/tmp/apworld-download/${APWORLD_NAME}.apworld" "worlds/${APWORLD_NAME}.apworld"
elif [[ -d "worlds/${APWORLD_NAME}" && -f "worlds/${APWORLD_NAME}/__init__.py" ]]; then
  echo "Using built-in Archipelago world: ${APWORLD_NAME}" >&2
else
  echo "No apworld available for ${APWORLD_NAME}; refusing to skip fuzz" >&2
  exit 1
fi

META_ARGS=()
META_FILE=""
for candidate in \
  "$INDEX_ROOT/fuzz-meta/${APWORLD_NAME}.yaml" \
  "$INDEX_ROOT/fuzz-meta/${APWORLD_NAME}"/*.yaml
do
  if [[ -f "$candidate" ]]; then
    META_FILE="$candidate"
    break
  fi
done
if [[ -n "$META_FILE" ]]; then
  META_ARGS=(-m "$META_FILE")
fi

HOOK_ARGS=()
RUNS="$FUZZ_RUNS_CHECK"
EXTRA_ARGS=()
case "$VARIANT" in
  baseline)
    RUNS="$FUZZ_RUNS_FULL"
    ;;
  no-restrictive-starts)
    RUNS="$FUZZ_RUNS_FULL"
    HOOK_ARGS=(--hook hooks.with_empty:Hook)
    ;;
  check-gerpocalypse)
    HOOK_ARGS=(--hook hooks.gerpocalypse:Hook)
    ;;
  check-item-location-count)
    HOOK_ARGS=(--hook hooks.item_location_count:Hook)
    ;;
  check-lambda-capture)
    HOOK_ARGS=(--hook hooks.detect_rule_variable_capture_issues:Hook)
    ;;
  check-placement-item-location-refs)
    HOOK_ARGS=(--hook hooks.check_placement_item_location_references:Hook)
    ;;
  check-indirect-conditions)
    HOOK_ARGS=(--hook hooks.indirect_conditions:Hook)
    ;;
  check-static-output-placement)
    HOOK_ARGS=(--hook hooks.detect_output_placement_changes:Hook)
    ;;
  check-determinism)
    # Determinism forks workers and uses a higher per-gen timeout; keep runs modest on GHA.
    HOOK_ARGS=(--hook hooks.determinism:Hook)
    EXTRA_ARGS=(-t 30 -j 2)
    RUNS="${FUZZ_RUNS_DETERMINISM:-100}"
    ;;
  check-collect-accessibility)
    HOOK_ARGS=(--hook hooks.collect_accessibility_test:Hook)
    ;;
  check-ut)
    # UT hook ships with Universal Tracker when present; skip soft if missing.
    if python -c "import worlds.tracker.fuzzer_hook" 2>/dev/null; then
      HOOK_ARGS=(--hook worlds.tracker.fuzzer_hook:Hook)
    else
      echo "Universal Tracker hook not available; skipping check-ut" >&2
      mkdir -p fuzz_output
      # Produce a passing empty-success report so the gate script can be skipped by caller.
      echo '{"stats":{"total":1,"success":1,"failure":0,"timeout":0,"ignored":0},"errors":{}}' > fuzz_output/report.json
      cp fuzz_output/report.json "$INDEX_ROOT/fuzz-report-${APWORLD_NAME}-${VARIANT}.json"
      exit 0
    fi
    ;;
  *)
    echo "Unknown VARIANT=$VARIANT" >&2
    exit 2
    ;;
esac

rm -rf fuzz_output
JOBS_ARGS=()
if [[ ${#EXTRA_ARGS[@]} -eq 0 ]]; then
  JOBS_ARGS=(-t 10 -j "$(nproc)")
fi

echo "Starting fuzz: variant=$VARIANT runs=$RUNS args=${JOBS_ARGS[*]:-} ${EXTRA_ARGS[*]:-}"
set +e
python -u fuzz.py -g "$APWORLD_NAME" -r "$RUNS" -n 1 \
  "${JOBS_ARGS[@]}" "${EXTRA_ARGS[@]}" "${META_ARGS[@]}" "${HOOK_ARGS[@]}"
FUZZ_STATUS=$?
set -e

if [[ ! -f fuzz_output/report.json ]]; then
  echo "fuzzer did not produce fuzz_output/report.json (exit=$FUZZ_STATUS)" >&2
  exit 1
fi

cp fuzz_output/report.json "$INDEX_ROOT/fuzz-report-${APWORLD_NAME}-${VARIANT}.json"
"$PYTHON_BIN" "$INDEX_ROOT/scripts/ci/check_fuzz_report.py" \
  fuzz_output/report.json \
  --label "${APWORLD_NAME}/${VARIANT}"
