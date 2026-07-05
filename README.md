# claude-sync

Keeps Claude Code memory and configuration consistent across multiple
machines (macOS, Windows/WSL, Amazon Workspace) by syncing a curated slice
of `~/.claude/` through this git repo.

## What gets synced

- `~/.claude/CLAUDE.md` (global instructions)
- `~/.claude/skills/`
- `~/.claude/projects/<hash>/memory/` (per-project memory, mapped to a
  stable name via each project's session `cwd`, not the ambiguous encoded
  folder name)
- Only the `enabledPlugins` and `extraKnownMarketplaces` keys of
  `~/.claude/settings.json` — not the plugin cache itself, and not any
  other settings (hooks, effort level, etc. stay machine-local)

## How it works

`sync.py` runs on a schedule (every 15 minutes via cron) and on each run:

1. Detects local changes (new/edited/deleted files) by comparing content
   hashes against `~/.claudesync/manifest.json`, and mirrors them into this
   repo's `data/` directory.
2. Commits and pushes if anything changed. If the push is rejected (another
   machine pushed first), pulls with `--rebase` and retries once — if
   there was nothing local to commit, pulls directly instead.
3. Applies the now-authoritative (and possibly just-merged) repo content
   out to the local `~/.claude/` paths.
4. Updates the manifest with fresh hashes for everything just synced.

Local changes are committed and reconciled with the remote *before* being
applied back out locally — pulling first would risk silently overwriting a
concurrent, not-yet-committed local edit with freshly-pulled remote content.

Per-project `MEMORY.md` files use a custom git merge driver (`memmerge.py`)
that unions entries from both sides instead of producing conflict markers,
since two machines commonly add different entries while offline.

## Setup on a new machine

```sh
git clone https://github.com/varunkumar/claude-sync.git
cd claude-sync
./install.sh
```

This registers the `MEMORY.md` merge driver in the repo's local git config
and installs a cron entry that runs `sync.py` every 15 minutes. It assumes
git push/pull authentication (SSH key or credential helper) is already set
up on the machine.

## Running manually

```sh
python3 sync.py
```

## Running the tests

```sh
pip install pytest
pytest -v
```

## Design

See `docs/superpowers/specs/2026-07-04-claude-sync-design.md` for the full
design rationale, including why plugin syncing is config-only and how
cross-machine project path differences are resolved.
