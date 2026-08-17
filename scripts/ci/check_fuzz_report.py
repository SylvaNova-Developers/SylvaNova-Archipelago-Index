#!/usr/bin/env python3
"""Fail if a fuzzer report.json exceeds the inclusion failure-rate gate.

Gate (SylvaNova index criteria):
  failure / (success + failure + timeout) < 0.20
  OptionError / ignored outcomes are excluded from the denominator.

Optional edge-case patterns (scripts/ci/fuzz_edge_cases.yaml) can reclassify
known option-incompatibility failures so they do not count toward the gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML on GHA runners
    yaml = None  # type: ignore[assignment]


@dataclass
class EdgeCasePattern:
    id: str
    pattern: str
    reason: str
    suggestion: str = ""

    def matches(self, text: str) -> bool:
        return self.pattern.casefold() in text.casefold()

    @classmethod
    def from_mapping(cls, mapping: dict) -> EdgeCasePattern:
        return cls(
            id=str(mapping["id"]),
            pattern=str(mapping["pattern"]),
            reason=str(mapping.get("reason", "")).strip(),
            suggestion=str(mapping.get("suggestion", "")).strip(),
        )


@dataclass
class EdgeCaseCatalog:
    reclassify: list[EdgeCasePattern] = field(default_factory=list)
    review: list[EdgeCasePattern] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path | None) -> EdgeCaseCatalog:
        if path is None or not path.is_file():
            return cls()
        if yaml is None:
            print(f"PyYAML not installed; ignoring edge cases at {path}", file=sys.stderr)
            return cls()
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            reclassify=[
                EdgeCasePattern.from_mapping(entry)
                for entry in raw.get("reclassify") or []
            ],
            review=[
                EdgeCasePattern.from_mapping(entry)
                for entry in raw.get("review") or []
            ],
        )


@dataclass
class PatternMatchSummary:
    pattern_id: str
    category: str
    count: int
    sample: str
    reason: str
    suggestion: str


def iter_error_messages(errors: dict) -> list[str]:
    messages: list[str] = []
    for game_errors in errors.values():
        if not isinstance(game_errors, dict):
            continue
        for message in game_errors:
            messages.append(str(message))
    return messages


def count_error_instances(errors: dict) -> int:
    total = 0
    for game_errors in errors.values():
        if not isinstance(game_errors, dict):
            continue
        for runs in game_errors.values():
            if isinstance(runs, list):
                total += len(runs)
    return total


def classify_errors(
    errors: dict,
    catalog: EdgeCaseCatalog,
) -> tuple[int, list[PatternMatchSummary], list[PatternMatchSummary]]:
    """Return (reclassified_count, reclassify_summaries, review_summaries)."""
    reclassify_counts: dict[str, tuple[int, str]] = {}
    review_counts: dict[str, tuple[int, str]] = {}

    for game_errors in errors.values():
        if not isinstance(game_errors, dict):
            continue
        for message, runs in game_errors.items():
            if not isinstance(runs, list):
                continue
            count = len(runs)
            text = str(message)
            for pattern in catalog.reclassify:
                if pattern.matches(text):
                    entry = reclassify_counts.get(pattern.id, (0, text))
                    reclassify_counts[pattern.id] = (entry[0] + count, entry[1] or text)
                    break
            else:
                for pattern in catalog.review:
                    if pattern.matches(text):
                        entry = review_counts.get(pattern.id, (0, text))
                        review_counts[pattern.id] = (entry[0] + count, entry[1] or text)
                        break

    def build_summaries(
        counts: dict[str, tuple[int, str]],
        patterns: list[EdgeCasePattern],
        category: str,
    ) -> list[PatternMatchSummary]:
        by_id = {pattern.id: pattern for pattern in patterns}
        summaries: list[PatternMatchSummary] = []
        for pattern_id, (count, sample) in sorted(counts.items(), key=lambda item: -item[1][0]):
            pattern = by_id[pattern_id]
            summaries.append(
                PatternMatchSummary(
                    pattern_id=pattern_id,
                    category=category,
                    count=count,
                    sample=sample.splitlines()[0][:240],
                    reason=pattern.reason,
                    suggestion=pattern.suggestion,
                )
            )
        return summaries

    reclassified = sum(count for count, _ in reclassify_counts.values())
    return (
        reclassified,
        build_summaries(reclassify_counts, catalog.reclassify, "reclassify"),
        build_summaries(review_counts, catalog.review, "review"),
    )


def failure_rate(
    stats: dict,
    *,
    reclassified: int = 0,
) -> tuple[float, int, int, int]:
    success = int(stats.get("success", 0))
    failure = max(0, int(stats.get("failure", 0)) - reclassified)
    timeout = int(stats.get("timeout", 0))
    considered = success + failure + timeout
    if considered == 0:
        return 0.0, failure, considered, reclassified
    return failure / considered, failure, considered, reclassified


def write_review_json(
    path: Path,
    *,
    label: str,
    stats: dict,
    raw_failure: int,
    reclassified: int,
    rate: float,
    considered: int,
    gate_passed: bool,
    reclassify_summaries: list[PatternMatchSummary],
    review_summaries: list[PatternMatchSummary],
) -> None:
    payload = {
        "label": label,
        "gate_passed": gate_passed,
        "stats": stats,
        "raw_failure": raw_failure,
        "reclassified": reclassified,
        "effective_failure": max(0, raw_failure - reclassified),
        "rate": rate,
        "considered": considered,
        "reclassify": [
            {
                "id": item.pattern_id,
                "count": item.count,
                "sample": item.sample,
                "reason": item.reason,
                "suggestion": item.suggestion,
            }
            for item in reclassify_summaries
        ],
        "review": [
            {
                "id": item.pattern_id,
                "count": item.count,
                "sample": item.sample,
                "reason": item.reason,
                "suggestion": item.suggestion,
            }
            for item in review_summaries
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path, help="Path to fuzz report.json")
    parser.add_argument(
        "--max-rate",
        type=float,
        default=0.20,
        help="Maximum allowed failure rate (default: 0.20)",
    )
    parser.add_argument("--label", default="", help="Optional label for log lines")
    parser.add_argument(
        "--edge-cases",
        type=Path,
        default=None,
        help="YAML file with reclassify/review patterns (default: scripts/ci/fuzz_edge_cases.yaml next to repo root)",
    )
    parser.add_argument(
        "--review-out",
        type=Path,
        default=None,
        help="Optional path to write JSON review summary",
    )
    args = parser.parse_args()

    if not args.report.is_file():
        print(f"Missing report: {args.report}", file=sys.stderr)
        return 2

    edge_cases_path = args.edge_cases
    if edge_cases_path is None:
        candidate = Path(__file__).resolve().parent / "fuzz_edge_cases.yaml"
        edge_cases_path = candidate if candidate.is_file() else None

    data = json.loads(args.report.read_text(encoding="utf-8"))
    stats = data.get("stats") or {}
    errors = data.get("errors") or {}
    catalog = EdgeCaseCatalog.load(edge_cases_path)
    reclassified, reclassify_summaries, review_summaries = classify_errors(errors, catalog)

    raw_failure = int(stats.get("failure", 0))
    rate, effective_failure, considered, _ = failure_rate(stats, reclassified=reclassified)
    prefix = f"[{args.label}] " if args.label else ""

    print(
        f"{prefix}fuzz stats: success={stats.get('success', 0)} "
        f"failure={raw_failure} reclassified={reclassified} "
        f"effective_failure={effective_failure} "
        f"timeout={stats.get('timeout', 0)} "
        f"ignored={stats.get('ignored', 0)} rate={rate:.4%} over {considered} considered runs"
    )

    if reclassify_summaries:
        print(f"{prefix}reclassified edge cases:")
        for item in reclassify_summaries:
            print(f"{prefix}  - {item.pattern_id}: {item.count}× ({item.sample})")

    if review_summaries:
        print(f"{prefix}flagged for human review (still counted in gate):")
        for item in review_summaries:
            print(f"{prefix}  - {item.pattern_id}: {item.count}× ({item.sample})")

    gate_passed = True
    if considered == 0:
        print(f"{prefix}no considered runs in report; treating as failure", file=sys.stderr)
        gate_passed = False
    elif rate >= args.max_rate:
        print(
            f"{prefix}failure rate {rate:.4%} >= {args.max_rate:.2%} "
            f"({effective_failure}/{considered})",
            file=sys.stderr,
        )
        gate_passed = False
    else:
        print(f"{prefix}passed failure-rate gate (< {args.max_rate:.2%})")

    if args.review_out is not None:
        write_review_json(
            args.review_out,
            label=args.label,
            stats=stats,
            raw_failure=raw_failure,
            reclassified=reclassified,
            rate=rate,
            considered=considered,
            gate_passed=gate_passed,
            reclassify_summaries=reclassify_summaries,
            review_summaries=review_summaries,
        )

    return 0 if gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())
