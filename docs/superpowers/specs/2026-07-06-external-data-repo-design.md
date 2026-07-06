# External data repo design

## Purpose

Today, `claude-sync` (this repo) serves double duty: it holds the tool's
source *and* the synced data (`data/`), committed and pushed to the same
GitHub repo. This couples the tool to one specific data store and makes it
impossible to point different machines' setups at a different data
destination without forking or modifying the tool itself.

This change decouples the two: `claude-sync` becomes source-only (`sync.py`,
`install.sh`, tests, docs). The synced content — global `CLAUDE.md`,
`skills/`, `plugins.json`, per-project `memory/` — moves to a separate git
repo, whose location is provided once at install time and persisted in
per-machine config.

Only a single data repo is supported. There is no near-term plan to split
data further (e.g. memory vs. everything else into separate repos); the
config is not designed to anticipate that.

## Config resolution (`paths.py`)

`repo_root()` no longer falls back to the script's own directory. Resolution
order:

1. `CLAUDESYNC_REPO_ROOT` env var (unchanged — highest precedence, used by
   tests and advanced overrides)
2. A persisted config file at `state_dir()/repo_root` — a plain text file
   containing one line, the absolute path to the cloned data repo. Written by
   `install.sh` during setup.
3. Neither present → raise `RuntimeError` with a message pointing at
   `install.sh <git-url>`.

`data_dir()` becomes `repo_root()` directly (no more `/ "data"` suffix) — the
data repo's root *is* the data directory now, since the repo is dedicated
entirely to synced content.

## `sync.py` fallout

`git_commit_and_push` currently runs `git add -A data`, hardcoding the old
subdirectory name independently of the `data` path threaded through
`sync_once`. Since data now lives at the repo root, this becomes
`git add -A .`.

No other changes: `sync_once`, `manifest.py`, `mirror.py`, `memmerge.py`
already take `data`/`repo_root` as separate parameters and don't assume
where `data` sits relative to `repo_root`.

## `install.sh` changes

`install.sh` now takes the data repo's git URL as its argument:

```sh
./install.sh git@github.com:varunkumar/claude-memory.git
```

Steps:

1. **Clone (idempotent)**: if `~/.claudesync/repo` doesn't already exist,
   `git clone <url> ~/.claudesync/repo`. If it already exists, skip cloning
   (assume it's already set up correctly).
2. **Persist config**: write the absolute path of `~/.claudesync/repo` to
   `~/.claudesync/repo_root`, so `paths.repo_root()` can find it without the
   URL being passed again.
3. **Bootstrap an empty repo**: if the clone has no commits yet (a brand new
   remote), create `.gitattributes` (containing
   `projects/*/memory/MEMORY.md merge=memmerge`) at the repo root as the
   initial commit, and push with `git push -u origin <current-branch>`. This
   step exists because a bare `git push` fails on a branch with no upstream
   tracking — without it, the very first cron run's push would fail
   silently every 15 minutes until someone noticed.
4. **Register the merge driver against the data repo** (not the code repo):
   `git -C ~/.claudesync/repo config merge.memmerge.driver "python3
   <code-repo-path>/memmerge.py %O %A %B %P"`.
5. **Cron entry**: simplifies to `cd <code-repo> && python3 sync.py`, since
   `sync.py` now resolves the data repo location itself from
   `~/.claudesync/repo_root` — no env var needs threading through cron.

Re-running `install.sh` (e.g. on a machine already set up) is a no-op for
steps 1 and 3, and idempotently re-applies steps 2 and 4.

## Conflict handling

Unchanged from the existing design (`2026-07-04-claude-sync-design.md`):
`memmerge.py` unions `MEMORY.md` entries; other same-file conflicts during
`git pull --rebase` surface as normal git conflict markers, caught by
`git_commit_and_push`, which aborts the rebase (preserving the local commit)
and re-raises so the cycle fails loudly in `sync.log` rather than silently
resolving or overwriting. Only the location of `.gitattributes` moves (data
repo root, instead of `data/.gitattributes` in the code repo).

## Migration

Out of scope. No existing machine has anything committed under this repo's
`data/` directory today, so there's nothing to migrate.

## Testing

- `tests/test_paths.py`: update `data_dir()` to assert it equals
  `repo_root()` (no `/data` suffix). Add cases for: config-file resolution
  (no env var, file present), and the "neither env var nor config file
  present → raises" case.
- `tests/test_install_script.py`: rework for the clone+bootstrap flow —
  point the script at a local bare repo standing in for GitHub, verify (a)
  `~/.claudesync/repo_root` is written with the clone path, (b) the merge
  driver is registered against the *clone*, not the code repo copy running
  the script, (c) the initial empty-repo bootstrap commit/push happens and
  a second `install.sh` run against an already-cloned repo doesn't
  re-clone or re-bootstrap.
- `tests/test_sync_integration.py`: no changes expected — it already passes
  `repo_root` and `data` as explicit params to `sync_once`, decoupled from
  `paths.py`'s resolution logic.
