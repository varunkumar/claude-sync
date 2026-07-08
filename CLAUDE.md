# claude-sync

A Python tool that syncs Claude Code memory, global instructions, skills,
and enabled-plugin selection across machines through this git repo. Run via
cron (`install.sh` wires this up), not a background daemon.

## Module map

- `paths.py` — every filesystem location the tool touches. `claude_home()`
  / `state_dir()` are overridable via `CLAUDESYNC_CLAUDE_HOME` /
  `CLAUDESYNC_STATE_DIR` env vars. `repo_root()` (and `data_dir()`, which is
  now just an alias for it) resolves to `CLAUDESYNC_REPO_ROOT` if set,
  otherwise the path persisted in `~/.claudesync/repo_root` by
  `install.sh`, otherwise raises — there is no fallback to this repo's own
  directory. Tests always set `CLAUDESYNC_*` env vars to temp dirs — never
  point tests at a real `~/.claude`.
- `basename.py` — resolves a project's stable name from the `cwd` field in
  its session `.jsonl` files. Never derive a project name by splitting the
  dashed `~/.claude/projects/<encoded-path>` folder name; it's ambiguous
  whenever the real basename itself contains a dash. The key is the
  normalized `origin` remote URL (`git remote get-url origin`, e.g. both
  ssh and https forms of the same repo collapse to `github.com/org/repo`)
  when one can be resolved — this is what makes a git worktree map to the
  same project as its main checkout, since worktrees share the main
  repo's remotes. Falls back to the raw `cwd` basename when there's no
  remote, or the directory has since been deleted or moved.
- `manifest.py` — content hashing, directory snapshotting, and diffing
  against the last-synced state recorded in `~/.claudesync/manifest.json`.
- `mirror.py` — plain file copy/remove helpers, plus the one special case:
  extracting/merging only `enabledPlugins` / `extraKnownMarketplaces` out
  of `settings.json` (never the whole file).
- `memmerge.py` — the git merge driver for `MEMORY.md`, registered via
  `.gitattributes` at the root of the (separate) data repo. Does a two-way
  union of lines from both sides, not a true three-way merge — deletions
  aren't tracked, since memory entries are treated as append-mostly. Its
  `union_merge` is also called directly by `sync.py` (not just invoked as a
  git driver) to reconcile multiple local worktrees' `MEMORY.md` in the same
  sync cycle, before any of it is ever committed.
- `sync.py` — orchestrates one full sync cycle: collect local changes up
  into the data repo, commit and push (falling back to a plain pull if
  there was nothing local to send; a rejected push retries via
  `pull --rebase` then push once), then apply the now-authoritative repo
  content back down to `~/.claude/`. Local changes are committed before
  being applied down deliberately — pulling first was found to risk
  silently overwriting a concurrent, not-yet-committed local edit with
  freshly-pulled content. Before applying anything down, `is_mass_deletion`
  compares the repo's current content against the last-synced manifest: if
  more than half of everything previously synced is now missing from the
  repo, `sync_once` refuses to apply and returns without touching local or
  saving the manifest, logging a warning instead. This guards against the
  repo having been edited outside claude-sync (e.g. a manual `rm`+commit) —
  without it, the tool can't distinguish that from a legitimate deletion and
  will mirror the loss down to every machine's `~/.claude`, which is exactly
  what happened once before this guard existed. A project's main checkout
  and its worktrees resolve to the same key (see `basename.py` above) and so
  share one `repo_memory` folder, but each has its own local memory dir —
  `group_targets_by_repo_memory` groups them, and `collect_local_changes_multi`
  unions their snapshots before diffing against the manifest, so a worktree
  that simply hasn't caught up on some file yet doesn't read as having
  deleted it (only absence from *every* local root does). A same-cycle
  conflict between two roots for `MEMORY.md` is union-merged via
  `memmerge.union_merge` — the same function backing the git-level merge
  driver below, since every worktree gets its own `MEMORY.md` immediately
  and diverging before ever syncing is the realistic case; anything else
  (e.g. a feedback file coincidentally written in two worktrees) resolves to
  whichever copy was modified most recently, since a real prose merge isn't
  expected to make sense there. `apply_remote_changes` mirrors down to each local root
  independently and always fills in a file a given root is missing, even if
  the repo side didn't change since the last cycle — that unchanged-digest
  shortcut used to assume the one local root it knew about already had the
  file, which broke the moment a second root (a fresh worktree) entered the
  picture.

This repo (`claude-sync`) holds only the tool's source. The synced data
(global `CLAUDE.md`, `skills/`, `plugins.json`, per-project `memory/`)
lives in a separate git repo whose location is provided once via
`install.sh <data-repo-git-url>` and persisted to `~/.claudesync/repo_root`
— see `paths.py` above.

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
- External data repo design: `docs/superpowers/specs/2026-07-06-external-data-repo-design.md`
- External data repo plan: `docs/superpowers/plans/2026-07-06-external-data-repo.md`
