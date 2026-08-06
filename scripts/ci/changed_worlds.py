#!/usr/bin/env python3
"""List apworld ids whose index/*.toml changed between BASE and HEAD.

Prints one apworld name per line (stem of the toml file). Used by PR CI to
scope validate/fuzz to worlds touched by the PR.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def git_diff_names(base: str, head: str, pathspec: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...{head}", "--", pathspec],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Base git ref (e.g. origin/main)")
    parser.add_argument("--head", default="HEAD", help="Head git ref")
    parser.add_argument(
        "--json-array",
        action="store_true",
        help="Emit a JSON array instead of newline-separated names",
    )
    args = parser.parse_args()

    names: list[str] = []
    for path in git_diff_names(args.base, args.head, "index/*.toml"):
        stem = Path(path).stem
        if stem and stem not in names:
            names.append(stem)

    if args.json_array:
        import json

        print(json.dumps(names))
    else:
        for name in names:
            print(name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
