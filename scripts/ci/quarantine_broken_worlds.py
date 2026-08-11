#!/usr/bin/env python3
"""Quarantine broken index worlds so bot sync cannot freeze on one bad entry.

For each given apworld id (toml stem):
  - Drop version rows whose resolved URL is unreachable
  - If no versions remain (and the world is not supported=true), set
    ``disabled = true`` with a short reason comment

Human PRs stay strict via validate_worlds.py. Bot sync runs this *before*
pushing bot/sync-upstream so required checks can still go green.

Preserves surrounding TOML formatting/comments via line edits (no re-serialize).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from validate_worlds import check_url, resolve_url

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


VERSION_LINE = re.compile(
    r'^(?P<indent>\s*)(?P<key>"[^"]+"|\'[^\']+\'|[A-Za-z0-9_.+-]+)\s*=\s*.*$'
)
DISABLED_LINE = re.compile(r"^(\s*)disabled\s*=\s*(true|false)\b(.*)$", re.IGNORECASE)


def _version_key(raw: str) -> str:
    raw = raw.strip()
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        return raw[1:-1]
    return raw


def unreachable_versions(path: Path, data: dict) -> list[tuple[str, str]]:
    """Return (version, reason) for versions with dead URLs."""
    bad: list[tuple[str, str]] = []
    if data.get("supported") is True:
        return bad
    versions = data.get("versions")
    if not isinstance(versions, dict):
        return bad
    for version, src in versions.items():
        if src is None:
            src = {}
        if not isinstance(src, dict):
            continue
        if "local" in src:
            continue
        url = resolve_url(data, str(version), src)
        if not url:
            bad.append((str(version), "no resolvable url/default_url"))
            continue
        try:
            check_url(url)
        except Exception as exc:  # noqa: BLE001
            bad.append((str(version), f"URL not reachable ({url}): {exc}"))
    return bad


def drop_version_lines(text: str, versions: set[str]) -> str:
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        match = VERSION_LINE.match(line.rstrip("\n"))
        if match and _version_key(match.group("key")) in versions:
            # Drop the version assignment line only.
            continue
        out.append(line)
    return "".join(out)


def ensure_disabled(text: str, reason: str) -> str:
    comment = f" # quarantined by sync: {reason}"
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        match = DISABLED_LINE.match(line.rstrip("\n"))
        if match:
            indent, _value, rest = match.groups()
            # Preserve an existing trailing comment if present and no quarantine yet.
            trailing = rest if rest.strip().startswith("#") else comment
            if "quarantined by sync" in rest:
                trailing = rest
            lines[i] = f"{indent}disabled = true{trailing}\n"
            if not lines[i].endswith("\n"):
                lines[i] += "\n"
            return "".join(lines)

    # Insert after the first `name = ...` line when possible.
    insert_at = 0
    for i, line in enumerate(lines):
        if re.match(r"^\s*name\s*=", line):
            insert_at = i + 1
            break
    lines.insert(insert_at, f"disabled = true{comment}\n")
    return "".join(lines)


def quarantine_world(path: Path) -> list[str]:
    actions: list[str] = []
    original = path.read_text(encoding="utf-8")
    try:
        data = tomllib.loads(original)
    except Exception as exc:  # noqa: BLE001
        # Unreadable TOML: disable so sync can proceed.
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path.write_text(
            ensure_disabled(original, f"unreadable TOML on {stamp} ({exc})"),
            encoding="utf-8",
        )
        return [f"{path.stem}: disabled (unreadable TOML: {exc})"]

    if data.get("disabled") is True:
        return actions

    bad = unreachable_versions(path, data)
    if not bad:
        return actions

    bad_keys = {version for version, _reason in bad}
    updated = drop_version_lines(original, bad_keys)
    for version, reason in bad:
        actions.append(f"{path.stem}: dropped version {version} ({reason})")

    # Re-parse to see if any versions remain.
    try:
        remaining = tomllib.loads(updated).get("versions")
    except Exception:  # noqa: BLE001
        remaining = None

    versions_left = isinstance(remaining, dict) and bool(remaining)
    if not versions_left and data.get("supported") is not True:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        reasons = "; ".join(f"{v}: {r}" for v, r in bad)
        updated = ensure_disabled(
            updated,
            f"no reachable versions on {stamp} ({reasons})",
        )
        actions.append(f"{path.stem}: disabled (no reachable versions left)")

    if updated != original:
        path.write_text(updated, encoding="utf-8")
    return actions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "worlds",
        nargs="*",
        help="Apworld ids (toml stems). If empty, scan all index/*.toml",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=Path("index"),
        help="Path to the index/ directory",
    )
    args = parser.parse_args()

    if args.worlds:
        paths = [args.index_dir / f"{name}.toml" for name in args.worlds]
    else:
        paths = sorted(args.index_dir.glob("*.toml"))

    all_actions: list[str] = []
    for path in paths:
        if not path.is_file():
            print(f"skip missing {path}", file=sys.stderr)
            continue
        all_actions.extend(quarantine_world(path))

    if all_actions:
        print("Quarantine actions:")
        for action in all_actions:
            print(f"  - {action}")
        print(f"changed=true")
    else:
        print("No quarantine actions needed")
        print("changed=false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
