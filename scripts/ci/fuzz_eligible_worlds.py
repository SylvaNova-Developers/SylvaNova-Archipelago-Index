#!/usr/bin/env python3
"""Filter changed apworld ids to those eligible for CI fuzzing."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path


def version_sources_downloadable(data: dict) -> bool:
    """Return True if at least one indexed version can be fetched for fuzz."""
    versions = data.get("versions")
    if not isinstance(versions, dict) or not versions:
        return False
    default_url = data.get("default_url")
    for raw_version, src in versions.items():
        if src is None:
            src = {}
        if not isinstance(src, dict):
            continue
        if "local" in src:
            continue
        if "url" in src and str(src["url"]).strip():
            return True
        if isinstance(default_url, str) and default_url and "{{version}}" in default_url:
            return True
    return False


def fuzz_skip_reason(path: Path, data: dict) -> str | None:
    world_id = path.stem
    if data.get("disabled") is True:
        if data.get("supported") is True:
            return f"{world_id}: skip fuzz (disabled=true, supported=true — index metadata only)"
        return f"{world_id}: skip fuzz (disabled=true)"

    if data.get("supported") is True:
        # Active core world; fuzz uses built-in Archipelago copy (no index versions).
        return None

    if not version_sources_downloadable(data):
        return f"{world_id}: skip fuzz (no downloadable [versions] for CI)"

    return None


def filter_fuzz_eligible(
    index_dir: Path,
    world_ids: list[str],
) -> tuple[list[str], list[str]]:
    eligible: list[str] = []
    skipped: list[str] = []
    for world_id in world_ids:
        path = index_dir / f"{world_id}.toml"
        if not path.is_file():
            skipped.append(f"{world_id}: skip fuzz (missing {path.name})")
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{world_id}: skip fuzz (TOML parse error: {exc})")
            continue
        reason = fuzz_skip_reason(path, data)
        if reason is None:
            eligible.append(world_id)
        else:
            skipped.append(reason)
    return eligible, skipped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=Path("index"),
    )
    parser.add_argument(
        "--worlds-json",
        required=True,
        help="JSON array of apworld ids from changed_worlds.py",
    )
    parser.add_argument(
        "--json-array",
        action="store_true",
        help="Emit eligible ids as JSON array (default: one id per line)",
    )
    args = parser.parse_args()

    world_ids = json.loads(args.worlds_json)
    if not isinstance(world_ids, list):
        print("worlds-json must be a JSON array", file=sys.stderr)
        return 1

    eligible, skipped = filter_fuzz_eligible(args.index_dir, world_ids)
    for line in skipped:
        print(f"warn: {line}", file=sys.stderr)

    if args.json_array:
        print(json.dumps(eligible))
    else:
        for world_id in eligible:
            print(world_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
