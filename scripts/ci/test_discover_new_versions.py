#!/usr/bin/env python3
"""Regression tests for discover_new_versions GitHub API handling."""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

from discover_new_versions import GithubApiHttpError, list_releases


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


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    unittest.main()
