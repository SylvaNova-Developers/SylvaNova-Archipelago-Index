#!/usr/bin/env python3
"""Print the Archipelago Python package name inside an .apworld zip.

The worlds/ filename stem must match the zip's top-level package directory so
AP can import worlds.<stem>. Index keys are lowercase, but release artifacts
often use mixed case or versioned filenames; read the zip instead of guessing.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from collections import defaultdict
from pathlib import Path


def package_stem_from_zip(apworld: Path) -> str:
    with zipfile.ZipFile(apworld) as archive:
        roots: set[str] = set()
        files_under_root: dict[str, list[str]] = defaultdict(list)
        for entry in archive.namelist():
            normalized = entry.replace("\\", "/").strip("/")
            if not normalized:
                continue
            root, _, rest = normalized.partition("/")
            roots.add(root)
            if rest:
                files_under_root[root].append(rest)

        if not roots:
            raise ValueError(f"{apworld}: empty apworld archive")

        def looks_like_world_package(root: str) -> bool:
            names = files_under_root.get(root, [])
            return any(
                name.endswith("__init__.py") or name == "archipelago.json"
                for name in names
            )

        packages = [root for root in sorted(roots) if looks_like_world_package(root)]
        if len(packages) == 1:
            return packages[0]
        if len(roots) == 1:
            return next(iter(roots))

    raise ValueError(
        f"{apworld}: could not determine a unique package directory "
        f"(candidates: {', '.join(sorted(roots))})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apworld", type=Path, help="Path to .apworld file")
    parser.add_argument(
        "--fallback-stem",
        help="Use when the archive is not a readable zip (defaults to apworld stem)",
    )
    args = parser.parse_args()

    if not args.apworld.is_file():
        print(f"missing apworld: {args.apworld}", file=sys.stderr)
        return 2

    try:
        stem = package_stem_from_zip(args.apworld)
    except (zipfile.BadZipFile, OSError) as exc:
        if args.fallback_stem:
            stem = args.fallback_stem
        else:
            stem = args.apworld.stem
        print(f"warning: {exc}; using stem {stem}", file=sys.stderr)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(stem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())