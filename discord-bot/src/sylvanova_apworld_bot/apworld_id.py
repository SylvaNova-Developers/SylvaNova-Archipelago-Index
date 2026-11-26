from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

_APWORLD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_STEM_SCRIPT = _REPO_ROOT / "scripts/ci/apworld_package_stem.py"


def _package_stem_from_zip(apworld: Path) -> str:
    if _STEM_SCRIPT.is_file():
        spec = importlib.util.spec_from_file_location("apworld_package_stem", _STEM_SCRIPT)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"could not load {_STEM_SCRIPT}")
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault("apworld_package_stem", module)
        spec.loader.exec_module(module)
        return module.package_stem_from_zip(apworld)
    raise RuntimeError(
        "apworld package stem script missing; clone the index repo beside the bot"
    )


def _resolve_download_url(url: str, version: str) -> str:
    return url.replace("{{version}}", version)


def _download_apworld(url: str) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".apworld", delete=False) as handle:
        dest = Path(handle.name)
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=120.0) as response:
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status} while downloading {url}")
            dest.write_bytes(response.read())
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return dest


def resolve_apworld_index_id(*, apworld: str, url: str, version: str) -> str:
    """Return the index filename stem, derived from the zip when needed."""
    download_url = _resolve_download_url(url.strip(), version.strip())
    apworld_path = _download_apworld(download_url)
    try:
        package_stem = _package_stem_from_zip(apworld_path)
    finally:
        apworld_path.unlink(missing_ok=True)

    requested = apworld.strip()
    if requested:
        if not _APWORLD_ID.match(requested):
            raise ValueError(
                "apworld id must be alphanumeric with optional _/- "
                f"(got {apworld!r})"
            )
        if requested != package_stem:
            raise ValueError(
                f"apworld id {requested!r} does not match the zip package "
                f"directory {package_stem!r}; use {package_stem!r} as the id"
            )
        return requested

    if not _APWORLD_ID.match(package_stem):
        raise ValueError(
            f"zip package directory {package_stem!r} is not a valid apworld id"
        )
    return package_stem