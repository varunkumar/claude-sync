# External Data Repo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple the synced data (global `CLAUDE.md`, `skills/`, `plugins.json`, per-project `memory/`) from this tool's source repo, so it lives in a separate, configurable git repo instead of this repo's `data/` subdirectory.

**Architecture:** `paths.repo_root()` resolves the data repo location from `CLAUDESYNC_REPO_ROOT` (env override, unchanged) or a persisted `~/.claudesync/repo_root` config file written by `install.sh`, raising if neither is set. `data_dir()` becomes `repo_root()` directly (flattened — no `/data` suffix) since the external repo is dedicated entirely to synced content. `install.sh` takes a git URL, clones it to `~/.claudesync/repo`, bootstraps `.gitattributes` + an initial commit/push if the clone is empty (so the very first `git push` has an upstream to push to), and registers the merge driver against that clone instead of the code repo.

**Tech Stack:** Python 3 (stdlib only), POSIX shell, git, pytest.

## Global Constraints

- No fallback to the code repo's own directory for `repo_root()` — a data repo must be explicitly configured, per the design doc.
- Only a single data repo is supported; do not add any multi-repo/split config surface.
- No migration tooling — no existing machine has anything under this repo's `data/` today (per design doc).
- Every `CLAUDESYNC_*` env var override documented in `CLAUDE.md`'s module map must stay accurate after these changes.
- Design reference: `docs/superpowers/specs/2026-07-06-external-data-repo-design.md`.

---

### Task 1: `paths.py` — configurable, error-if-unset `repo_root()` and flattened `data_dir()`

**Files:**
- Modify: `paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces: `paths.repo_root() -> Path` (raises `RuntimeError` if unconfigured), `paths.data_dir() -> Path` (now equals `repo_root()`), `paths.repo_root_config_path() -> Path` (new — `state_dir() / "repo_root"`, read by `paths.py` and written by `install.sh`, referenced in Task 3).

- [ ] **Step 1: Write the failing tests**

Replace the existing `test_repo_root_respects_env_override` / `test_data_dir_is_repo_root_slash_data` pair in `tests/test_paths.py` and add new cases. Full replacement block for those two tests plus new ones (insert in place of the old two, same file):

```python
def test_repo_root_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDESYNC_REPO_ROOT", str(tmp_path))
    import paths
    importlib.reload(paths)
    assert paths.repo_root() == tmp_path


def test_repo_root_reads_persisted_config_file_when_no_env_override(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDESYNC_REPO_ROOT", raising=False)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("CLAUDESYNC_STATE_DIR", str(state_dir))
    data_repo = tmp_path / "data_repo"
    (state_dir / "repo_root").write_text(str(data_repo) + "\n")
    import paths
    importlib.reload(paths)
    assert paths.repo_root() == data_repo


def test_repo_root_raises_when_nothing_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDESYNC_REPO_ROOT", raising=False)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("CLAUDESYNC_STATE_DIR", str(state_dir))
    import paths
    importlib.reload(paths)
    with pytest.raises(RuntimeError):
        paths.repo_root()


def test_data_dir_equals_repo_root(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDESYNC_REPO_ROOT", str(tmp_path))
    import paths
    importlib.reload(paths)
    assert paths.data_dir() == tmp_path
```

This requires adding `import pytest` at the top of `tests/test_paths.py` alongside the existing `import importlib`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_paths.py -v`
Expected: `test_repo_root_reads_persisted_config_file_when_no_env_override`, `test_repo_root_raises_when_nothing_configured`, and `test_data_dir_equals_repo_root` FAIL (old `repo_root()`/`data_dir()` behavior doesn't match); other tests still pass.

- [ ] **Step 3: Rewrite `paths.py`**

```python
import os
from pathlib import Path


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDESYNC_CLAUDE_HOME", str(Path.home() / ".claude")))


def state_dir() -> Path:
    return Path(os.environ.get("CLAUDESYNC_STATE_DIR", str(Path.home() / ".claudesync")))


def repo_root_config_path() -> Path:
    return state_dir() / "repo_root"


def repo_root() -> Path:
    env_override = os.environ.get("CLAUDESYNC_REPO_ROOT")
    if env_override:
        return Path(env_override)
    config_path = repo_root_config_path()
    if config_path.is_file():
        return Path(config_path.read_text().strip())
    raise RuntimeError(
        f"No data repo configured (checked CLAUDESYNC_REPO_ROOT and {config_path}). "
        "Run install.sh <data-repo-git-url> to set one up."
    )


def data_dir() -> Path:
    return repo_root()


def manifest_path() -> Path:
    return state_dir() / "manifest.json"


def settings_path() -> Path:
    return claude_home() / "settings.json"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_paths.py -v`
Expected: all PASS

- [ ] **Step 5: Update `CLAUDE.md`'s module map entry for `paths.py`**

In `/Users/varunkumar/projects/claude-sync/CLAUDE.md`, replace the `paths.py` bullet:

```markdown
- `paths.py` — every filesystem location the tool touches. `claude_home()`
  / `state_dir()` are overridable via `CLAUDESYNC_CLAUDE_HOME` /
  `CLAUDESYNC_STATE_DIR` env vars. `repo_root()` (and `data_dir()`, which is
  now just an alias for it) resolves to `CLAUDESYNC_REPO_ROOT` if set,
  otherwise the path persisted in `~/.claudesync/repo_root` by
  `install.sh`, otherwise raises — there is no fallback to this repo's own
  directory. Tests always set `CLAUDESYNC_*` env vars to temp dirs — never
  point tests at a real `~/.claude`.
```

- [ ] **Step 6: Run the full test suite**

Run: `pytest -v`
Expected: all PASS (other test files don't exercise `paths.repo_root()`/`data_dir()` directly — `sync.py` tests pass explicit `repo_root`/`data` params).

- [ ] **Step 7: Commit**

```bash
git add paths.py tests/test_paths.py CLAUDE.md
git commit -m "feat: require explicit data repo config in paths.repo_root()"
```

---

### Task 2: `sync.py` — fix hardcoded `git add -A data` for the flattened layout

**Files:**
- Modify: `sync.py:101`
- Test: `tests/test_sync_integration.py` (no changes expected — verify only)

**Interfaces:**
- Consumes: none new.
- Produces: no signature changes — `git_commit_and_push(repo_root, message)` keeps the same signature.

- [ ] **Step 1: Confirm the current integration tests pass before touching code**

Run: `pytest tests/test_sync_integration.py -v`
Expected: all PASS (baseline)

- [ ] **Step 2: Make the change**

In `sync.py`, `git_commit_and_push`:

```python
def git_commit_and_push(repo_root: Path, message: str) -> bool:
    run_git(["add", "-A", "."], cwd=repo_root)
```

(Only the `run_git` call's argument list changes, from `["add", "-A", "data"]` to `["add", "-A", "."]`. The rest of the function is unchanged.)

- [ ] **Step 3: Run the integration tests again**

Run: `pytest tests/test_sync_integration.py -v`
Expected: all PASS — these tests pass `data=repo_root / "data"` explicitly (a subdirectory of the test's `repo_root`, which itself only contains that `data/` dir plus `.git`), so `git add -A .` from `repo_root` stages the same files `git add -A data` did.

- [ ] **Step 4: Run the full test suite**

Run: `pytest -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add sync.py
git commit -m "fix: stage the whole data repo root, not a hardcoded data/ subdir"
```

---

### Task 3: `install.sh` — clone, bootstrap, and configure against an external data repo

**Files:**
- Modify: `install.sh`
- Test: `tests/test_install_script.py`

**Interfaces:**
- Consumes: `paths.repo_root_config_path()`'s location convention (`~/.claudesync/repo_root`) — `install.sh` writes to the literal path `$STATE_DIR/repo_root` where `STATE_DIR` defaults to `$HOME/.claudesync` (matching `paths.state_dir()`'s default) or `$CLAUDESYNC_STATE_DIR` if set.
- Produces: on success, `$STATE_DIR/repo_root` contains the absolute path to the cloned data repo; that clone has `merge.memmerge.driver` configured and a `.gitattributes` with the `memmerge` line; a cron entry invokes `sync.py` from the code repo directory.

- [ ] **Step 1: Write the failing tests**

Replace `test_install_script_configures_merge_driver` in `tests/test_install_script.py` with the following (keep `test_install_script_is_valid_posix_shell` as-is):

```python
def _crontab_stub(fake_bin):
    crontab_stub = fake_bin / "crontab"
    crontab_stub.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  -l) exit 1 ;;\n"
        "  -) cat > /dev/null; exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    crontab_stub.chmod(0o755)


def _run_install(install_copy, code_repo, remote, fake_home, fake_bin):
    env = {
        "HOME": str(fake_home),
        "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    return subprocess.run(
        ["sh", str(install_copy), str(remote)],
        cwd=code_repo, check=True, env=env, capture_output=True, text=True,
    )


def _setup_install(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)

    code_repo = tmp_path / "code_repo"
    code_repo.mkdir()
    install_copy = code_repo / "install.sh"
    install_copy.write_text(INSTALL_SH.read_text())
    install_copy.chmod(0o755)
    (code_repo / "memmerge.py").write_text("# stub\n")

    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    fake_bin = tmp_path / "fake_bin"
    fake_bin.mkdir()
    _crontab_stub(fake_bin)

    return install_copy, code_repo, remote, fake_home, fake_bin


def test_install_script_clones_bootstraps_and_configures_merge_driver(tmp_path):
    install_copy, code_repo, remote, fake_home, fake_bin = _setup_install(tmp_path)

    _run_install(install_copy, code_repo, remote, fake_home, fake_bin)

    data_repo_dir = fake_home / ".claudesync" / "repo"
    assert data_repo_dir.is_dir()

    repo_root_config = fake_home / ".claudesync" / "repo_root"
    assert repo_root_config.read_text().strip() == str(data_repo_dir)

    result = subprocess.run(
        ["git", "config", "merge.memmerge.driver"], cwd=data_repo_dir, capture_output=True, text=True,
    )
    assert "memmerge.py" in result.stdout

    assert (data_repo_dir / ".gitattributes").read_text() == "projects/*/memory/MEMORY.md merge=memmerge\n"

    local_log = subprocess.run(
        ["git", "log", "--oneline"], cwd=data_repo_dir, capture_output=True, text=True,
    ).stdout
    assert local_log.strip() != ""

    remote_log = subprocess.run(
        ["git", "log", "--oneline", "main"], cwd=remote, capture_output=True, text=True,
    ).stdout
    assert remote_log.strip() != "", "initial bootstrap commit must be pushed so a plain `git push` in sync.py later succeeds"


def test_install_script_is_idempotent_on_second_run(tmp_path):
    install_copy, code_repo, remote, fake_home, fake_bin = _setup_install(tmp_path)

    _run_install(install_copy, code_repo, remote, fake_home, fake_bin)
    data_repo_dir = fake_home / ".claudesync" / "repo"
    first_log = subprocess.run(
        ["git", "log", "--oneline"], cwd=data_repo_dir, capture_output=True, text=True,
    ).stdout

    _run_install(install_copy, code_repo, remote, fake_home, fake_bin)
    second_log = subprocess.run(
        ["git", "log", "--oneline"], cwd=data_repo_dir, capture_output=True, text=True,
    ).stdout

    assert first_log == second_log, "second run must not re-clone or add a duplicate bootstrap commit"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_install_script.py -v`
Expected: FAIL — `install.sh` doesn't yet accept a URL argument or clone anywhere (old script ignores `$1` and treats its own directory as the repo).

- [ ] **Step 3: Rewrite `install.sh`**

```sh
#!/usr/bin/env sh
set -eu

if [ $# -lt 1 ]; then
  echo "usage: $0 <data-repo-git-url>" >&2
  exit 1
fi

DATA_REPO_URL="$1"
CODE_REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${CLAUDESYNC_STATE_DIR:-$HOME/.claudesync}"
DATA_REPO_DIR="$STATE_DIR/repo"

mkdir -p "$STATE_DIR"

if [ ! -d "$DATA_REPO_DIR" ]; then
  git clone "$DATA_REPO_URL" "$DATA_REPO_DIR"
fi

echo "$DATA_REPO_DIR" > "$STATE_DIR/repo_root"

if ! git -C "$DATA_REPO_DIR" log -1 >/dev/null 2>&1; then
  printf '%s\n' "projects/*/memory/MEMORY.md merge=memmerge" > "$DATA_REPO_DIR/.gitattributes"
  git -C "$DATA_REPO_DIR" add .gitattributes
  git -C "$DATA_REPO_DIR" commit -m "claude-sync: bootstrap data repo"
  CURRENT_BRANCH="$(git -C "$DATA_REPO_DIR" branch --show-current)"
  git -C "$DATA_REPO_DIR" push -u origin "$CURRENT_BRANCH"
fi

git -C "$DATA_REPO_DIR" config merge.memmerge.driver "python3 $CODE_REPO_ROOT/memmerge.py %O %A %B %P"

CRON_CMD="*/15 * * * * cd $CODE_REPO_ROOT && /usr/bin/env python3 $CODE_REPO_ROOT/sync.py >> $STATE_DIR/sync.log 2>&1"
CRON_MARKER="# claude-sync"

EXISTING_CRON="$(crontab -l 2>/dev/null || true)"
if ! printf '%s\n' "$EXISTING_CRON" | grep -qF "$CRON_MARKER"; then
  { printf '%s\n' "$EXISTING_CRON"; echo "$CRON_CMD $CRON_MARKER"; } | crontab -
  echo "Installed cron entry."
else
  echo "Cron entry already present; skipping."
fi

echo "claude-sync installed. Data repo: $DATA_REPO_DIR. Merge driver configured; cron runs every 15 minutes."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_install_script.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add install.sh tests/test_install_script.py
git commit -m "feat: install.sh clones and bootstraps an external data repo"
```

---

### Task 4: Update `README.md` for the new setup flow

**Files:**
- Modify: `README.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Update "What gets synced" and "Setup on a new machine" sections**

Replace the `README.md` content from the start through the "Setup on a new machine" section with:

```markdown
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
./install.sh <your-data-repo-git-url>
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
- Installs a cron entry that runs `sync.py` every 15 minutes.

It assumes git push/pull authentication (SSH key or credential helper) is
already set up for the data repo's remote.
```

- [ ] **Step 2: Update the "Design" section's pointer if needed**

At the bottom of `README.md`, after the existing line pointing to
`2026-07-04-claude-sync-design.md`, add:

```markdown

See `docs/superpowers/specs/2026-07-06-external-data-repo-design.md` for
why the data repo is separate from this one and how its location is
configured.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the external data repo setup flow"
```
