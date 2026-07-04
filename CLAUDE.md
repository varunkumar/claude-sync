# claude-sync

A Python tool that syncs Claude Code memory, global instructions, skills,
and enabled-plugin selection across machines through this git repo. Run via
cron (`install.sh` wires this up), not a background daemon.

## Module map

- `paths.py` — every filesystem location the tool touches, all
  overridable via `CLAUDESYNC_CLAUDE_HOME` / `CLAUDESYNC_REPO_ROOT` /
  `CLAUDESYNC_STATE_DIR` env vars. Tests always set these to temp dirs —
  never point tests at a real `~/.claude`.
- `basename.py` — resolves a project's stable name from the `cwd` field in
  its session `.jsonl` files. Never derive a project name by splitting the
  dashed `~/.claude/projects/<encoded-path>` folder name; it's ambiguous
  whenever the real basename itself contains a dash.
- `manifest.py` — content hashing, directory snapshotting, and diffing
  against the last-synced state recorded in `~/.claudesync/manifest.json`.
- `mirror.py` — plain file copy/remove helpers, plus the one special case:
  extracting/merging only `enabledPlugins` / `extraKnownMarketplaces` out
  of `settings.json` (never the whole file).
- `memmerge.py` — the git merge driver for `MEMORY.md`, registered via
  `data/.gitattributes`. Does a two-way union of lines from both sides,
  not a true three-way merge — deletions aren't tracked, since memory
  entries are treated as append-mostly.
- `sync.py` — orchestrates one full sync cycle: collect local changes up
  into `data/`, commit and push (falling back to a plain pull if there was
  nothing local to send; a rejected push retries via `pull --rebase` then
  push once), then apply the now-authoritative repo content back down to
  `~/.claude/`. Local changes are committed before being applied down
  deliberately — pulling first was found to risk silently overwriting a
  concurrent, not-yet-committed local edit with freshly-pulled content.

## Testing conventions

- Every test sets `CLAUDESYNC_*` env vars (or passes explicit paths
  directly into the functions under test) so nothing touches a real
  `~/.claude` directory.
- `tests/test_sync_integration.py` exercises full two-machine round trips
  against local bare git repos standing in for GitHub — no network access
  needed to run the suite.

## Spec and plan

- Design: `docs/superpowers/specs/2026-07-04-claude-sync-design.md`
- Implementation plan: `docs/superpowers/plans/2026-07-04-claude-sync-implementation.md`
