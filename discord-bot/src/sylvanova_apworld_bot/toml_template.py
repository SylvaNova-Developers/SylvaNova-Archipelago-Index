from __future__ import annotations

from .apworld_id import resolve_apworld_index_id


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


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
