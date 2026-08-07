from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from .discover import DiscoveredWorld

_APWORLD_ID = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")


def validate_apworld_id(apworld: str) -> str:
	value = apworld.strip()
	if not _APWORLD_ID.match(value):
		raise ValueError(
			"apworld id must be lowercase alphanumeric with optional _/- "
			f"(got {apworld!r})"
		)
	return value


def render_world_toml(
	*,
	name: str,
	url: str,
	version: str,
	home: str | None = None,
	display_name: str | None = None,
) -> str:
	"""Build an index/{apworld}.toml body matching the index README format."""
	lines: list[str] = [f'name = "{_escape(name)}"']
	if display_name:
		lines.append(f'display_name = "{_escape(display_name)}"')
	if home:
		lines.append(f'home = "{_escape(home)}"')

	if "{{version}}" in url:
		lines.append(f'default_url = "{_escape(url)}"')
		lines.append("")
		lines.append("[versions]")
		lines.append(f'"{_escape(version)}" = {{}}')
	else:
		lines.append("")
		lines.append("[versions]")
		lines.append(f'"{_escape(version)}" = {{ url = "{_escape(url)}" }}')

	lines.append("")
	return "\n".join(lines)


def render_discovered_toml(world: DiscoveredWorld) -> str:
	return render_world_toml(
		name=world.name,
		url=world.url_or_template,
		version=world.version,
		home=world.home,
		display_name=world.display_name,
	)


def _escape(value: str) -> str:
	return value.replace("\\", "\\\\").replace('"', '\\"')
