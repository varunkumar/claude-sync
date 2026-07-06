# claude-sync

Keeps Claude Code memory and configuration consistent across multiple
machines (macOS, Windows/WSL, Amazon Workspace) by syncing a curated slice
of `~/.claude/` through a dedicated git repo that holds only synced data —
separate from this repo, which holds only the tool's source.

## What gets synced

- `~/.claude/CLAUDE.md` (global instructions)
- `~/.claude/skills/`
- `~/.claude/projects/<hash>/memory/` (per-project memory, mapped to a
  stable name via each project's session `cwd`, not the ambiguous encoded
  folder name)
- Only the `enabledPlugins` and `extraKnownMarketplaces` keys of
  `~/.claude/settings.json` — not the plugin cache itself, and not any
  other settings (hooks, effort level, etc. stay machine-local)

All of the above lives at the root of a separate data repo that you provide
(see Setup below) — not in this repo.

## How it works

`sync.py` runs on a schedule (every 15 minutes via cron) and on each run:

1. Detects local changes (new/edited/deleted files) by comparing content
   hashes against `~/.claudesync/manifest.json`, and mirrors them into the
   configured data repo.
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

Create (or reuse) an empty git repo to hold your synced data — this is
separate from this tool's repo, and can be empty or already have commits.
Then:

```sh
git clone https://github.com/varunkumar/claude-sync.git
cd claude-sync
./install.sh <your-data-repo-git-url> [ssh-deploy-key-path]
```

`install.sh`:
- Clones your data repo to `~/.claudesync/repo` (skipped if already
  cloned on this machine).
- Persists that path to `~/.claudesync/repo_root` so `sync.py` can find it
  without the URL being passed again.
- If the data repo is brand new (no commits yet), creates the initial
  `.gitattributes` (registering the `MEMORY.md` merge driver) and pushes
  it, so the first scheduled sync has something to push against.
- Registers the `MEMORY.md` merge driver against the data repo.
- Installs a cron entry that runs `sync.py` every 15 minutes. If you pass
  `ssh-deploy-key-path`, that entry also sets `GIT_SSH_COMMAND` so git uses
  that key directly (see "cron auth" below); if omitted, cron runs with
  whatever auth is already configured for the remote.

It otherwise assumes git push/pull authentication (SSH agent, credential
helper, etc.) is already set up for the data repo's remote **and reachable
from cron**, which is not automatic on every OS — see below.

### Cron auth

`cron` runs outside your login session, so on some setups it can't reach an
`ssh-agent` or a GUI-gated credential store (this bit macOS specifically:
`git-credential-osxkeychain` works fine interactively but fails from cron
with `could not read Username ... Device not configured`, because the login
keychain isn't reachable outside the GUI session). If `git -C
~/.claudesync/repo pull` works in a normal terminal but the same command
fails when run from cron, this is almost always why.

The fix that doesn't depend on any session/keychain state is a dedicated SSH
deploy key, read straight off disk:

1. Generate a key with no passphrase, dedicated to this one repo:
   ```sh
   ssh-keygen -t ed25519 -f ~/.ssh/claude-sync-deploy -N "" -C "claude-sync cron $(hostname -s)"
   ```
2. Add `~/.ssh/claude-sync-deploy.pub` as a **deploy key with write access**
   on your data repo (GitHub: repo Settings -> Deploy keys -> Add deploy
   key, uncheck "read-only"; GitLab: repo Settings -> Repository -> Deploy
   keys, grant "Write access"). Deploy keys are scoped to that one repo
   only — unlike a personal SSH key or token, this key cannot reach any
   other repo on your account.
3. Make sure the data repo's remote uses SSH (`git@...`), then pass the key
   path to `install.sh`:
   ```sh
   ./install.sh <your-data-repo-git-url> ~/.ssh/claude-sync-deploy
   ```

If your machine already has working cron-compatible git auth (a custom
credential helper you've confirmed runs under cron, an HTTPS remote backed
by a `credential.helper=store` file, etc.), skip this — just omit the
second argument and `install.sh` won't touch your auth setup at all.

## Running manually

```sh
python3 sync.py
```

## Upgrading

The current version lives in the `VERSION` file at the repo root. To
upgrade an already-installed machine:

```sh
cd <wherever you cloned claude-sync>
git pull
./install.sh <your-data-repo-git-url>
```

`install.sh` is safe to re-run at any point: cloning the data repo,
bootstrapping `.gitattributes`, and configuring the merge driver are all
skipped if already done, and the cron entry is replaced (not duplicated)
each time — so re-running it after a `git pull` is enough to pick up
changes to the sync schedule or to the script paths cron invokes. It
records the version it installed to `~/.claudesync/installed_version`.

The cron job always runs `sync.py` out of the path you cloned to
(`CODE_REPO_ROOT` at install time), so a `git pull` alone already updates
the code the next scheduled run will use — re-running `install.sh` is only
needed when the upgrade also changes the cron schedule or install-time
configuration.

## Logs

Every cron-triggered run's stdout/stderr is appended to
`$CLAUDESYNC_STATE_DIR/sync.log` (`~/.claudesync/sync.log` by default —
the same directory as `manifest.json` and `repo_root`). Each line is
timestamped (`YYYY-MM-DD HH:MM:SS LEVEL message`), and every run logs its
`claude-sync <version>` at both start and finish, so you can tell which
version produced a given log line and how long a run took by diffing the
start/finish timestamps:

```sh
tail -f ~/.claudesync/sync.log
```

## FAQ / Troubleshooting

**"No data repo configured" / `RuntimeError` mentioning `CLAUDESYNC_REPO_ROOT`**
`~/.claudesync/repo_root` doesn't exist or points at a path that's gone
(e.g. you moved or deleted `~/.claudesync/repo`). Re-run
`./install.sh <your-data-repo-git-url>` — it's idempotent and will
re-clone/re-link as needed.

**Nothing seems to be syncing**
1. Check the cron entry exists: `crontab -l | grep claude-sync`. If it's
   missing, re-run `install.sh`.
2. Check `~/.claudesync/sync.log` for the most recent run and whether it
   logged `sync failed` with a traceback (see Logs above).
3. Confirm git auth works non-interactively for the data repo: `git -C
   ~/.claudesync/repo pull` should not prompt for a password.

**Push/pull errors, or a run failed mid-rebase**
`sync.py` retries a rejected push once via `pull --rebase`, and aborts the
rebase automatically if that still conflicts (this only happens for files
outside the `MEMORY.md` merge driver's coverage, e.g. two machines editing
the global `CLAUDE.md` at the same time). The next scheduled run starts
clean. If you want to resolve it immediately: `cd ~/.claudesync/repo && git
status` to see the conflict, resolve by hand, commit, and push.

**A machine's changes never show up on other machines**
Cron may not be running at all on that machine (common on machines that
sleep/hibernate a lot, or where cron isn't enabled — e.g. some minimal WSL
setups). Confirm with `crontab -l` and check `sync.log` has recent
timestamps close to now.

**`could not read Username ... Device not configured` in `sync.log`, but git
works fine when I run it myself**
Cron can't reach your login session's `ssh-agent` or GUI-gated credential
store (see "Cron auth" in Setup above). Set up a dedicated SSH deploy key
and re-run `install.sh <your-data-repo-git-url> ~/.ssh/claude-sync-deploy`.

**Two machines keep syncing at nearly the same minute and one keeps losing
the push race**
`install.sh` picks a random per-machine minute offset within each 15-minute
block specifically to avoid this; a genuine collision should self-resolve
via the retry-with-rebase logic. If it doesn't, see the rebase item above.

**How do I check which version is installed?**
`cat ~/.claudesync/installed_version`, or check the most recent
`claude-sync <version>: sync starting` line in `sync.log`.

**How do I report a bug?**
Open an issue at https://github.com/varunkumar/claude-sync/issues. Include
the version from `installed_version`, your OS, and the relevant lines from
`sync.log` (the log is local-only and never synced, so it's safe to share).

## Running the tests

```sh
pip install pytest
pytest -v
```

## Design

See `docs/superpowers/specs/2026-07-04-claude-sync-design.md` for the full
design rationale, including why plugin syncing is config-only and how
cross-machine project path differences are resolved.

See `docs/superpowers/specs/2026-07-06-external-data-repo-design.md` for
why the data repo is separate from this one and how its location is
configured.
