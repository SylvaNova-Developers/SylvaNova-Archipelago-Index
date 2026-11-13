#!/usr/bin/env python3
"""Shard changed worlds for PR CI fuzz matrix (GitHub Actions 256-job limit).

Each matrix job runs one (shard, variant) pair and may fuzz multiple worlds
sequentially. Matrix size is ``shard_count * variant_count`` and must stay <= 256.
"""

from __future__ import annotations

import argparse
import json
import sys

# Keep in sync with variant list in .github/workflows/pr-ci.yml fuzz job.
FUZZ_VARIANT_COUNT = 11
GITHUB_MATRIX_JOB_LIMIT = 256


def shard_count(world_count: int) -> int:
    if world_count <= 0:
        return 0
    max_shards = GITHUB_MATRIX_JOB_LIMIT // FUZZ_VARIANT_COUNT
    if world_count <= max_shards:
        return world_count
    return max_shards


def worlds_for_shard(all_worlds: list[str], shard: int, total_shards: int) -> list[str]:
    if total_shards <= 0:
        return []
    return [world for index, world in enumerate(all_worlds) if index % total_shards == shard]


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--worlds-json",
        help="JSON array of apworld ids (same as discover output)",
    )
    group.add_argument("--world-count", type=int, help="Only compute shard count")
    parser.add_argument(
        "--shard",
        type=int,
        help="With --worlds-json: list worlds assigned to this shard index",
    )
    parser.add_argument(
        "--shards-json",
        action="store_true",
        help="Emit JSON array of shard indices [0..n-1]",
    )
    args = parser.parse_args()

    if args.world_count is not None:
        count = shard_count(args.world_count)
        if args.shards_json:
            print(json.dumps(list(range(count))))
        else:
            print(count)
        return 0

    worlds = json.loads(args.worlds_json)
    if not isinstance(worlds, list):
        print("worlds-json must be a JSON array", file=sys.stderr)
        return 1

    total = shard_count(len(worlds))
    if args.shards_json:
        print(json.dumps(list(range(total))))
        return 0

    if args.shard is not None:
        assigned = worlds_for_shard(worlds, args.shard, total)
        for world in assigned:
            print(world)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
