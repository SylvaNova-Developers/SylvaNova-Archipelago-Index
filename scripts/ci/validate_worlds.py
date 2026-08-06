#!/usr/bin/env python3
"""Validate index world TOML entries touched by a PR.

Checks:
  - file parses as TOML
  - required `name` field present
  - new entries do not use `local` version sources
  - version URLs (resolved via default_url when needed) are reachable (HEAD/GET)
"""

from __future__ import annotations

import argparse
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path


def resolve_url(world: dict, version: str, src: dict | None) -> str | None:
    src = src or {}
    if "url" in src:
        return src["url"]
    if "local" in src:
        return None
    default_url = world.get("default_url")
    if isinstance(default_url, str) and default_url:
        return default_url.replace("{{version}}", version)
    return None


def check_url(url: str, timeout: float = 30.0) -> None:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status} for {url}")
            return
    except urllib.error.HTTPError as exc:
        # Some hosts reject HEAD; fall back to a ranged GET.
        if exc.code not in (403, 405, 501):
            raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError:
        pass

    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Range": "bytes=0-0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status >= 400:
            raise RuntimeError(f"HTTP {response.status} for {url}")


def is_core_world(apworld_id: str, archipelago_dir: Path) -> bool:
    world_dir = archipelago_dir / "worlds" / apworld_id
    return world_dir.is_dir() and (world_dir / "__init__.py").is_file()


def validate_world(
    path: Path,
    *,
    check_urls: bool,
    archipelago_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surface parse errors as validation failures
        return [f"{path}: failed to parse TOML: {exc}"]

    if "name" not in data or not str(data["name"]).strip():
        errors.append(f"{path}: missing required `name` field")

    if data.get("supported") is True:
        if "home" not in data or not str(data["home"]).strip():
            errors.append(f"{path}: supported worlds require a `home` field")
        if archipelago_dir is None:
            errors.append(
                f"{path}: supported=true requires --archipelago-dir to verify built-in world membership"
            )
        else:
            apworld_id = path.stem
            if not is_core_world(apworld_id, archipelago_dir):
                errors.append(
                    f"{path}: supported=true but worlds/{apworld_id} is not a built-in "
                    "Archipelago world at the pinned version"
                )
        return errors

    versions = data.get("versions")
    if not isinstance(versions, dict) or not versions:
        errors.append(f"{path}: non-supported worlds require a non-empty [versions] table")
        return errors

    for version, src in versions.items():
        if src is None:
            src = {}
        if not isinstance(src, dict):
            errors.append(f"{path}: version {version} source must be a table")
            continue
        if "local" in src:
            errors.append(
                f"{path}: version {version} uses local=...; "
                "new/updated entries must use url/default_url"
            )
            continue
        url = resolve_url(data, str(version), src)
        if not url:
            errors.append(f"{path}: version {version} has no resolvable url/default_url")
            continue
        if check_urls:
            try:
                check_url(url)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{path}: version {version} URL not reachable ({url}): {exc}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "worlds",
        nargs="*",
        help="Apworld ids (toml stems). If empty, validate all index/*.toml",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=Path("index"),
        help="Path to the index/ directory",
    )
    parser.add_argument(
        "--skip-url-check",
        action="store_true",
        help="Skip HTTP reachability checks",
    )
    parser.add_argument(
        "--archipelago-dir",
        type=Path,
        help="Path to an Archipelago checkout (required to validate supported=true worlds)",
    )
    args = parser.parse_args()

    if args.worlds:
        paths = [args.index_dir / f"{name}.toml" for name in args.worlds]
    else:
        paths = sorted(args.index_dir.glob("*.toml"))

    all_errors: list[str] = []
    for path in paths:
        if not path.is_file():
            all_errors.append(f"{path}: file does not exist")
            continue
        all_errors.extend(
            validate_world(
                path,
                check_urls=not args.skip_url_check,
                archipelago_dir=args.archipelago_dir,
            )
        )

    if all_errors:
        print("Validation failed:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"Validated {len(paths)} world file(s) successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
