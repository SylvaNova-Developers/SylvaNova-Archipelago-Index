#!/usr/bin/env python3
"""Discover and append new GitHub release versions for fork-diverged worlds.

Eligibility (relative to --upstream-ref, default upstream/main):
  - local world has a GitHub default_url with {{version}} and /releases/download/
  - local world is not supported = true
  - upstream file missing (fork-only) OR upstream has supported = true (demoted)

For each eligible world, polls GitHub Releases, maps tags/assets to semver, and
appends versions newer than the current latest indexed version.

Prints `changed=true` or `changed=false` on the last stdout line for CI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version

SEMVER_RE = re.compile(
    r"(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)"
)
GITHUB_DEFAULT_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/releases/download/"
    r"(?P<tag_template>[^/]+)/(?P<asset>[^/]+)$"
)


@dataclass(frozen=True)
class GithubDefaultUrl:
    owner: str
    repo: str
    tag_template: str
    asset: str
    raw: str


@dataclass(frozen=True)
class CandidateVersion:
    version: str
    url: str
    uses_default_url: bool


def load_toml(path: Path) -> dict | None:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"warn: failed to parse {path}: {exc}", file=sys.stderr)
        return None


def parse_github_default_url(default_url: str) -> GithubDefaultUrl | None:
    if "{{version}}" not in default_url or "/releases/download/" not in default_url:
        return None
    match = GITHUB_DEFAULT_URL_RE.match(default_url)
    if not match:
        return None
    return GithubDefaultUrl(
        owner=match.group("owner"),
        repo=match.group("repo"),
        tag_template=match.group("tag_template"),
        asset=match.group("asset"),
        raw=default_url,
    )


def git_show_toml(ref: str, path: Path) -> dict | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path.as_posix()}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return tomllib.loads(result.stdout)
    except Exception as exc:  # noqa: BLE001
        print(f"warn: failed to parse {ref}:{path}: {exc}", file=sys.stderr)
        return None


def classify_eligibility(
    world_id: str,
    local: dict,
    upstream: dict | None,
    parsed_url: GithubDefaultUrl | None,
) -> str | None:
    """Return reason string if eligible, else None."""
    if parsed_url is None:
        return None
    if local.get("supported") is True:
        return None
    if upstream is None:
        return "fork-only"
    if upstream.get("supported") is True:
        return "demoted"
    return None


def version_key(version: str) -> Version:
    return Version(version)


def latest_indexed_version(versions: dict[str, object]) -> Version | None:
    latest: Version | None = None
    for raw in versions:
        try:
            parsed = version_key(str(raw))
        except InvalidVersion:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest


def extract_semver_from_tag(tag: str) -> str | None:
    match = SEMVER_RE.search(tag)
    if not match:
        return None
    candidate = match.group("version")
    try:
        Version(candidate)
    except InvalidVersion:
        return None
    return candidate


def github_api_get(url: str, token: str | None) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "sylvanova-index-discover-new-versions",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def list_releases(owner: str, repo: str, token: str | None) -> list[dict]:
    releases: list[dict] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        url = f"https://api.github.com/repos/{owner}/{repo}/releases?{query}"
        payload = github_api_get(url, token)
        if not isinstance(payload, list) or not payload:
            break
        releases.extend(payload)
        if len(payload) < 100:
            break
        page += 1
    return releases


def check_url(url: str, timeout: float = 30.0) -> bool:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status < 400
    except urllib.error.HTTPError as exc:
        if exc.code not in (403, 405, 501):
            return False
    except urllib.error.URLError:
        pass

    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Range": "bytes=0-0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status < 400
    except Exception:  # noqa: BLE001
        return False


def find_asset_url(release: dict, asset_name: str) -> str | None:
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("name") == asset_name:
            url = asset.get("browser_download_url")
            if isinstance(url, str) and url:
                return url
    return None


def collect_candidates(
    parsed_url: GithubDefaultUrl,
    existing_versions: dict[str, object],
    token: str | None,
    *,
    check_urls: bool,
) -> list[CandidateVersion]:
    latest = latest_indexed_version(existing_versions)
    releases = list_releases(parsed_url.owner, parsed_url.repo, token)
    found: dict[str, CandidateVersion] = {}

    for release in releases:
        if release.get("draft") is True:
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not tag:
            continue
        version = extract_semver_from_tag(tag)
        if version is None:
            continue
        if version in existing_versions or version in found:
            continue
        try:
            parsed_version = version_key(version)
        except InvalidVersion:
            continue
        if latest is None or parsed_version <= latest:
            continue

        asset_url = find_asset_url(release, parsed_url.asset)
        if asset_url is None:
            continue

        templated = parsed_url.raw.replace("{{version}}", version)
        uses_default = templated == asset_url
        chosen_url = templated if uses_default else asset_url
        if check_urls and not check_url(chosen_url):
            print(
                f"warn: skipping {parsed_url.owner}/{parsed_url.repo}@{version}: "
                f"URL not reachable ({chosen_url})",
                file=sys.stderr,
            )
            continue
        found[version] = CandidateVersion(
            version=version,
            url=chosen_url,
            uses_default_url=uses_default,
        )

    return sorted(found.values(), key=lambda item: version_key(item.version))


def format_version_line(candidate: CandidateVersion) -> str:
    if candidate.uses_default_url:
        return f'"{candidate.version}" = {{}}'
    escaped = candidate.url.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{candidate.version}" = {{ url = "{escaped}" }}'


def append_versions(path: Path, candidates: list[CandidateVersion]) -> None:
    if not candidates:
        return
    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    if "[versions]" not in text:
        raise RuntimeError(f"{path}: missing [versions] table")

    lines = [format_version_line(candidate) for candidate in candidates]
    path.write_text(text + "\n".join(lines) + "\n", encoding="utf-8")


def discover_eligible(
    index_dir: Path,
    upstream_ref: str,
) -> list[tuple[str, Path, dict, GithubDefaultUrl, str]]:
    eligible: list[tuple[str, Path, dict, GithubDefaultUrl, str]] = []
    for path in sorted(index_dir.glob("*.toml")):
        local = load_toml(path)
        if local is None:
            continue
        default_url = local.get("default_url")
        parsed_url = (
            parse_github_default_url(default_url)
            if isinstance(default_url, str)
            else None
        )
        upstream = git_show_toml(upstream_ref, path)
        reason = classify_eligibility(path.stem, local, upstream, parsed_url)
        if reason is None or parsed_url is None:
            continue
        print(f"eligible: {path.stem} ({reason})")
        eligible.append((path.stem, path, local, parsed_url, reason))
    return eligible


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=Path("index"),
        help="Path to the index/ directory",
    )
    parser.add_argument(
        "--upstream-ref",
        default="upstream/main",
        help="Git ref for ionium upstream (default: upstream/main)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report candidates without rewriting TOML files",
    )
    parser.add_argument(
        "--skip-url-check",
        action="store_true",
        help="Skip HTTP reachability checks for candidate URLs",
    )
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    eligible = discover_eligible(args.index_dir, args.upstream_ref)
    if not eligible:
        print("No eligible fork-diverged worlds found")
        print("changed=false")
        return 0

    changed = False
    for world_id, path, local, parsed_url, reason in eligible:
        versions = local.get("versions")
        if not isinstance(versions, dict):
            print(f"warn: {world_id}: missing [versions]; skipping", file=sys.stderr)
            continue
        candidates = collect_candidates(
            parsed_url,
            versions,
            token,
            check_urls=not args.skip_url_check,
        )
        if not candidates:
            print(f"{world_id}: no newer versions ({reason})")
            continue
        summary = ", ".join(candidate.version for candidate in candidates)
        print(f"{world_id}: adding {summary} ({reason})")
        if not args.dry_run:
            append_versions(path, candidates)
        changed = True

    print(f"changed={'true' if changed else 'false'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
