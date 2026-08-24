# SylvaNova apworld request bot (scaffold)

Minimal Discord + GitHub framework for submitting apworld entries to
[`SylvaNova-Developers/SylvaNova-Archipelago-Index`](https://github.com/SylvaNova-Developers/SylvaNova-Archipelago-Index).

**Status:** scaffold only — not wired to a production Discord application yet.
Fuzz / validate / auto-merge stay in the index repo's `PR CI` workflow; this bot
only opens the PR.

## Split into its own repo (recommended)

This directory is portable. When you are ready:

```bash
gh repo create SylvaNova-Developers/SylvaNova-Apworld-Bot --public --source=discord-bot --remote=origin --push
```

(or copy `discord-bot/` to a new checkout and push)

## What it does

Slash command `/request-apworld`:

| Option | Required | Meaning |
|--------|----------|---------|
| `apworld` | yes | Apworld id (becomes `index/{apworld}.toml`) |
| `name` | yes | Game name used in YAML |
| `url` | yes | Direct `.apworld` download URL (or a `default_url` template with `{{version}}`) |
| `version` | yes | Semver version string |
| `home` | no | Discord thread / GitHub / homepage link |
| `display_name` | no | Pretty name when `name` is ugly |

The bot opens a PR on the index repo that adds the TOML. Index `PR CI` then
validates, fuzzes, and auto-merges when green. Collaborators can comment
`/force-merge` (or `r+`) on the PR to land despite a high fuzz failure rate.

## Setup

```bash
cd discord-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# fill DISCORD_TOKEN, DISCORD_GUILD_ID, GITHUB_TOKEN
PYTHONPATH=src python -m sylvanova_apworld_bot
```

Create a Discord application → Bot → enable `applications.commands`, invite the
bot with `applications.commands` + `bot` scopes. Create a GitHub PAT (or fine-grained
token) with `contents:write` and `pull_requests:write` on the index repo.

## Env

See [`.env.example`](.env.example).
