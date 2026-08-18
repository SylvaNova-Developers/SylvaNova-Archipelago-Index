#!/usr/bin/env python3
"""Aggregate fuzz report JSON files into a PR-facing markdown summary."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_fuzz_report import EdgeCaseCatalog, classify_errors, failure_rate


def discover_reports(root: Path) -> list[Path]:
    return sorted(root.rglob("fuzz-report-*.json"))


def label_from_report(path: Path) -> str:
    name = path.name
    if name.startswith("fuzz-report-") and name.endswith(".json"):
        return name.removeprefix("fuzz-report-").removesuffix(".json")
    return path.stem


def summarize_report(path: Path, catalog: EdgeCaseCatalog, *, max_rate: float) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    stats = data.get("stats") or {}
    errors = data.get("errors") or {}
    label = label_from_report(path)
    reclassified, reclassify_summaries, review_summaries = classify_errors(errors, catalog)
    raw_failure = int(stats.get("failure", 0))
    rate, effective_failure, considered, _ = failure_rate(stats, reclassified=reclassified)
    gate_passed = considered > 0 and rate < max_rate
    return {
        "label": label,
        "path": str(path),
        "gate_passed": gate_passed,
        "stats": stats,
        "raw_failure": raw_failure,
        "reclassified": reclassified,
        "effective_failure": effective_failure,
        "rate": rate,
        "considered": considered,
        "reclassify": [
            {"id": item.pattern_id, "count": item.count, "sample": item.sample, "reason": item.reason, "suggestion": item.suggestion}
            for item in reclassify_summaries
        ],
        "review": [
            {"id": item.pattern_id, "count": item.count, "sample": item.sample, "reason": item.reason, "suggestion": item.suggestion}
            for item in review_summaries
        ],
    }


def format_markdown(summaries: list[dict], *, max_rate: float) -> str:
    failed = [item for item in summaries if not item["gate_passed"]]
    passed = [item for item in summaries if item["gate_passed"]]

    lines: list[str] = [
        "## Fuzz gate — human review",
        "",
        "Some failures look like **option edge cases** (reclassified for the rate gate). "
        "Others still count and may need **maintainer intervention** before auto-merge.",
        "",
    ]

    if failed:
        lines.extend(
            [
                "### Failed variants",
                "",
            ]
        )
        for item in failed:
            rate_pct = item["rate"] * 100
            lines.append(
                f"- **`{item['label']}`** — effective rate **{rate_pct:.1f}%** "
                f"({item['effective_failure']}/{item['considered']}; "
                f"raw failures {item['raw_failure']}, reclassified {item['reclassified']})"
            )
            if item["reclassify"]:
                lines.append("  - Reclassified edge cases:")
                for entry in item["reclassify"]:
                    lines.append(f"    - `{entry['id']}` ×{entry['count']}: {entry['sample']}")
            if item["review"]:
                lines.append("  - **Needs human judgment** (still counted):")
                for entry in item["review"]:
                    lines.append(f"    - `{entry['id']}` ×{entry['count']}: {entry['sample']}")
                    if entry["reason"]:
                        lines.append(f"      - {entry['reason'].replace(chr(10), ' ')}")
            lines.append("")

    has_blocking_review = any(item["review"] for item in failed)

    lines.extend(
        [
            "### What you can do",
            "",
        ]
    )

    if has_blocking_review:
        lines.extend(
            [
                "- **Real bugs suspected** (e.g. non-determinism, FillError): fix upstream or accept risk explicitly.",
                "- **Option edge cases only** after reclassification: extend `fuzz-meta/<world>.yaml` or comment `/force-merge` / `r+` on this PR.",
                "",
                "Force-merge still requires green `validate`. See `.github/workflows/force-merge.yml`.",
            ]
        )
    elif failed:
        lines.extend(
            [
                "- Failures look like **option edge cases**. Consider adding `fuzz-meta` for this world, "
                "or `/force-merge` if the effective rate is acceptable.",
                "",
                "Force-merge still requires green `validate`. See `.github/workflows/force-merge.yml`.",
            ]
        )
    else:
        lines.extend(
            [
                f"All downloaded variants passed the **<{max_rate:.0%}** effective failure-rate gate.",
            ]
        )

    if passed and failed:
        lines.extend(["", f"({len(passed)} other variant(s) passed.)"])

    return "\n".join(lines).strip() + "\n"


def post_pr_comment(body: str, *, repo: str, pr: int) -> None:
    subprocess.run(
        ["gh", "pr", "comment", str(pr), "--repo", repo, "--body", body],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "reports_dir",
        type=Path,
        help="Directory containing fuzz-report-*.json files (e.g. artifact download root)",
    )
    parser.add_argument("--max-rate", type=float, default=0.20)
    parser.add_argument(
        "--edge-cases",
        type=Path,
        default=Path(__file__).resolve().parent / "fuzz_edge_cases.yaml",
    )
    parser.add_argument("--markdown-out", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--post-pr-comment", type=int, default=None)
    parser.add_argument("--repo", default="")
    args = parser.parse_args()

    if not args.reports_dir.is_dir():
        print(f"Reports directory not found: {args.reports_dir}", file=sys.stderr)
        return 2

    catalog = EdgeCaseCatalog.load(args.edge_cases)
    reports = discover_reports(args.reports_dir)
    if not reports:
        print(f"No fuzz-report-*.json under {args.reports_dir}", file=sys.stderr)
        return 2

    summaries = [summarize_report(path, catalog, max_rate=args.max_rate) for path in reports]
    markdown = format_markdown(summaries, max_rate=args.max_rate)

    if args.markdown_out:
        args.markdown_out.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)

    if args.json_out:
        args.json_out.write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")

    if args.post_pr_comment is not None:
        if not args.repo:
            print("--repo required with --post-pr-comment", file=sys.stderr)
            return 2
        post_pr_comment(markdown, repo=args.repo, pr=args.post_pr_comment)

    return 0


if __name__ == "__main__":
    sys.exit(main())
