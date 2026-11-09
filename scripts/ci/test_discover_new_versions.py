#!/usr/bin/env python3
"""Regression tests for discover_new_versions GitHub API handling."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

from discover_new_versions import (
    GithubApiHttpError,
    GithubDefaultUrl,
    list_releases,
    main,
)


class ListReleasesTests(unittest.TestCase):
    def test_404_returns_empty_and_warns(self) -> None:
        stderr = io.StringIO()
        with (
            mock.patch(
                "discover_new_versions.github_api_get",
                side_effect=GithubApiHttpError(404, "https://api.github.com/repos/o/r/releases"),
            ),
            redirect_stderr(stderr),
        ):
            result = list_releases("o", "r", None)
        self.assertEqual(result, [])
        self.assertIn("o/r", stderr.getvalue())
        self.assertIn("404", stderr.getvalue())

    def test_403_reraises(self) -> None:
        with mock.patch(
            "discover_new_versions.github_api_get",
            side_effect=GithubApiHttpError(403, "https://api.github.com/repos/o/r/releases"),
        ):
            with self.assertRaises(GithubApiHttpError) as ctx:
                list_releases("o", "r", "token")
            self.assertEqual(ctx.exception.status, 403)

    def test_429_reraises(self) -> None:
        with mock.patch(
            "discover_new_versions.github_api_get",
            side_effect=GithubApiHttpError(429, "https://api.github.com/repos/o/r/releases"),
        ):
            with self.assertRaises(GithubApiHttpError):
                list_releases("o", "r", "token")

    def test_500_reraises(self) -> None:
        with mock.patch(
            "discover_new_versions.github_api_get",
            side_effect=GithubApiHttpError(502, "https://api.github.com/repos/o/r/releases"),
        ):
            with self.assertRaises(GithubApiHttpError):
                list_releases("o", "r", None)

    def test_paginates_releases(self) -> None:
        page_one = [{"tag_name": "v1.0.0", "draft": False, "assets": []}]
        page_two: list[object] = []
        with mock.patch(
            "discover_new_versions.github_api_get",
            side_effect=[page_one, page_two],
        ):
            result = list_releases("owner", "repo", None)
        self.assertEqual(len(result), 1)


class MainGithubApiTests(unittest.TestCase):
    _parsed = GithubDefaultUrl(
        owner="o",
        repo="r",
        tag_template="{{version}}",
        asset="world.apworld",
        raw="https://github.com/o/r/releases/download/{{version}}/world.apworld",
    )
    _eligible = [
        (
            "testworld",
            __import__("pathlib").Path("index/testworld.toml"),
            {"versions": {"1.0.0": {}}},
            _parsed,
            "fork-only",
        )
    ]

    def test_main_exits_nonzero_on_403(self) -> None:
        with (
            mock.patch(
                "discover_new_versions.discover_eligible",
                return_value=self._eligible,
            ),
            mock.patch(
                "discover_new_versions.collect_candidates",
                side_effect=GithubApiHttpError(403, "https://api.github.com/repos/o/r/releases"),
            ),
            mock.patch(
                "sys.argv",
                ["discover_new_versions.py", "--dry-run", "--skip-url-check"],
            ),
        ):
            with self.assertRaises(GithubApiHttpError):
                main()

    def test_main_completes_when_list_releases_gets_404(self) -> None:
        with (
            mock.patch(
                "discover_new_versions.discover_eligible",
                return_value=self._eligible,
            ),
            mock.patch(
                "discover_new_versions.collect_candidates",
                return_value=[],
            ),
            mock.patch("discover_new_versions.append_versions"),
            mock.patch(
                "sys.argv",
                ["discover_new_versions.py", "--dry-run", "--skip-url-check"],
            ),
        ):
            self.assertEqual(main(), 0)


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    unittest.main()
