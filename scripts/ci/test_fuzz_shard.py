#!/usr/bin/env python3
"""Tests for fuzz matrix sharding."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from fuzz_shard import FUZZ_VARIANT_COUNT, GITHUB_MATRIX_JOB_LIMIT, shard_count, worlds_for_shard

CI_DIR = Path(__file__).resolve().parent


class FuzzShardTests(unittest.TestCase):
    def test_small_pr_one_world_per_shard(self) -> None:
        self.assertEqual(shard_count(5), 5)

    def test_large_sync_caps_at_matrix_limit(self) -> None:
        max_shards = GITHUB_MATRIX_JOB_LIMIT // FUZZ_VARIANT_COUNT
        self.assertEqual(shard_count(94), max_shards)
        self.assertLessEqual(max_shards * FUZZ_VARIANT_COUNT, GITHUB_MATRIX_JOB_LIMIT)

    def test_worlds_round_robin(self) -> None:
        worlds = [f"w{i}" for i in range(10)]
        total = shard_count(len(worlds))
        seen: list[str] = []
        for shard in range(total):
            seen.extend(worlds_for_shard(worlds, shard, total))
        self.assertEqual(seen, worlds)

    def test_cli_shards_json_matches_run_109(self) -> None:
        worlds = ["a"] * 94
        proc = subprocess.run(
            [
                sys.executable,
                str(CI_DIR / "fuzz_shard.py"),
                "--worlds-json",
                json.dumps(worlds),
                "--shards-json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        shards = json.loads(proc.stdout)
        self.assertEqual(len(shards), shard_count(94))
        self.assertLessEqual(len(shards) * FUZZ_VARIANT_COUNT, GITHUB_MATRIX_JOB_LIMIT)


if __name__ == "__main__":
    sys.path.insert(0, str(CI_DIR))
    unittest.main()
