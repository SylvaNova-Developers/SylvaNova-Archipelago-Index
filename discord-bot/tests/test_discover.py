from __future__ import annotations

import io
import unittest
import zipfile

from sylvanova_apworld_bot.discover import (
	DiscoveryError,
	build_url_or_template,
	coerce_semver,
	derive_version,
	discover_from_release_url,
	extract_apworld_id,
	extract_game_name,
	manual_display_name,
	parse_github_release_asset_url,
)
from sylvanova_apworld_bot.toml_template import render_discovered_toml


def _make_apworld(package: str, init_source: str) -> bytes:
	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w") as archive:
		archive.writestr(f"{package}/__init__.py", init_source)
		archive.writestr(f"{package}/Items.py", "# items\n")
	return buffer.getvalue()


class ParseUrlTests(unittest.TestCase):
	def test_parses_release_asset(self) -> None:
		url = "https://github.com/Ishigh1/Archipelago/releases/download/2048-1.1.2/2048.apworld"
		asset = parse_github_release_asset_url(url)
		self.assertEqual(asset.owner, "Ishigh1")
		self.assertEqual(asset.repo, "Archipelago")
		self.assertEqual(asset.tag, "2048-1.1.2")
		self.assertEqual(asset.asset, "2048.apworld")
		self.assertEqual(asset.home, "https://github.com/Ishigh1/Archipelago")

	def test_rejects_release_page(self) -> None:
		with self.assertRaises(DiscoveryError) as ctx:
			parse_github_release_asset_url(
				"https://github.com/Ishigh1/Archipelago/releases/tag/2048-1.1.2"
			)
		self.assertIn("direct GitHub release asset", str(ctx.exception))

	def test_rejects_non_github(self) -> None:
		with self.assertRaises(DiscoveryError):
			parse_github_release_asset_url(
				"https://example.com/files/world.apworld"
			)


class SemverTests(unittest.TestCase):
	def test_coerce_short_version(self) -> None:
		self.assertEqual(coerce_semver("0.8"), "0.8.0")
		self.assertEqual(coerce_semver("v1.2.3"), "1.2.3")
		self.assertEqual(coerce_semver("1.0.0-beta.1"), "1.0.0-beta.1")

	def test_derive_from_prefixed_tag(self) -> None:
		self.assertEqual(
			derive_version(tag="2048-1.1.2", asset="2048.apworld", apworld_id="2048"),
			"1.1.2",
		)

	def test_derive_from_asset_filename(self) -> None:
		self.assertEqual(
			derive_version(tag="release", asset="demo-0.8.apworld", apworld_id="demo"),
			"0.8.0",
		)

	def test_derive_failure(self) -> None:
		with self.assertRaises(DiscoveryError):
			derive_version(tag="latest", asset="demo.apworld", apworld_id="demo")


class DefaultUrlTests(unittest.TestCase):
	def test_templates_when_version_in_url(self) -> None:
		url = "https://github.com/o/r/releases/download/2048-1.1.2/2048.apworld"
		template, uses = build_url_or_template(url, "1.1.2")
		self.assertTrue(uses)
		self.assertEqual(
			template,
			"https://github.com/o/r/releases/download/2048-{{version}}/2048.apworld",
		)

	def test_keeps_explicit_url_when_version_absent(self) -> None:
		url = "https://github.com/o/r/releases/download/nightly/demo.apworld"
		result, uses = build_url_or_template(url, "1.0.0")
		self.assertFalse(uses)
		self.assertEqual(result, url)


class ManualDisplayNameTests(unittest.TestCase):
	def test_manual_game_author(self) -> None:
		self.assertEqual(
			manual_display_name("Manual_pokemonss_riannehx"),
			"Manual: pokemonss",
		)
		self.assertEqual(
			manual_display_name("Manual_EuroTruckSim2_bdi"),
			"Manual: EuroTruckSim2",
		)

	def test_non_manual(self) -> None:
		self.assertIsNone(manual_display_name("Celeste (Open World)"))


class ArchiveDiscoveryTests(unittest.TestCase):
	def test_extract_id_and_game(self) -> None:
		payload = _make_apworld(
			"DemoWorld",
			'from worlds.AutoWorld import World\n\nclass Demo(World):\n\tgame = "Demo Game"\n',
		)
		apworld_id = extract_apworld_id(payload)
		self.assertEqual(apworld_id, "demoworld")
		self.assertEqual(extract_game_name(payload, apworld_id), "Demo Game")

	def test_full_discover_and_toml(self) -> None:
		payload = _make_apworld(
			"demo",
			'class DemoWorld:\n\tgame = "Demo Game"\n',
		)
		url = "https://github.com/acme/demo/releases/download/demo-1.2.3/demo.apworld"
		world = discover_from_release_url(url, archive_bytes=payload)
		self.assertEqual(world.apworld_id, "demo")
		self.assertEqual(world.name, "Demo Game")
		self.assertEqual(world.version, "1.2.3")
		self.assertEqual(world.home, "https://github.com/acme/demo")
		self.assertTrue(world.uses_default_url)
		self.assertEqual(
			world.url_or_template,
			"https://github.com/acme/demo/releases/download/demo-{{version}}/demo.apworld",
		)
		toml = render_discovered_toml(world)
		self.assertIn('name = "Demo Game"', toml)
		self.assertIn("default_url =", toml)
		self.assertIn('"1.2.3" = {}', toml)

	def test_manual_display_name_in_toml(self) -> None:
		payload = _make_apworld(
			"manual_demo_author",
			'game = "Manual_Demo_Author"\n',
		)
		url = "https://github.com/acme/demo/releases/download/v0.0.1/manual_demo_author.apworld"
		world = discover_from_release_url(url, archive_bytes=payload)
		self.assertEqual(world.display_name, "Manual: Demo")
		toml = render_discovered_toml(world)
		self.assertIn('display_name = "Manual: Demo"', toml)


if __name__ == "__main__":
	unittest.main()
