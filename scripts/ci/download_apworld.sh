#!/usr/bin/env bash
# Download the latest URL version of an apworld from its index toml into DEST.
# Usage: download_apworld.sh <index-repo-root> <apworld-name> <dest-dir>
set -euo pipefail

ROOT="${1:?index repo root}"
NAME="${2:?apworld name}"
DEST="${3:?destination directory}"
TOML="$ROOT/index/${NAME}.toml"

if [[ ! -f "$TOML" ]]; then
  echo "missing $TOML" >&2
  exit 2
fi

mkdir -p "$DEST"

python3 - "$TOML" "$NAME" "$DEST" <<'PY'
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

toml_path, name, dest = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
if data.get("supported") is True:
    print(f"{name} is a supported/core world; nothing to download")
    sys.exit(0)

versions = data.get("versions") or {}
if not versions:
    raise SystemExit(f"{name}: no versions")

# Prefer highest semver-ish key; fall back to lexicographic.
def version_key(v: str):
    parts = []
    for piece in v.split("."):
        try:
            parts.append((0, int(piece)))
        except ValueError:
            parts.append((1, piece))
    return parts

latest = sorted(versions.keys(), key=version_key)[-1]
src = versions[latest] or {}
if "local" in src:
    raise SystemExit(f"{name}@{latest} is local-only; CI cannot download it")
if "url" in src:
    url = src["url"]
else:
    default_url = data.get("default_url")
    if not default_url:
        raise SystemExit(f"{name}@{latest}: no url")
    url = default_url.replace("{{version}}", latest)

out = dest / f"{name}.apworld"
print(f"Downloading {name}@{latest} from {url}")
last_exc: BaseException | None = None
for attempt in range(5):
    try:
        urllib.request.urlretrieve(url, out)
        last_exc = None
        break
    except urllib.error.HTTPError as exc:
        last_exc = exc
        if exc.code in (408, 429, 500, 502, 503, 504) and attempt < 4:
            delay = 2**attempt
            print(
                f"warn: HTTP {exc.code} for {url}; retry in {delay}s "
                f"({attempt + 1}/5)",
                file=sys.stderr,
            )
            time.sleep(delay)
            continue
        raise
    except urllib.error.URLError as exc:
        last_exc = exc
        if attempt < 4:
            delay = 2**attempt
            print(f"warn: URL error for {url}; retry in {delay}s", file=sys.stderr)
            time.sleep(delay)
            continue
        raise
if last_exc is not None:
    raise last_exc
print(f"Wrote {out} ({out.stat().st_size} bytes)")
PY
