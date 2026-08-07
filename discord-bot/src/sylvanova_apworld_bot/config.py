from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

_DEFAULT_MAX_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class Settings:
	discord_token: str
	discord_guild_id: int
	github_token: str
	index_repo: str
	index_base_branch: str
	pr_branch_prefix: str
	apworld_max_bytes: int


def load_settings() -> Settings:
	load_dotenv()
	token = os.environ.get("DISCORD_TOKEN", "").strip()
	guild = os.environ.get("DISCORD_GUILD_ID", "").strip()
	github = os.environ.get("GITHUB_TOKEN", "").strip()
	if not token or not guild or not github:
		raise RuntimeError(
			"DISCORD_TOKEN, DISCORD_GUILD_ID, and GITHUB_TOKEN are required "
			"(see .env.example)"
		)
	max_bytes_raw = os.environ.get("APWORLD_MAX_BYTES", "").strip()
	apworld_max_bytes = int(max_bytes_raw) if max_bytes_raw else _DEFAULT_MAX_BYTES
	return Settings(
		discord_token=token,
		discord_guild_id=int(guild),
		github_token=github,
		index_repo=os.environ.get("INDEX_REPO", "chouticly/SylvaNova-archipelago-index").strip(),
		index_base_branch=os.environ.get("INDEX_BASE_BRANCH", "main").strip(),
		pr_branch_prefix=os.environ.get("PR_BRANCH_PREFIX", "bot/apworld-").strip(),
		apworld_max_bytes=apworld_max_bytes,
	)
