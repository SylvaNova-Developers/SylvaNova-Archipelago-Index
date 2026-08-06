from __future__ import annotations

import logging

import discord
from discord import app_commands

from .config import Settings, load_settings
from .github_pr import IndexPullRequestClient
from .toml_template import render_world_toml, validate_apworld_id

log = logging.getLogger("sylvanova_apworld_bot")


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


def build_bot(settings: Settings) -> ApworldBot:
    bot = ApworldBot(settings)

    @bot.tree.command(
        name="request-apworld",
        description="Open a PR to add an apworld to the SylvaNova index",
    )
    @app_commands.describe(
        apworld="Apworld id (filename stem under index/)",
        name="Game name used in YAML",
        url="Direct .apworld URL, or a default_url template containing {{version}}",
        version="Semver version to register",
        home="Optional Discord/GitHub/home link",
        display_name="Optional pretty display name",
    )
    async def request_apworld(
        interaction: discord.Interaction,
        apworld: str,
        name: str,
        url: str,
        version: str,
        home: str | None = None,
        display_name: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            apworld_id = validate_apworld_id(apworld)
            toml_body = render_world_toml(
                name=name.strip(),
                url=url.strip(),
                version=version.strip(),
                home=home.strip() if home else None,
                display_name=display_name.strip() if display_name else None,
            )
            requester = (
                interaction.user.name
                if interaction.user
                else "unknown"
            )
            pr = bot.github.open_apworld_pr(
                apworld=apworld_id,
                toml_body=toml_body,
                requested_by=requester,
            )
        except Exception as exc:  # noqa: BLE001 - surface to Discord user
            log.exception("request-apworld failed")
            await interaction.followup.send(f"Failed: {exc}", ephemeral=True)
            return

        await interaction.followup.send(
            f"Opened PR #{pr.number}: {pr.url}\n"
            "Index CI will validate, fuzz, and auto-merge when green.",
            ephemeral=True,
        )

    return bot


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    bot = build_bot(settings)
    bot.run(settings.discord_token)
