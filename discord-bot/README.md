# SylvaNova apworld request bot

Discord bot that turns a **GitHub release `.apworld` download link** into an add-only
PR on [`chouticly/SylvaNova-archipelago-index`](https://github.com/chouticly/SylvaNova-archipelago-index).

Fuzz / validate / auto-merge stay in the index repo's `PR CI` workflow; this bot
only discovers metadata and opens the PR.

## What it does

Slash command `/request-apworld`:

| Option | Required | Meaning |
|--------|----------|---------|
| `url` | yes | Direct GitHub release asset URL ending in `.apworld` |

Example:

`https://github.com/owner/repo/releases/download/1.2.3/world.apworld`

Flow:

1. Bot downloads the asset and auto-discovers apworld id, game name, version, and home.
2. If `index/{apworld}.toml` already exists, it tells the user that **Chou or Virunas**
   can add or update worlds that are already hosted (no PR).
3. Otherwise it shows a preview (metadata + proposed TOML) with **Confirm** / **Cancel**.
4. On Confirm, it opens an add-only PR. Index CI validates, fuzzes, and auto-merges when green.

Only direct release **asset** links are accepted (not the release page URL).

## Split into its own repo (optional)

This directory is portable. When you are ready:

```bash
gh repo create chouticly/SylvaNova-apworld-bot --public --source=discord-bot --remote=origin --push
```

(or copy `discord-bot/` to a new checkout and push)

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

## Tests

```bash
cd discord-bot
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Env

See [`.env.example`](.env.example). Optional: `APWORLD_MAX_BYTES` (default 52428800).
