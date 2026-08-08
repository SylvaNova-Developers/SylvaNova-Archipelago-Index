# How to add/update worlds

- Add an `{apworld}.toml` file in the `index/` directory. The name of the file **MUST** match the apworld name. So for `A link to the Past` which apworld is `alttp`, you would create a file named `alttp.toml`.
- In the `toml` file, add a name, `name = "A Link to the Past"`. That name **MUST** match the world name. If you're unsure what that means, it's the name used in your YAML.
- If the `name` field is nondescriptive or "ugly", add a `display_name` field with a pretty name. This especially useful for manuals where the name is `Manual_{game}_{author}`. In that case, add a `display_name` with `"Manual: {game}"`.
- Add a `home` field if applicable. In order of preference, it should contain a link to the discord thread, the github repo, any other webpage where the apworld might live. If there's none (i.e you made this apworld and it's not publically available anywhere else, omit the field).
- If the world needs to be tagged specifically, add a `tags = [...]`, available tags are: `ad` to mark the world as being from the after dark server.
- Add a `[versions]` section, one version per line. It should look something like this: `"{version}" = { src }`. Read the following sections to understand what that means.

## Version

Each version **MUST** be valid [semver](https://semver.org/). It doesn't matter if the apworld doesn't respect semver or doesn't even have a version that would be valid. We use this to make sure versions can be ordered.
If necessary, be creative with your version number.

For example, if an apworld has a release for a version `0.8`, you'd specify version `0.8.0` as the version the index.
If an apworld doesn't specify a version, as is usually the case with manuals, invent one. I tend to count the number of releases in the discord channel and name it `0.0.X`.
It's not always feasible though because of discord UX choices regarding search. It's fine to just go with `0.0.1`. When updating those apworlds, just increment the version number.

## Src

The index supports two different source types, `url` and `local`.
Since we're no longer accepting local sources, always use `url`.

Examples:

- The apworld is released on github and has a direct download link to the apworld in the release:
  `"0.1.0" = { url = "https://github.com/foo/bar/releases/download/0.1.0/foo.apworld" }`

### Special case for `url` releases

When the author uses tags that are semver compatible, it's possible to add a `default_url` field instead in the global scope of the toml like this:
`default_url = "https://github.com/foo/bar/releases/download/{{version}}/foo.apworld` and to specify versions like this: `"0.1.0" = {}`.
This makes it easier to update and can be used to automatically fetch newer versions so it's the prefered way of doing things.


# Criteria for inclusion

> [!IMPORTANT]
> Do **NOT** make demands of apworld authors to cater their apworlds for inclusion in this index.

- We will only accept apworlds that have a stable public URL: For example, a GitHub release artifact, or otherwise a direct link to the `.apworld` file. We will no longer accept apworlds directly into this repo (i.e. local sources).
- The apworld must not be banned on the Archipelago Discord server for copyright reasons.
- The apworld must not contain big unknown executable binary blobs or depend on any.
- The apworld must not contain obvious flaws that will make life difficult for anyone trying to generate large multiworlds. That includes direct usage of the random module, obvious logic flaws, forced interactivity during generation, or test failures that are deemed problematic.
- The apworld must not make any use of remote resources during generation. That includes checking the internet for the latest release or similar checks.
- The apworld must not require a ROM to generate. Apworlds already present in the index are exempt from this, but I will not accept any new ones.
- The generation failure rate calculated using Eijebong's [fuzzer](https://github.com/ionium-ap/Archipelago-fuzzer) must be below 20% (not counting `OptionError`s).
  - To help removing failures that would be considered restrictive starts, those rates will be calculated with a second [world](https://github.com/ionium-ap/empty-apworld) present that has 100 free locations. Any failures that remain may indicate a logic issue.
  - To help check for other logical issues that could prevent multiworlds from generating, we will also be checking against the following Fuzzer tests. These must fall within the 20% rule:
    - GERpocalypse, checks for issues with Generic Entrance Randomization (GER). See AP docs for more information:  [Entrance Rando](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/entrance%20randomization.md)
    - Indirect conditions, checks for issues related to indirect conditions, see AP docs for more information: [World FAQ](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/apworld_dev_faq.md?plain=1#L101) or [World API](https://github.com/ArchipelagoMW/Archipelago/blob/main/docs/world%20api.md#an-important-note-on-entrance-access-rules)
    - Item counts match the location count
    - Lambda variable capture issues (typically creates incorrect rule conditions)
    - Item/Location references match check (i.e. if Item A is on Location A, both of these should point to each other)
    - No stage output item/location changes (rogue behaviour, do not do this)
  - Some exceptions could be made for failures happening early during generation (before `generate_basic`) as those would most likely be detected by YAML validation and won't result in a big time loss during generation
- If the apworld is a beta for core verified game then it must have a different game name (`LADX` -> `LADX beta`)

- Note: Other Fuzzer tests may also be done on the world at the time of merging into the index, at the benefit of helping devs discover other types of bugs such as:
  - Universal Tracker compatibility issues
  - Determinism (i.e. that using the same random seed number and same input yaml(s) should produce the same outcome every single time)

# SylvaNova automation

This fork tracks [`ionium-ap/Archipelago-index`](https://github.com/ionium-ap/Archipelago-index) `main` automatically and accepts PRs through GitHub Actions (no GitLab / Taskcluster required).

Discord request bot scaffold (portable; split to its own repo when ready): see [`discord-bot/`](discord-bot/).

## Upstream sync

Workflow: `.github/workflows/sync-upstream.yml`

- Runs every 15 minutes (and on `workflow_dispatch`)
- Fast-forwards or merges `ionium-ap/Archipelago-index:main` into this repo's `main`
- On merge conflicts, opens (or comments on) a GitHub issue

Secret: `BOT_PAT` (contents:write; recommended so pushes work with branch protection)

## Diverged world version updates

Workflow: `.github/workflows/update-diverged-worlds.yml`

Upstream sync covers shared worlds. Fork-specific entries need their own release polling:

- Runs every 6 hours (and on `workflow_dispatch`)
- Auto-detects eligible `index/*.toml` files (no manual watch list):
  - GitHub `default_url` with `{{version}}`
  - Not `supported = true` locally
  - Fork-only (missing upstream) **or** demoted (upstream still `supported = true`)
- Polls GitHub Releases, appends semver versions newer than the latest indexed one
- Pushes `bot/update-world-versions`, waits for `validate` + `fuzz-ok`, then fast-forwards `main`
- Post-merge publish then refreshes `index.lock` as usual

Today that covers `celeste_open_world` (demoted) and `tww3` (fork-only). New Discord/PR worlds that match the rules are enrolled on the next run automatically.

## PR acceptance (automatic CI)

Workflow: `.github/workflows/pr-ci.yml`

On every non-draft PR to `main`:

1. **validate** — parse changed `index/*.toml`, reject new `local` sources, check version URLs, run `apwm changes`/`download`
2. **fuzz** — for each changed apworld, run the gate suite (baseline, restrictive-starts / empty world, GER, item/location counts, lambda capture, placement refs, indirect conditions, static output placement, determinism, collect accessibility, UT when available). Failure rate must stay **below 20%** (OptionErrors ignored)
3. **auto-merge** — squash-merges when validate + fuzz succeed

GitHub-hosted runners use a reduced run floor (`FUZZ_RUNS_FULL=1000`, `FUZZ_RUNS_CHECK=500`) versus upstream Taskcluster (`5000` / `500`).

### Force-merge (collaborator fuzz bypass)

When fuzz fails above the gate but you still want the world indexed, a **collaborator / member / owner** can override:

- Comment `/force-merge`, `r+`, or `r++` on the PR (first line exact), or
- Apply label `force-merge` or `bypass-fuzz`

Workflow: `.github/workflows/force-merge.yml`

That path still requires `validate` green on the PR head, best-effort posts a successful `fuzz-ok` override check (via the Actions token — PATs cannot create check runs), then squash-merges with `--admin` when `BOT_PAT` allows it. Use it for high fuzz failure rates you are willing to accept; it does not skip TOML/URL validation.

Recommended repo settings:

- Enable **Allow auto-merge**
- Branch protection on `main` requiring checks `validate` and `fuzz-ok`
- Give `BOT_PAT` permission to admin-merge (bypass required status checks), since force-merge relies on that when `fuzz-ok` has already failed

## Post-merge publish + lobby refresh

Workflow: `.github/workflows/post-merge-publish.yml`

After `main` advances (skips commits marked `[skip ci]`):

1. Builds `apwm` from `chouticly/SylvaNova-archipelago-lobby`
2. Runs `apwm update`; if `index.lock` changed, opens `bot/update-index-lock` PR (direct pushes to `main` are blocked by required checks) and waits for merge
3. If both secrets are set, calls the lobby admin refresh endpoint:
   - `LOBBY_REFRESH_URL` — e.g. `https://your-host/worlds/refresh`
   - `LOBBY_ADMIN_TOKEN` — value for `X-Api-Key`
4. If those secrets are unset, refresh is skipped (safe while no public lobby is deployed)

Point your lobby's `APWORLDS_INDEX_REPO_URL` at this repository so `/worlds/refresh` pulls the SylvaNova index.
