# claude-sync design

## Purpose

Keep Claude Code memory and configuration consistent across three machines
(macOS, Windows/WSL, Amazon Workspace) by syncing a curated slice of
`~/.claude/` through a private GitHub repo
(`github.com/varunkumar/claude-sync` — this repo). Inspired by
https://blog.lhotka.net/2026/05/08/Claude-Memory-Sync, adapted to a
cron-driven, dependency-light Python tool instead of an always-on Go daemon.

## Scope

Synced:
- Per-project memory dirs: `~/.claude/projects/<hash>/memory/*.md`
- Global instructions: `~/.claude/CLAUDE.md`
- Skills: `~/.claude/skills/`
- Plugin selection only: the `enabledPlugins` and `extraKnownMarketplaces`
  keys from `~/.claude/settings.json` (not the `~/.claude/plugins/` cache,
  which is large and OS/binary-specific — each machine installs plugins
  itself once the config says which ones are enabled)

Explicitly out of scope: session transcripts (`.jsonl`), history, caches,
`hooks`/`effortLevel`/`tui` and other machine-specific `settings.json` keys.

## Repo layout

This repo (`claude-sync`) serves as both the tool's source and the data
store:

```
claude-sync/
  sync.py            # main entrypoint: pull, detect, mirror, commit, push
  memmerge.py         # git merge driver for MEMORY.md files
  install.sh          # sets up cron entry, .gitattributes, git merge config
  data/
    global/CLAUDE.md
    skills/...
    projects/<basename>/memory/...
    plugins.json      # {"enabledPlugins": {...}, "extraKnownMarketplaces": {...}}
  .gitattributes       # projects/*/memory/MEMORY.md merge=memmerge
```

Local, per-machine, gitignored state lives outside the repo at
`~/.claudesync/manifest.json`.

## Project basename mapping

Claude Code encodes each project's absolute path into its memory folder
name by replacing `/` with `-` (e.g. `/Users/varunkumar/projects/claude-sync`
→ `-Users-varunkumar-projects-claude-sync`). This encoding is ambiguous to
reverse when the project's own basename contains a dash (`claude-sync` could
be misread as `claude`/`sync`).

To resolve this reliably, `sync.py` reads the real absolute path from the
`cwd` field present in that project's session `.jsonl` files (verified to
exist in this environment) and takes `os.path.basename(cwd)` as the
canonical project key. Memory content is stored in the repo under
`data/projects/<basename>/memory/`, so the same logical project maps to the
same repo path regardless of which machine or full filesystem path it lives
under (`/Users/...` on Mac, `/home/...` on WSL, etc.).

If a project's `.jsonl` files are all missing the `cwd` field (edge case,
e.g. an empty project with no sessions yet), that project is skipped for
this sync run and logged — never guessed from the dashed folder name.

If two different full paths resolve to the same basename (rare name
collision, e.g. two unrelated `foo` projects on different machines), their
memory is merged into one `data/projects/foo/memory/` — acceptable given
this is a single-user, low-project-count setup; not handled specially.

## Sync mechanism

A single Python script, `sync.py`, run periodically via cron (`*/15 * * * *`
on Mac/WSL/Linux workspace) with pull-then-push semantics:

1. **Pull**: `git pull --rebase` on the repo.
2. **Apply remote → local**: for each synced path, copy repo `data/`
   contents out to the corresponding `~/.claude/` location, except
   `plugins.json`, which is merged key-by-key into local
   `~/.claude/settings.json` (only `enabledPlugins` /
   `extraKnownMarketplaces` are overwritten; all other keys, e.g. `hooks`,
   are left untouched).
2. **Detect local → repo changes**: for each synced path, compute a
   content hash and compare against `~/.claudesync/manifest.json` (the hash
   recorded as of the last successful sync). A mismatch means the local file
   changed since last sync; mirror it into `data/`. A path present in the
   manifest but missing locally means a local deletion; remove it from
   `data/` too.
3. **Commit & push**: if anything in `data/` changed, `git add -A`,
   commit with a timestamped message, and `git push`. Conflicts during
   push (remote moved) trigger a re-pull-rebase-retry, once.
4. **Update manifest**: record fresh hashes for everything just synced.

The manifest exists specifically so genuine local deletions can be
distinguished from files simply not yet pulled from another machine (same
problem the reference blog post's manifest solves).

## Conflict resolution

Git's default line-based merge handles most cases fine, since content here
is mostly whole-file adds/replaces (new skill files, new project dirs) that
don't textually overlap.

The one structurally risky file is each project's `MEMORY.md`: since it's
an append-mostly index of one-line entries, two machines adding different
entries while offline would otherwise produce conflict markers on a
standard merge. To avoid that, a custom git merge driver
(`memmerge.py`, registered via `.gitattributes` for
`projects/*/memory/MEMORY.md`) parses both sides as line entries and unions
them, deduplicating identical lines. Non-`MEMORY.md` merge conflicts (rare)
are left as normal git conflict markers for manual resolution.

## Setup

`install.sh`:
1. Registers the merge driver in the repo's local git config
   (`git config merge.memmerge.driver ...`) and ensures `.gitattributes` is
   present.
2. Adds a cron entry invoking `python3 sync.py` every 15 minutes.
3. Assumes git push/pull authentication (SSH key or credential helper) is
   already configured on the machine — not handled by this tool.

Run once per machine. Safe to re-run (idempotent).

## Error handling

- Git auth/network failures: log and exit non-zero; cron will simply retry
  next interval. No alerting beyond that.
- Partial failure mid-sync (e.g. push fails after local files were already
  mirrored into `data/`): manifest is only updated after a successful push,
  so a retry re-detects and re-attempts the same changes; safe to re-run.

## Testing

- Unit tests for `memmerge.py`: union of disjoint entries, dedup of
  identical entries, stable ordering.
- Unit tests for basename resolution: dash-ambiguous paths resolved via
  `cwd`, missing-`cwd` project skipped and logged.
- Unit tests for the plugins.json ↔ settings.json partial merge (other keys
  preserved).
- An integration test using two temp "local" `~/.claude`-like dirs and a
  local bare git repo standing in for GitHub, exercising a full two-machine
  round trip including a MEMORY.md union-merge case.
