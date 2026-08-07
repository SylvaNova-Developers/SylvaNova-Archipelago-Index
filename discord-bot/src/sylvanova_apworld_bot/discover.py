from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from .toml_template import validate_apworld_id

_RELEASE_ASSET = re.compile(
	r"^https://github\.com/"
	r"(?P<owner>[^/]+)/"
	r"(?P<repo>[^/]+)/"
	r"releases/download/"
	r"(?P<tag>[^/]+)/"
	r"(?P<asset>[^/]+\.apworld)$",
	re.IGNORECASE,
)

_GAME_ASSIGNMENT = re.compile(
	r"^\s*game\s*=\s*(?:['\"]([^'\"]+)['\"]|([A-Za-z_][A-Za-z0-9_]*))",
	re.MULTILINE,
)

_SEMVER_CORE = re.compile(
	r"(?P<major>0|[1-9]\d*)"
	r"\.(?P<minor>0|[1-9]\d*)"
	r"(?:\.(?P<patch>0|[1-9]\d*))?"
	r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
	r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
	r"(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?"
)

_DEFAULT_MAX_BYTES = 50 * 1024 * 1024
_USER_AGENT = "SylvaNova-apworld-bot/0.1 (+https://github.com/chouticly/SylvaNova-archipelago-index)"


@dataclass(frozen=True)
class GitHubReleaseAsset:
	owner: str
	repo: str
	tag: str
	asset: str
	url: str

	@property
	def home(self) -> str:
		return f"https://github.com/{self.owner}/{self.repo}"


@dataclass(frozen=True)
class DiscoveredWorld:
	apworld_id: str
	name: str
	version: str
	home: str
	source_url: str
	url_or_template: str
	display_name: str | None
	uses_default_url: bool


class DiscoveryError(ValueError):
	"""User-facing discovery failure."""


def parse_github_release_asset_url(url: str) -> GitHubReleaseAsset:
	value = url.strip()
	match = _RELEASE_ASSET.match(value)
	if not match:
		raise DiscoveryError(
			"URL must be a direct GitHub release asset download ending in `.apworld` "
			"(e.g. https://github.com/owner/repo/releases/download/tag/world.apworld). "
			"Open the release page, right-click the `.apworld` asset, and copy the link."
		)
	return GitHubReleaseAsset(
		owner=match.group("owner"),
		repo=match.group("repo"),
		tag=unquote(match.group("tag")),
		asset=unquote(match.group("asset")),
		url=value.split("?")[0],
	)


def download_apworld(url: str, *, max_bytes: int = _DEFAULT_MAX_BYTES) -> bytes:
	parsed = urlparse(url)
	if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
		raise DiscoveryError("Only https://github.com/... release asset URLs are accepted.")

	request = Request(url, headers={"User-Agent": _USER_AGENT})
	try:
		with urlopen(request, timeout=60) as response:
			content_length = response.headers.get("Content-Length")
			if content_length is not None and int(content_length) > max_bytes:
				raise DiscoveryError(
					f"Apworld is larger than the {max_bytes // (1024 * 1024)}MB download limit."
				)
			chunks: list[bytes] = []
			total = 0
			while True:
				chunk = response.read(64 * 1024)
				if not chunk:
					break
				total += len(chunk)
				if total > max_bytes:
					raise DiscoveryError(
						f"Apworld is larger than the {max_bytes // (1024 * 1024)}MB download limit."
					)
				chunks.append(chunk)
	except HTTPError as exc:
		raise DiscoveryError(f"Failed to download apworld (HTTP {exc.code}).") from exc
	except URLError as exc:
		raise DiscoveryError(f"Failed to download apworld: {exc.reason}") from exc

	return b"".join(chunks)


def extract_apworld_id(archive_bytes: bytes) -> str:
	try:
		with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
			names = [
				name
				for name in archive.namelist()
				if name and not name.startswith("__MACOSX")
			]
	except zipfile.BadZipFile as exc:
		raise DiscoveryError("Downloaded file is not a valid .apworld (zip) archive.") from exc

	roots = sorted({name.split("/", 1)[0] for name in names})
	candidates = [
		root
		for root in roots
		if any(entry.startswith(root + "/") for entry in names)
	]
	if not candidates:
		raise DiscoveryError("Apworld archive has no top-level package directory.")
	if len(candidates) != 1:
		raise DiscoveryError(
			"Apworld archive must contain exactly one top-level package directory "
			f"(found {candidates!r})."
		)
	return validate_apworld_id(candidates[0].lower())


def extract_game_name(archive_bytes: bytes, apworld_id: str) -> str:
	with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
		py_members = [
			info
			for info in archive.infolist()
			if info.filename.endswith(".py") and not info.is_dir()
		]
		if not py_members:
			raise DiscoveryError("Apworld contains no Python files to discover `game = ...`.")

		preferred = f"{apworld_id}/__init__.py"
		ordered = sorted(
			py_members,
			key=lambda info: (
				0 if info.filename.lower() == preferred else 1,
				0 if info.filename.lower().endswith("/__init__.py") else 1,
				info.filename.lower(),
			),
		)

		found: list[tuple[str, str]] = []
		for info in ordered:
			text = archive.read(info).decode("utf-8", errors="replace")
			for match in _GAME_ASSIGNMENT.finditer(text):
				literal = match.group(1)
				if literal is None:
					continue
				found.append((info.filename, literal))

		if not found:
			raise DiscoveryError(
				"Could not find a string `game = \"...\"` assignment in the apworld. "
				"Ask Chou or Virunas to add it manually."
			)

		# Prefer package __init__.py hits; require a unique name among preferred files.
		init_hits = [name for path, name in found if path.lower().endswith("/__init__.py")]
		names = init_hits or [name for _, name in found]
		unique = sorted(set(names))
		if len(unique) != 1:
			raise DiscoveryError(
				"Ambiguous `game` values in the apworld: "
				+ ", ".join(repr(n) for n in unique)
				+ ". Ask Chou or Virunas to add it manually."
			)
		return unique[0]


def manual_display_name(name: str) -> str | None:
	if not name.startswith("Manual_"):
		return None
	parts = name.split("_")
	if len(parts) < 2:
		return None
	if len(parts) == 2:
		game = parts[1]
	else:
		game = "_".join(parts[1:-1])
	if not game:
		return None
	return f"Manual: {game}"


def coerce_semver(raw: str) -> str | None:
	value = raw.strip()
	if value.startswith("v") or value.startswith("V"):
		value = value[1:]
	match = _SEMVER_CORE.fullmatch(value) or _SEMVER_CORE.search(value)
	if not match:
		return None
	major = match.group("major")
	minor = match.group("minor")
	patch = match.group("patch") or "0"
	prerelease = match.group("prerelease")
	build = match.group("build")
	version = f"{major}.{minor}.{patch}"
	if prerelease:
		version = f"{version}-{prerelease}"
	if build:
		version = f"{version}+{build}"
	return version


def derive_version(*, tag: str, asset: str, apworld_id: str) -> str:
	candidates: list[str] = []
	lower_id = apworld_id.lower()
	for source in (tag, asset.removesuffix(".apworld")):
		text = source
		if text.lower().startswith(f"{lower_id}-"):
			text = text[len(apworld_id) + 1 :]
		elif text.lower().startswith(f"{lower_id}_"):
			text = text[len(apworld_id) + 1 :]
		elif text.startswith("v") or text.startswith("V"):
			maybe = text[1:]
			if maybe and (maybe[0].isdigit() or maybe[0] == "."):
				text = maybe
		candidates.append(text)
		candidates.append(source)

	for candidate in candidates:
		version = coerce_semver(candidate)
		if version:
			return version

	raise DiscoveryError(
		f"Could not derive a semver version from tag {tag!r} or asset {asset!r}. "
		"Use a release tagged with a version (e.g. 1.2.3 or world-1.2.3), "
		"or ask Chou or Virunas to add it."
	)


def build_url_or_template(source_url: str, version: str) -> tuple[str, bool]:
	"""Return (url_or_template, uses_default_url)."""
	if not version or version not in source_url:
		return source_url, False

	# Replace the version occurrence that round-trips when substituted.
	# Prefer the rightmost occurrence (usually the tag), then verify.
	start = 0
	positions: list[int] = []
	while True:
		idx = source_url.find(version, start)
		if idx < 0:
			break
		positions.append(idx)
		start = idx + 1
	if not positions:
		return source_url, False

	for idx in reversed(positions):
		template = source_url[:idx] + "{{version}}" + source_url[idx + len(version) :]
		if template.replace("{{version}}", version) == source_url:
			return template, True

	return source_url, False


def discover_from_release_url(
	url: str,
	*,
	archive_bytes: bytes | None = None,
	max_bytes: int = _DEFAULT_MAX_BYTES,
) -> DiscoveredWorld:
	asset = parse_github_release_asset_url(url)
	payload = archive_bytes if archive_bytes is not None else download_apworld(asset.url, max_bytes=max_bytes)
	apworld_id = extract_apworld_id(payload)
	name = extract_game_name(payload, apworld_id)
	version = derive_version(tag=asset.tag, asset=asset.asset, apworld_id=apworld_id)
	url_or_template, uses_default_url = build_url_or_template(asset.url, version)
	return DiscoveredWorld(
		apworld_id=apworld_id,
		name=name,
		version=version,
		home=asset.home,
		source_url=asset.url,
		url_or_template=url_or_template,
		display_name=manual_display_name(name),
		uses_default_url=uses_default_url,
	)
