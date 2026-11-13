#!/usr/bin/env python3
"""Tests for fuzz eligibility filtering."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fuzz_eligible_worlds import filter_fuzz_eligible


class FuzzEligibleTests(unittest.TestCase):
    def write(self, root: Path, name: str, text: str) -> None:
        (root / f"{name}.toml").write_text(text, encoding="utf-8")

    def test_disabled_no_versions_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            self.write(
                index_dir,
                "sims4",
                'name = "The Sims 4"\ndisabled = true\n\n[versions]\n',
            )
            self.write(
                index_dir,
                "scrc",
                'name = "SCRC"\ndisabled = true\n',
            )
            eligible, skipped = filter_fuzz_eligible(index_dir, ["sims4", "scrc"])
            self.assertEqual(eligible, [])
            self.assertEqual(len(skipped), 2)
            self.assertTrue(all("disabled=true" in s for s in skipped))

    def test_supported_disabled_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            self.write(
                index_dir,
                "dkc3",
                (
                    'name = "DKC3"\n'
                    "supported = true\n"
                    "disabled = true\n"
                ),
            )
            eligible, skipped = filter_fuzz_eligible(index_dir, ["dkc3"])
            self.assertEqual(eligible, [])
            self.assertIn("supported=true", skipped[0])

    def test_enabled_with_url_kept(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            self.write(
                index_dir,
                "spire2",
                (
                    'name = "Spire"\n'
                    'default_url = "https://example.com/{{version}}/x.apworld"\n\n'
                    '[versions]\n"1.0.0" = {}\n'
                ),
            )
            eligible, skipped = filter_fuzz_eligible(index_dir, ["spire2"])
            self.assertEqual(eligible, ["spire2"])
            self.assertEqual(skipped, [])

    def test_supported_active_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index_dir = Path(tmp)
            self.write(
                index_dir,
                "celeste",
                'name = "Celeste"\nsupported = true\nhome = "https://example.com"\n',
            )
            eligible, _ = filter_fuzz_eligible(index_dir, ["celeste"])
            self.assertEqual(eligible, ["celeste"])


if __name__ == "__main__":
    unittest.main()
