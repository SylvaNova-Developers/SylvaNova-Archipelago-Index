#!/usr/bin/env python3
"""Fail if a fuzzer report.json exceeds the inclusion failure-rate gate.

Gate (SylvaNova index criteria):
  failure / (success + failure + timeout) < 0.025
  OptionError / ignored outcomes are excluded from the denominator.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def failure_rate(stats: dict) -> tuple[float, int, int]:
    success = int(stats.get("success", 0))
    failure = int(stats.get("failure", 0))
    timeout = int(stats.get("timeout", 0))
    considered = success + failure + timeout
    if considered == 0:
        return 0.0, failure, considered
    return failure / considered, failure, considered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path, help="Path to fuzz report.json")
    parser.add_argument(
        "--max-rate",
        type=float,
        default=0.025,
        help="Maximum allowed failure rate (default: 0.025)",
    )
    parser.add_argument("--label", default="", help="Optional label for log lines")
    args = parser.parse_args()

    if not args.report.is_file():
        print(f"Missing report: {args.report}", file=sys.stderr)
        return 2

    data = json.loads(args.report.read_text(encoding="utf-8"))
    stats = data.get("stats") or {}
    rate, failures, considered = failure_rate(stats)
    prefix = f"[{args.label}] " if args.label else ""
    print(
        f"{prefix}fuzz stats: success={stats.get('success', 0)} "
        f"failure={stats.get('failure', 0)} timeout={stats.get('timeout', 0)} "
        f"ignored={stats.get('ignored', 0)} rate={rate:.4%} over {considered} considered runs"
    )

    if considered == 0:
        print(f"{prefix}no considered runs in report; treating as failure", file=sys.stderr)
        return 1

    if rate >= args.max_rate:
        print(
            f"{prefix}failure rate {rate:.4%} >= {args.max_rate:.2%} "
            f"({failures}/{considered})",
            file=sys.stderr,
        )
        return 1

    print(f"{prefix}passed failure-rate gate (< {args.max_rate:.2%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
