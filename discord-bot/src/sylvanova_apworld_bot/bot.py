from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands

from .config import Settings, load_settings
from .discover import DiscoveredWorld, DiscoveryError, discover_from_release_url
from .github_pr import IndexPullRequestClient
from .toml_template import render_discovered_toml

log = logging.getLogger("sylvanova_apworld_bot")

_ALREADY_HOSTED = (
	"This apworld is already hosted in the SylvaNova index. "
	"Chou or Virunas can add or update versions for worlds that are already listed."
)

_CONFIRM_TIMEOUT_SECONDS = 600


class ApworldBot(discord.Client):
	def __init__(self, settings: Settings):
		intents = discord.Intents.default()
		super().__init__(intents=intents)
		self.settings = settings
		self.tree = app_commands.CommandTree(self)
		self.github = IndexPullRequestClient(
			token=settings.github_token,
			repo_full_name=settings.index_repo,
			base_branch=settings.index_base_branch,
			branch_prefix=settings.pr_branch_prefix,
		)

	async def setup_hook(self) -> None:
		guild = discord.Object(id=self.settings.discord_guild_id)
		self.tree.copy_global_to(guild=guild)
		await self.tree.sync(guild=guild)
		log.info("Synced slash commands to guild %s", self.settings.discord_guild_id)


class ConfirmRequestView(discord.ui.View):
	def __init__(
		self,
		*,
		requester_id: int,
		world: DiscoveredWorld,
		toml_body: str,
		github: IndexPullRequestClient,
		requested_by: str,
	):
		super().__init__(timeout=_CONFIRM_TIMEOUT_SECONDS)
		self.requester_id = requester_id
		self.world = world
		self.toml_body = toml_body
		self.github = github
		self.requested_by = requested_by
		self.message: discord.WebhookMessage | discord.Message | None = None

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		if interaction.user.id != self.requester_id:
			await interaction.response.send_message(
				"Only the user who ran `/request-apworld` can confirm this.",
				ephemeral=True,
			)
			return False
		return True

	async def on_timeout(self) -> None:
		self._disable_children()
		if self.message is not None:
			try:
				await self.message.edit(
					content="Request timed out — run `/request-apworld` again if you still want to submit.",
					embed=None,
					view=self,
				)
			except discord.HTTPException:
				log.debug("Failed to edit timed-out confirm message", exc_info=True)

	def _disable_children(self) -> None:
		for child in self.children:
			if isinstance(child, discord.ui.Button):
				child.disabled = True

	@discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
	async def confirm(
		self,
		interaction: discord.Interaction,
		button: discord.ui.Button,
	) -> None:
		await interaction.response.defer(ephemeral=True, thinking=True)
		self._disable_children()
		try:
			if self.message is not None:
				await self.message.edit(view=self)
		except discord.HTTPException:
			pass

		try:
			pr = await asyncio.to_thread(
				self.github.open_apworld_pr,
				apworld=self.world.apworld_id,
				toml_body=self.toml_body,
				requested_by=self.requested_by,
				world=self.world,
			)
		except Exception as exc:  # noqa: BLE001 - surface to Discord user
			log.exception("confirm open_apworld_pr failed")
			await interaction.followup.send(f"Failed to open PR: {exc}", ephemeral=True)
			self.stop()
			return

		await interaction.followup.send(
			f"Opened PR #{pr.number}: {pr.url}\n"
			"Index CI will validate, fuzz, and auto-merge when green.",
			ephemeral=True,
		)
		if self.message is not None:
			try:
				await self.message.edit(
					content=f"Confirmed — opened PR #{pr.number}.",
					embed=None,
					view=self,
				)
			except discord.HTTPException:
				pass
		self.stop()

	@discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
	async def cancel(
		self,
		interaction: discord.Interaction,
		button: discord.ui.Button,
	) -> None:
		self._disable_children()
		await interaction.response.edit_message(
			content="Cancelled — no PR was opened.",
			embed=None,
			view=self,
		)
		self.stop()


def _preview_embed(world: DiscoveredWorld, toml_body: str) -> discord.Embed:
	url_label = "default_url" if world.uses_default_url else "url"
	embed = discord.Embed(
		title="Confirm apworld index PR",
		description=(
			"Review the auto-discovered metadata. "
			"Confirm to open an add-only PR on the SylvaNova index."
		),
		color=discord.Color.blurple(),
	)
	embed.add_field(name="apworld id", value=f"`{world.apworld_id}`", inline=True)
	embed.add_field(name="version", value=f"`{world.version}`", inline=True)
	embed.add_field(name="game name", value=world.name, inline=False)
	if world.display_name:
		embed.add_field(name="display_name", value=world.display_name, inline=False)
	embed.add_field(name="home", value=world.home, inline=False)
	embed.add_field(name=url_label, value=world.url_or_template, inline=False)
	toml_block = toml_body.strip()
	if len(toml_block) > 900:
		toml_block = toml_block[:900] + "\n..."
	embed.add_field(name="Proposed TOML", value=f"```toml\n{toml_block}\n```", inline=False)
	return embed


def build_bot(settings: Settings) -> ApworldBot:
	bot = ApworldBot(settings)

	@bot.tree.command(
		name="request-apworld",
		description="Submit a GitHub release .apworld link to open an index PR",
	)
	@app_commands.describe(
		url="Direct GitHub release asset URL ending in .apworld",
	)
	async def request_apworld(
		interaction: discord.Interaction,
		url: str,
	) -> None:
		await interaction.response.defer(ephemeral=True, thinking=True)
		try:
			world = await asyncio.to_thread(
				discover_from_release_url,
				url.strip(),
				max_bytes=bot.settings.apworld_max_bytes,
			)
			if bot.github.apworld_exists(world.apworld_id):
				await interaction.followup.send(_ALREADY_HOSTED, ephemeral=True)
				return

			toml_body = render_discovered_toml(world)
			requested_by = interaction.user.name if interaction.user else "unknown"
			view = ConfirmRequestView(
				requester_id=interaction.user.id,
				world=world,
				toml_body=toml_body,
				github=bot.github,
				requested_by=requested_by,
			)
			message = await interaction.followup.send(
				embed=_preview_embed(world, toml_body),
				view=view,
				ephemeral=True,
				wait=True,
			)
			view.message = message
		except DiscoveryError as exc:
			await interaction.followup.send(f"Could not discover apworld: {exc}", ephemeral=True)
		except Exception as exc:  # noqa: BLE001 - surface to Discord user
			log.exception("request-apworld failed")
			await interaction.followup.send(f"Failed: {exc}", ephemeral=True)

	return bot


def main() -> None:
	logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
	settings = load_settings()
	bot = build_bot(settings)
	bot.run(settings.discord_token)
