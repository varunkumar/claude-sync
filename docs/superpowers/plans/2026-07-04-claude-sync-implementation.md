# claude-sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python tool that syncs Claude Code memory, global instructions, skills, and enabled-plugin config across machines via the `claude-sync` git repo, run periodically via cron.

**Architecture:** Small stdlib-only Python modules (`paths.py`, `basename.py`, `manifest.py`, `mirror.py`, `memmerge.py`, `sync.py`) at the repo root, orchestrated by `sync.py`. State that must persist across runs (per-file content hashes) lives in a local, non-synced manifest at `~/.claudesync/manifest.json`. A `data/` directory inside this repo is the git-tracked mirror of the curated `~/.claude/` content. `install.sh` wires up the git merge driver and a cron entry.

**Tech Stack:** Python 3 standard library only (`hashlib`, `json`, `pathlib`, `subprocess`, `os`, `sys`). `pytest` for tests (dev-only dependency). Plain POSIX shell for `install.sh`. No third-party runtime dependencies, so nothing needs installing on any of the three machines beyond Python 3 and git.

## Global Constraints

- No third-party Python packages at runtime — stdlib only (spec: dependency-light, cron-driven tool).
- Synced content is exactly: `~/.claude/CLAUDE.md`, `~/.claude/skills/`, per-project `~/.claude/projects/<hash>/memory/`, and only the `enabledPlugins`/`extraKnownMarketplaces` keys of `~/.claude/settings.json`. Nothing else under `~/.claude/` is read or written.
- Project basename resolution must use the `cwd` field from session `.jsonl` files, never derived by splitting the dashed folder name (spec: ambiguous when the basename itself contains a dash, e.g. `claude-sync`).
- `MEMORY.md` files use a custom union merge driver (`memmerge.py`); all other files rely on git's default merge behavior.
- All local, per-machine state (manifest) lives outside this repo at `~/.claudesync/`, never committed.
- Every path the tool touches must be overridable via environment variables (`CLAUDESYNC_CLAUDE_HOME`, `CLAUDESYNC_REPO_ROOT`, `CLAUDESYNC_STATE_DIR`) so tests never touch the real `~/.claude` or `~/.claudesync`.

---

## Task 1: Project scaffolding and `paths.py`

**Files:**
- Create: `paths.py`
- Create: `tests/conftest.py`
- Create: `tests/test_paths.py`
- Create: `pyproject.toml`
- Create: `.gitignore`

**Interfaces:**
- Produces: `paths.claude_home() -> Path`, `paths.repo_root() -> Path`, `paths.data_dir() -> Path`, `paths.state_dir() -> Path`, `paths.manifest_path() -> Path`, `paths.settings_path() -> Path`. All later tasks import these instead of hardcoding paths.

- [ ] **Step 1: Create test scaffolding**

`tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

`pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 2: Write the failing test**

`tests/test_paths.py`:
```python
import importlib


def test_claude_home_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDESYNC_CLAUDE_HOME", str(tmp_path))
    import paths
    importlib.reload(paths)
    assert paths.claude_home() == tmp_path


def test_claude_home_defaults_to_dot_claude(monkeypatch):
    monkeypatch.delenv("CLAUDESYNC_CLAUDE_HOME", raising=False)
    import paths
    importlib.reload(paths)
    assert paths.claude_home() == Path.home() / ".claude"


def test_repo_root_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDESYNC_REPO_ROOT", str(tmp_path))
    import paths
    importlib.reload(paths)
    assert paths.repo_root() == tmp_path


def test_data_dir_is_repo_root_slash_data(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDESYNC_REPO_ROOT", str(tmp_path))
    import paths
    importlib.reload(paths)
    assert paths.data_dir() == tmp_path / "data"


def test_state_dir_respects_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDESYNC_STATE_DIR", str(tmp_path))
    import paths
    importlib.reload(paths)
    assert paths.state_dir() == tmp_path
    assert paths.manifest_path() == tmp_path / "manifest.json"


def test_settings_path_is_claude_home_slash_settings_json(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDESYNC_CLAUDE_HOME", str(tmp_path))
    import paths
    importlib.reload(paths)
    assert paths.settings_path() == tmp_path / "settings.json"


from pathlib import Path  # noqa: E402  (kept near usage above for clarity in this file)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'paths'`

- [ ] **Step 4: Write `paths.py`**

```python
import os
from pathlib import Path


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDESYNC_CLAUDE_HOME", str(Path.home() / ".claude")))


def repo_root() -> Path:
    default = Path(__file__).resolve().parent
    return Path(os.environ.get("CLAUDESYNC_REPO_ROOT", str(default)))


def data_dir() -> Path:
    return repo_root() / "data"


def state_dir() -> Path:
    return Path(os.environ.get("CLAUDESYNC_STATE_DIR", str(Path.home() / ".claudesync")))


def manifest_path() -> Path:
    return state_dir() / "manifest.json"


def settings_path() -> Path:
    return claude_home() / "settings.json"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_paths.py -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add paths.py tests/conftest.py tests/test_paths.py pyproject.toml .gitignore
git commit -m "feat: add paths module with env-overridable locations"
```

---

## Task 2: `basename.py` — resolve project identity via session `cwd`

**Files:**
- Create: `basename.py`
- Create: `tests/test_basename.py`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: `basename.resolve_project_basename(project_dir: Path) -> str | None`, `basename.iter_project_dirs(claude_home: Path) -> Iterator[Path]`. Used by `sync.py` (Task 6) to map each local project dir to its repo-side name.

- [ ] **Step 1: Write the failing tests**

`tests/test_basename.py`:
```python
import json
from pathlib import Path

import basename


def _write_jsonl(path: Path, records):
    with path.open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def test_resolve_finds_cwd_in_first_matching_line(tmp_path):
    project_dir = tmp_path / "-Users-varunkumar-projects-claude-sync"
    project_dir.mkdir()
    _write_jsonl(
        project_dir / "session.jsonl",
        [
            {"type": "summary"},
            {"type": "user", "cwd": "/Users/varunkumar/projects/claude-sync"},
        ],
    )

    assert basename.resolve_project_basename(project_dir) == "claude-sync"


def test_resolve_handles_dash_in_basename_correctly(tmp_path):
    project_dir = tmp_path / "-home-varunkumar-projects-claude-sync"
    project_dir.mkdir()
    _write_jsonl(
        project_dir / "session.jsonl",
        [{"cwd": "/home/varunkumar/projects/claude-sync"}],
    )

    assert basename.resolve_project_basename(project_dir) == "claude-sync"


def test_resolve_skips_malformed_json_lines(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    with (project_dir / "session.jsonl").open("w") as f:
        f.write("not valid json\n")
        f.write(json.dumps({"cwd": "/Users/varunkumar/projects/foo"}) + "\n")

    assert basename.resolve_project_basename(project_dir) == "foo"


def test_resolve_returns_none_when_no_cwd_anywhere(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _write_jsonl(project_dir / "session.jsonl", [{"type": "summary"}])

    assert basename.resolve_project_basename(project_dir) is None


def test_iter_project_dirs_yields_only_directories(tmp_path):
    claude_home = tmp_path / ".claude"
    projects = claude_home / "projects"
    projects.mkdir(parents=True)
    (projects / "proj-a").mkdir()
    (projects / "proj-b").mkdir()
    (projects / "stray-file.txt").write_text("not a project")

    result = sorted(p.name for p in basename.iter_project_dirs(claude_home))
    assert result == ["proj-a", "proj-b"]


def test_iter_project_dirs_empty_when_projects_root_missing(tmp_path):
    claude_home = tmp_path / ".claude"
    assert list(basename.iter_project_dirs(claude_home)) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_basename.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'basename'`

- [ ] **Step 3: Write `basename.py`**

```python
import json
from pathlib import Path
from typing import Iterator, Optional


def resolve_project_basename(project_dir: Path) -> Optional[str]:
    for jsonl_path in sorted(project_dir.glob("*.jsonl")):
        try:
            with jsonl_path.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cwd = record.get("cwd")
                    if cwd:
                        return Path(cwd).name
        except OSError:
            continue
    return None


def iter_project_dirs(claude_home: Path) -> Iterator[Path]:
    projects_root = claude_home / "projects"
    if not projects_root.is_dir():
        return
    for entry in sorted(projects_root.iterdir()):
        if entry.is_dir():
            yield entry
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_basename.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add basename.py tests/test_basename.py
git commit -m "feat: resolve project basename from session cwd"
```

---

## Task 3: `manifest.py` — hashing, tree snapshots, diffing

**Files:**
- Create: `manifest.py`
- Create: `tests/test_manifest.py`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: `manifest.hash_bytes(data: bytes) -> str`, `manifest.hash_file(path: Path) -> str`, `manifest.snapshot_tree(root: Path) -> dict[str, str]`, `manifest.load_manifest(path: Path) -> dict`, `manifest.save_manifest(path: Path, manifest: dict) -> None`, `manifest.diff_against_manifest(current: dict, manifest: dict) -> tuple[set[str], set[str]]`. Used by `sync.py` (Task 6/7).

- [ ] **Step 1: Write the failing tests**

`tests/test_manifest.py`:
```python
import json

import manifest


def test_hash_bytes_is_deterministic():
    assert manifest.hash_bytes(b"hello") == manifest.hash_bytes(b"hello")
    assert manifest.hash_bytes(b"hello") != manifest.hash_bytes(b"world")


def test_hash_file_matches_hash_bytes(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"content")
    assert manifest.hash_file(f) == manifest.hash_bytes(b"content")


def test_snapshot_tree_returns_relative_posix_paths(tmp_path):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "a.md").write_text("a")
    (root / "sub" / "b.md").write_text("b")

    snap = manifest.snapshot_tree(root)

    assert snap["a.md"] == manifest.hash_bytes(b"a")
    assert snap["sub/b.md"] == manifest.hash_bytes(b"b")
    assert set(snap.keys()) == {"a.md", "sub/b.md"}


def test_snapshot_tree_empty_when_root_missing(tmp_path):
    assert manifest.snapshot_tree(tmp_path / "missing") == {}


def test_load_manifest_returns_empty_dict_when_missing(tmp_path):
    assert manifest.load_manifest(tmp_path / "manifest.json") == {}


def test_save_then_load_manifest_roundtrips(tmp_path):
    path = tmp_path / "state" / "manifest.json"
    data = {"a.md": "hash1", "sub/b.md": "hash2"}

    manifest.save_manifest(path, data)

    assert path.is_file()
    assert json.loads(path.read_text()) == data
    assert manifest.load_manifest(path) == data


def test_diff_against_manifest_flags_new_changed_and_deleted():
    old = {"unchanged.md": "h1", "changed.md": "h2", "deleted.md": "h3"}
    current = {"unchanged.md": "h1", "changed.md": "h2-new", "added.md": "h4"}

    changed, deleted = manifest.diff_against_manifest(current, old)

    assert changed == {"changed.md", "added.md"}
    assert deleted == {"deleted.md"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'manifest'`

- [ ] **Step 3: Write `manifest.py`**

```python
import hashlib
import json
from pathlib import Path


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    return hash_bytes(path.read_bytes())


def snapshot_tree(root: Path) -> dict:
    if not root.is_dir():
        return {}
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            snapshot[rel] = hash_file(path)
    return snapshot


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text())


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def diff_against_manifest(current: dict, manifest: dict):
    changed = {rel for rel, digest in current.items() if manifest.get(rel) != digest}
    deleted = set(manifest.keys()) - set(current.keys())
    return changed, deleted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_manifest.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add manifest.py tests/test_manifest.py
git commit -m "feat: add manifest hashing, snapshotting, and diffing"
```

---

## Task 4: `mirror.py` — file copy helpers and plugin config extraction/merge

**Files:**
- Create: `mirror.py`
- Create: `tests/test_mirror.py`

**Interfaces:**
- Consumes: nothing from prior tasks directly (standalone helpers).
- Produces: `mirror.copy_file(src, dst) -> None`, `mirror.remove_file(path) -> None`, `mirror.PLUGIN_KEYS`, `mirror.extract_plugin_settings(settings: dict) -> dict`, `mirror.sync_plugins_to_repo(settings_path, plugins_json_path) -> None`, `mirror.apply_plugins_from_repo(settings_path, plugins_json_path) -> None`. Used by `sync.py` (Task 6/7).

- [ ] **Step 1: Write the failing tests**

`tests/test_mirror.py`:
```python
import json

import mirror


def test_copy_file_creates_parent_dirs_and_copies_bytes(tmp_path):
    src = tmp_path / "src.md"
    src.write_bytes(b"content")
    dst = tmp_path / "nested" / "dst.md"

    mirror.copy_file(src, dst)

    assert dst.read_bytes() == b"content"


def test_remove_file_deletes_existing_file(tmp_path):
    f = tmp_path / "f.md"
    f.write_text("x")

    mirror.remove_file(f)

    assert not f.exists()


def test_remove_file_is_noop_when_missing(tmp_path):
    mirror.remove_file(tmp_path / "missing.md")  # must not raise


def test_extract_plugin_settings_pulls_only_plugin_keys():
    settings = {
        "hooks": {"SessionStart": []},
        "enabledPlugins": {"superpowers": True},
        "extraKnownMarketplaces": {"googlechrome": {"source": "x"}},
        "effortLevel": "medium",
    }

    extracted = mirror.extract_plugin_settings(settings)

    assert extracted == {
        "enabledPlugins": {"superpowers": True},
        "extraKnownMarketplaces": {"googlechrome": {"source": "x"}},
    }


def test_extract_plugin_settings_defaults_missing_keys_to_empty_dict():
    assert mirror.extract_plugin_settings({}) == {
        "enabledPlugins": {},
        "extraKnownMarketplaces": {},
    }


def test_sync_plugins_to_repo_writes_only_plugin_keys(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "hooks": {"SessionStart": []},
        "enabledPlugins": {"superpowers": True},
    }))
    plugins_json_path = tmp_path / "data" / "plugins.json"

    mirror.sync_plugins_to_repo(settings_path, plugins_json_path)

    written = json.loads(plugins_json_path.read_text())
    assert written == {"enabledPlugins": {"superpowers": True}, "extraKnownMarketplaces": {}}


def test_sync_plugins_to_repo_noop_when_settings_missing(tmp_path):
    plugins_json_path = tmp_path / "data" / "plugins.json"
    mirror.sync_plugins_to_repo(tmp_path / "missing_settings.json", plugins_json_path)
    assert not plugins_json_path.exists()


def test_apply_plugins_from_repo_merges_preserving_other_keys(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "hooks": {"SessionStart": ["python3 hook.py"]},
        "enabledPlugins": {"old-plugin": True},
    }))
    plugins_json_path = tmp_path / "plugins.json"
    plugins_json_path.write_text(json.dumps({
        "enabledPlugins": {"superpowers": True, "github": True},
        "extraKnownMarketplaces": {},
    }))

    mirror.apply_plugins_from_repo(settings_path, plugins_json_path)

    result = json.loads(settings_path.read_text())
    assert result["hooks"] == {"SessionStart": ["python3 hook.py"]}
    assert result["enabledPlugins"] == {"superpowers": True, "github": True}


def test_apply_plugins_from_repo_creates_settings_when_missing(tmp_path):
    settings_path = tmp_path / "settings.json"
    plugins_json_path = tmp_path / "plugins.json"
    plugins_json_path.write_text(json.dumps({
        "enabledPlugins": {"superpowers": True},
        "extraKnownMarketplaces": {},
    }))

    mirror.apply_plugins_from_repo(settings_path, plugins_json_path)

    result = json.loads(settings_path.read_text())
    assert result == {"enabledPlugins": {"superpowers": True}, "extraKnownMarketplaces": {}}


def test_apply_plugins_from_repo_noop_when_plugins_json_missing(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"hooks": {}}))
    mirror.apply_plugins_from_repo(settings_path, tmp_path / "missing.json")
    assert json.loads(settings_path.read_text()) == {"hooks": {}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mirror.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mirror'`

- [ ] **Step 3: Write `mirror.py`**

```python
import json
from pathlib import Path

PLUGIN_KEYS = ("enabledPlugins", "extraKnownMarketplaces")


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def remove_file(path: Path) -> None:
    if path.is_file():
        path.unlink()


def extract_plugin_settings(settings: dict) -> dict:
    return {key: settings.get(key, {}) for key in PLUGIN_KEYS}


def sync_plugins_to_repo(settings_path: Path, plugins_json_path: Path) -> None:
    if not settings_path.is_file():
        return
    settings = json.loads(settings_path.read_text())
    plugins_json_path.parent.mkdir(parents=True, exist_ok=True)
    plugins_json_path.write_text(
        json.dumps(extract_plugin_settings(settings), indent=2, sort_keys=True) + "\n"
    )


def apply_plugins_from_repo(settings_path: Path, plugins_json_path: Path) -> None:
    if not plugins_json_path.is_file():
        return
    incoming = json.loads(plugins_json_path.read_text())
    settings = json.loads(settings_path.read_text()) if settings_path.is_file() else {}
    for key in PLUGIN_KEYS:
        if key in incoming:
            settings[key] = incoming[key]
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_mirror.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add mirror.py tests/test_mirror.py
git commit -m "feat: add file mirroring and plugin config merge helpers"
```

---

## Task 5: `memmerge.py` — union merge driver for `MEMORY.md`

**Files:**
- Create: `memmerge.py`
- Create: `tests/test_memmerge.py`

**Interfaces:**
- Consumes: nothing from prior tasks.
- Produces: `memmerge.union_merge(local_text: str, remote_text: str) -> str`, `memmerge.main(argv: list[str]) -> int` (CLI entrypoint invoked by git as the `merge.memmerge.driver` command with `%O %A %B %P`). Registered against `MEMORY.md` in Task 8's `.gitattributes`.

- [ ] **Step 1: Write the failing tests**

`tests/test_memmerge.py`:
```python
import memmerge


def test_union_merge_combines_disjoint_entries():
    local = "- entry X\n"
    remote = "- entry Y\n"

    result = memmerge.union_merge(local, remote)

    assert "- entry X" in result
    assert "- entry Y" in result


def test_union_merge_dedups_identical_lines():
    local = "# Memory Index\n- entry X\n"
    remote = "# Memory Index\n- entry X\n- entry Y\n"

    result = memmerge.union_merge(local, remote)

    assert result.count("- entry X") == 1
    assert result.count("# Memory Index") == 1
    assert "- entry Y" in result


def test_union_merge_preserves_local_order_then_appends_remote_only_lines():
    local = "- A\n- B\n"
    remote = "- B\n- C\n"

    result = memmerge.union_merge(local, remote)

    lines = [line for line in result.splitlines() if line]
    assert lines == ["- A", "- B", "- C"]


def test_main_writes_merged_content_into_local_file(tmp_path):
    base = tmp_path / "base.md"
    local = tmp_path / "local.md"
    remote = tmp_path / "remote.md"
    base.write_text("- A\n")
    local.write_text("- A\n- B\n")
    remote.write_text("- A\n- C\n")

    exit_code = memmerge.main(
        ["memmerge.py", str(base), str(local), str(remote), "MEMORY.md"]
    )

    assert exit_code == 0
    merged = local.read_text()
    assert "- B" in merged
    assert "- C" in merged


def test_main_returns_error_code_with_wrong_arg_count():
    assert memmerge.main(["memmerge.py", "only-one-arg"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_memmerge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'memmerge'`

- [ ] **Step 3: Write `memmerge.py`**

```python
import sys
from pathlib import Path


def union_merge(local_text: str, remote_text: str) -> str:
    result = []
    seen = set()
    for line in local_text.splitlines():
        if line not in seen:
            result.append(line)
            seen.add(line)
    for line in remote_text.splitlines():
        if line not in seen:
            result.append(line)
            seen.add(line)
    return ("\n".join(result) + "\n") if result else ""


def main(argv) -> int:
    if len(argv) != 5:
        print("usage: memmerge.py <base> <local> <remote> <path>", file=sys.stderr)
        return 2
    _base_path, local_path, remote_path, _original_path = argv[1], argv[2], argv[3], argv[4]
    local_text = Path(local_path).read_text()
    remote_text = Path(remote_path).read_text()
    merged = union_merge(local_text, remote_text)
    Path(local_path).write_text(merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_memmerge.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add memmerge.py tests/test_memmerge.py
git commit -m "feat: add union merge driver for MEMORY.md"
```

---

## Task 6: `sync.py` core sync functions (remote-apply / local-collect)

**Files:**
- Create: `sync.py`
- Create: `tests/test_sync_core.py`

**Interfaces:**
- Consumes: `manifest.snapshot_tree`, `manifest.hash_file`, `manifest.diff_against_manifest` (Task 3); `mirror.copy_file`, `mirror.remove_file` (Task 4); `basename.iter_project_dirs`, `basename.resolve_project_basename` (Task 2).
- Produces: `sync.apply_remote_changes(local_root, repo_dir, old_manifest, prefix) -> None`, `sync.collect_local_changes(local_root, repo_dir, old_manifest, prefix) -> dict[str, str]`, `sync.apply_remote_file(local_path, repo_path, old_manifest, key) -> None`, `sync.collect_local_file_change(local_path, repo_path, old_manifest, key, current) -> None`, `sync.local_project_targets(home, data) -> list[tuple[Path, Path]]`. Used by `sync.sync_once` in Task 7.

- [ ] **Step 1: Write the failing tests**

`tests/test_sync_core.py`:
```python
import manifest
import mirror
import sync


def test_apply_remote_changes_copies_new_repo_files_to_local(tmp_path):
    local_root = tmp_path / "local"
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "MEMORY.md").write_text("- entry\n")

    sync.apply_remote_changes(local_root, repo_dir, old_manifest={}, prefix="memory")

    assert (local_root / "MEMORY.md").read_text() == "- entry\n"


def test_apply_remote_changes_skips_files_already_known(tmp_path):
    local_root = tmp_path / "local"
    repo_dir = tmp_path / "repo"
    local_root.mkdir(parents=True)
    repo_dir.mkdir(parents=True)
    (repo_dir / "MEMORY.md").write_text("- entry\n")
    (local_root / "MEMORY.md").write_text("- local-edit\n")
    digest = manifest.hash_file(repo_dir / "MEMORY.md")

    sync.apply_remote_changes(
        local_root, repo_dir, old_manifest={"memory/MEMORY.md": digest}, prefix="memory"
    )

    # local file unchanged: manifest already reflected this repo content
    assert (local_root / "MEMORY.md").read_text() == "- local-edit\n"


def test_apply_remote_changes_removes_files_deleted_upstream(tmp_path):
    local_root = tmp_path / "local"
    repo_dir = tmp_path / "repo"
    local_root.mkdir(parents=True)
    repo_dir.mkdir(parents=True)
    (local_root / "gone.md").write_text("stale")

    sync.apply_remote_changes(
        local_root, repo_dir, old_manifest={"memory/gone.md": "somehash"}, prefix="memory"
    )

    assert not (local_root / "gone.md").exists()


def test_collect_local_changes_mirrors_new_and_edited_files(tmp_path):
    local_root = tmp_path / "local"
    repo_dir = tmp_path / "repo"
    local_root.mkdir(parents=True)
    (local_root / "MEMORY.md").write_text("- new entry\n")

    snapshot = sync.collect_local_changes(local_root, repo_dir, old_manifest={}, prefix="memory")

    assert (repo_dir / "MEMORY.md").read_text() == "- new entry\n"
    assert snapshot == {"memory/MEMORY.md": manifest.hash_file(local_root / "MEMORY.md")}


def test_collect_local_changes_removes_locally_deleted_files_from_repo(tmp_path):
    local_root = tmp_path / "local"
    repo_dir = tmp_path / "repo"
    local_root.mkdir(parents=True)
    repo_dir.mkdir(parents=True)
    (repo_dir / "gone.md").write_text("stale")

    snapshot = sync.collect_local_changes(
        local_root, repo_dir, old_manifest={"memory/gone.md": "oldhash"}, prefix="memory"
    )

    assert not (repo_dir / "gone.md").exists()
    assert snapshot == {}


def test_apply_remote_file_copies_when_repo_has_new_content(tmp_path):
    local_path = tmp_path / "CLAUDE.md"
    repo_path = tmp_path / "data" / "CLAUDE.md"
    repo_path.parent.mkdir(parents=True)
    repo_path.write_text("global instructions")

    sync.apply_remote_file(local_path, repo_path, old_manifest={}, key="global/CLAUDE.md")

    assert local_path.read_text() == "global instructions"


def test_collect_local_file_change_copies_local_to_repo_and_updates_current(tmp_path):
    local_path = tmp_path / "CLAUDE.md"
    repo_path = tmp_path / "data" / "CLAUDE.md"
    local_path.write_text("updated instructions")
    current = {}

    sync.collect_local_file_change(local_path, repo_path, old_manifest={}, key="global/CLAUDE.md", current=current)

    assert repo_path.read_text() == "updated instructions"
    assert current == {"global/CLAUDE.md": manifest.hash_file(local_path)}


def test_local_project_targets_maps_basename_to_repo_memory_dir(tmp_path):
    home = tmp_path / ".claude"
    data = tmp_path / "data"
    project_dir = home / "projects" / "-Users-varunkumar-projects-claude-sync"
    (project_dir / "memory").mkdir(parents=True)
    with (project_dir / "session.jsonl").open("w") as f:
        f.write('{"cwd": "/Users/varunkumar/projects/claude-sync"}\n')

    targets = sync.local_project_targets(home, data)

    assert targets == [(project_dir / "memory", data / "projects" / "claude-sync" / "memory")]


def test_local_project_targets_skips_projects_with_no_resolvable_cwd(tmp_path):
    home = tmp_path / ".claude"
    data = tmp_path / "data"
    project_dir = home / "projects" / "empty-project"
    (project_dir / "memory").mkdir(parents=True)
    (project_dir / "session.jsonl").write_text('{"type": "summary"}\n')

    assert sync.local_project_targets(home, data) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sync_core.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'sync'`

- [ ] **Step 3: Write the core functions in `sync.py`**

```python
import sys
from pathlib import Path

import basename
import manifest
import mirror


def apply_remote_changes(local_root: Path, repo_dir: Path, old_manifest: dict, prefix: str) -> None:
    repo_snapshot = manifest.snapshot_tree(repo_dir)
    prefixed_old = {k: v for k, v in old_manifest.items() if k.startswith(prefix + "/")}

    for rel, digest in repo_snapshot.items():
        key = f"{prefix}/{rel}"
        if prefixed_old.get(key) != digest:
            local_path = local_root / rel
            if not local_path.is_file() or manifest.hash_file(local_path) != digest:
                mirror.copy_file(repo_dir / rel, local_path)

    repo_keys = {f"{prefix}/{rel}" for rel in repo_snapshot}
    for key in prefixed_old:
        if key not in repo_keys:
            rel = key[len(prefix) + 1:]
            mirror.remove_file(local_root / rel)


def collect_local_changes(local_root: Path, repo_dir: Path, old_manifest: dict, prefix: str) -> dict:
    local_snapshot = {
        f"{prefix}/{rel}": digest for rel, digest in manifest.snapshot_tree(local_root).items()
    }
    prefixed_old = {k: v for k, v in old_manifest.items() if k.startswith(prefix + "/")}
    changed, deleted = manifest.diff_against_manifest(local_snapshot, prefixed_old)

    for key in changed:
        rel = key[len(prefix) + 1:]
        mirror.copy_file(local_root / rel, repo_dir / rel)
    for key in deleted:
        rel = key[len(prefix) + 1:]
        mirror.remove_file(repo_dir / rel)

    return local_snapshot


def apply_remote_file(local_path: Path, repo_path: Path, old_manifest: dict, key: str) -> None:
    if not repo_path.is_file():
        if key in old_manifest and local_path.is_file():
            mirror.remove_file(local_path)
        return
    digest = manifest.hash_file(repo_path)
    if old_manifest.get(key) != digest:
        if not local_path.is_file() or manifest.hash_file(local_path) != digest:
            mirror.copy_file(repo_path, local_path)


def collect_local_file_change(local_path: Path, repo_path: Path, old_manifest: dict, key: str, current: dict) -> None:
    if local_path.is_file():
        digest = manifest.hash_file(local_path)
        if old_manifest.get(key) != digest:
            mirror.copy_file(local_path, repo_path)
        current[key] = digest
    elif key in old_manifest:
        mirror.remove_file(repo_path)


def local_project_targets(home: Path, data: Path):
    targets = []
    for project_dir in basename.iter_project_dirs(home):
        name = basename.resolve_project_basename(project_dir)
        if name is None:
            print(f"skip: no cwd found for {project_dir}", file=sys.stderr)
            continue
        local_memory = project_dir / "memory"
        repo_memory = data / "projects" / name / "memory"
        targets.append((local_memory, repo_memory))
    return targets
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sync_core.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add sync.py tests/test_sync_core.py
git commit -m "feat: add core remote-apply and local-collect sync functions"
```

---

## Task 7: `sync.py` orchestration (`sync_once`, git plumbing, `main`) + integration test

**Files:**
- Modify: `sync.py` (append orchestration functions)
- Create: `tests/test_sync_integration.py`

**Interfaces:**
- Consumes: everything from Task 6, plus `paths.py` (Task 1), `mirror.sync_plugins_to_repo` / `mirror.apply_plugins_from_repo` (Task 4), `manifest.load_manifest` / `manifest.save_manifest` (Task 3).
- Produces: `sync.git_pull(repo_root) -> None`, `sync.git_commit_and_push(repo_root, message) -> bool`, `sync.sync_once(home, repo_root, data, state_manifest_path) -> None`, `sync.main() -> int`.

- [ ] **Step 1: Write the failing integration test**

`tests/test_sync_integration.py`:
```python
import json
import subprocess
from pathlib import Path

import sync


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo_with_remote(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(["init", "--bare"], cwd=remote)

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], cwd=repo)
    _git(["config", "user.email", "test@example.com"], cwd=repo)
    _git(["config", "user.name", "Test"], cwd=repo)
    (repo / "data").mkdir()
    (repo / "data" / ".gitkeep").write_text("")
    _git(["add", "-A"], cwd=repo)
    _git(["commit", "-m", "init"], cwd=repo)
    _git(["remote", "add", "origin", str(remote)], cwd=repo)
    _git(["push", "-u", "origin", "main"], cwd=repo, )
    return repo, remote


def test_sync_once_pushes_local_memory_entry_to_remote(tmp_path):
    repo, remote = _init_repo_with_remote(tmp_path)

    home = tmp_path / "home" / ".claude"
    project_dir = home / "projects" / "-Users-alice-projects-demo"
    (project_dir / "memory").mkdir(parents=True)
    (project_dir / "memory" / "MEMORY.md").write_text("- first entry\n")
    (project_dir / "session.jsonl").write_text(
        json.dumps({"cwd": "/Users/alice/projects/demo"}) + "\n"
    )
    home.mkdir(parents=True, exist_ok=True)
    (home / "CLAUDE.md").write_text("global instructions v1")

    state_manifest_path = tmp_path / "state" / "manifest.json"

    sync.sync_once(
        home=home,
        repo_root=repo,
        data=repo / "data",
        state_manifest_path=state_manifest_path,
    )

    assert (repo / "data" / "projects" / "demo" / "memory" / "MEMORY.md").read_text() == "- first entry\n"
    assert (repo / "data" / "global" / "CLAUDE.md").read_text() == "global instructions v1"

    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert "claude-sync" in log


def test_sync_once_pulls_another_machines_changes_down(tmp_path):
    repo_a, remote = _init_repo_with_remote(tmp_path)

    # Machine A pushes an entry.
    home_a = tmp_path / "home_a" / ".claude"
    project_a = home_a / "projects" / "-Users-alice-projects-demo"
    (project_a / "memory").mkdir(parents=True)
    (project_a / "memory" / "MEMORY.md").write_text("- from machine A\n")
    (project_a / "session.jsonl").write_text(
        json.dumps({"cwd": "/Users/alice/projects/demo"}) + "\n"
    )
    sync.sync_once(
        home=home_a,
        repo_root=repo_a,
        data=repo_a / "data",
        state_manifest_path=tmp_path / "state_a" / "manifest.json",
    )

    # Machine B clones fresh and runs sync_once with no local changes; should pull A's entry down.
    repo_b = tmp_path / "repo_b"
    _git(["clone", str(remote), str(repo_b)], cwd=tmp_path)
    _git(["config", "user.email", "test@example.com"], cwd=repo_b)
    _git(["config", "user.name", "Test"], cwd=repo_b)

    home_b = tmp_path / "home_b" / ".claude"
    home_b.mkdir(parents=True)

    sync.sync_once(
        home=home_b,
        repo_root=repo_b,
        data=repo_b / "data",
        state_manifest_path=tmp_path / "state_b" / "manifest.json",
    )

    pulled = home_b / "projects" / "-Users-bob-does-not-matter"
    # Machine B has no matching local project dir yet (never opened it there),
    # so the repo-side content is the source of truth to verify instead.
    assert (repo_b / "data" / "projects" / "demo" / "memory" / "MEMORY.md").read_text() == "- from machine A\n"


def test_sync_once_unions_concurrent_memory_edits_via_merge_driver(tmp_path):
    repo_a, remote = _init_repo_with_remote(tmp_path)

    # Register the merge driver in machine A's repo config.
    memmerge_path = Path(__file__).resolve().parent.parent / "memmerge.py"
    _git(["config", "merge.memmerge.driver", f"python3 {memmerge_path} %O %A %B %P"], cwd=repo_a)
    (repo_a / ".gitattributes").write_text("projects/*/memory/MEMORY.md merge=memmerge\n")
    _git(["add", ".gitattributes"], cwd=repo_a)
    _git(["commit", "-m", "add gitattributes"], cwd=repo_a)
    _git(["push"], cwd=repo_a)

    home_a = tmp_path / "home_a" / ".claude"
    project_a = home_a / "projects" / "-Users-alice-projects-demo"
    (project_a / "memory").mkdir(parents=True)
    (project_a / "memory" / "MEMORY.md").write_text("- shared base entry\n")
    (project_a / "session.jsonl").write_text(
        json.dumps({"cwd": "/Users/alice/projects/demo"}) + "\n"
    )
    sync.sync_once(
        home=home_a, repo_root=repo_a, data=repo_a / "data",
        state_manifest_path=tmp_path / "state_a" / "manifest.json",
    )

    repo_b = tmp_path / "repo_b"
    _git(["clone", str(remote), str(repo_b)], cwd=tmp_path)
    _git(["config", "user.email", "test@example.com"], cwd=repo_b)
    _git(["config", "user.name", "Test"], cwd=repo_b)
    _git(["config", "merge.memmerge.driver", f"python3 {memmerge_path} %O %A %B %P"], cwd=repo_b)

    home_b = tmp_path / "home_b" / ".claude"
    project_b = home_b / "projects" / "-home-bob-projects-demo"
    (project_b / "memory").mkdir(parents=True)
    (project_b / "memory" / "MEMORY.md").write_text("- shared base entry\n- from B\n")
    (project_b / "session.jsonl").write_text(
        json.dumps({"cwd": "/home/bob/projects/demo"}) + "\n"
    )
    sync.sync_once(
        home=home_b, repo_root=repo_b, data=repo_b / "data",
        state_manifest_path=tmp_path / "state_b" / "manifest.json",
    )

    # Machine A now adds its own new entry and syncs again; must pull + merge B's entry.
    (project_a / "memory" / "MEMORY.md").write_text("- shared base entry\n- from A\n")
    sync.sync_once(
        home=home_a, repo_root=repo_a, data=repo_a / "data",
        state_manifest_path=tmp_path / "state_a" / "manifest.json",
    )

    merged = (repo_a / "data" / "projects" / "demo" / "memory" / "MEMORY.md").read_text()
    assert "- shared base entry" in merged
    assert "- from A" in merged
    assert "- from B" in merged
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sync_integration.py -v`
Expected: FAIL with `AttributeError: module 'sync' has no attribute 'sync_once'`

- [ ] **Step 3: Append orchestration to `sync.py`**

Add to the bottom of `sync.py` (below the Task 6 functions, keeping existing imports and adding `subprocess` and `paths`):

```python
import subprocess

import paths


def run_git(args, cwd) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def git_pull(repo_root: Path) -> None:
    run_git(["pull", "--rebase"], cwd=repo_root)


def git_push(repo_root: Path) -> None:
    run_git(["push"], cwd=repo_root)


def has_staged_changes(repo_root: Path) -> bool:
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
    return result.returncode != 0


def git_commit_and_push(repo_root: Path, message: str) -> bool:
    run_git(["add", "-A", "data"], cwd=repo_root)
    if not has_staged_changes(repo_root):
        return False
    run_git(["commit", "-m", message], cwd=repo_root)
    try:
        git_push(repo_root)
    except subprocess.CalledProcessError:
        git_pull(repo_root)
        git_push(repo_root)
    return True


def sync_once(home: Path, repo_root: Path, data: Path, state_manifest_path: Path) -> None:
    git_pull(repo_root)

    old_manifest = manifest.load_manifest(state_manifest_path)
    current = {}

    global_local = home / "CLAUDE.md"
    global_repo = data / "global" / "CLAUDE.md"
    apply_remote_file(global_local, global_repo, old_manifest, "global/CLAUDE.md")

    skills_local = home / "skills"
    skills_repo = data / "skills"
    apply_remote_changes(skills_local, skills_repo, old_manifest, "skills")

    project_targets = local_project_targets(home, data)
    for local_memory, repo_memory in project_targets:
        project_name = repo_memory.parent.name
        apply_remote_changes(local_memory, repo_memory, old_manifest, f"projects/{project_name}/memory")

    settings_path = home / "settings.json"
    plugins_json_path = data / "plugins.json"
    mirror.apply_plugins_from_repo(settings_path, plugins_json_path)

    collect_local_file_change(global_local, global_repo, old_manifest, "global/CLAUDE.md", current)
    current.update(
        {f"skills/{rel}": digest for rel, digest in
         collect_local_changes(skills_local, skills_repo, old_manifest, "skills").items()}
    )
    for local_memory, repo_memory in project_targets:
        project_name = repo_memory.parent.name
        prefix = f"projects/{project_name}/memory"
        current.update(collect_local_changes(local_memory, repo_memory, old_manifest, prefix))

    mirror.sync_plugins_to_repo(settings_path, plugins_json_path)
    if plugins_json_path.is_file():
        current["plugins.json"] = manifest.hash_file(plugins_json_path)

    manifest.save_manifest(state_manifest_path, current)

    git_commit_and_push(repo_root, "claude-sync: update")


def main() -> int:
    sync_once(
        home=paths.claude_home(),
        repo_root=paths.repo_root(),
        data=paths.data_dir(),
        state_manifest_path=paths.manifest_path(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sync_integration.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests across all modules, ~40 tests)

- [ ] **Step 6: Commit**

```bash
git add sync.py tests/test_sync_integration.py
git commit -m "feat: add sync_once orchestration with git pull/commit/push"
```

---

## Task 8: `install.sh` and `.gitattributes`

**Files:**
- Create: `install.sh`
- Create: `.gitattributes`
- Create: `tests/test_install_script.py`

**Interfaces:**
- Consumes: `memmerge.py` (Task 5), `sync.py` (Task 7).
- Produces: an idempotent installer any of the three machines can run.

- [ ] **Step 1: Write `.gitattributes`**

```
projects/*/memory/MEMORY.md merge=memmerge
```

(Note: paths in `.gitattributes` are relative to the repo root, and this repo's synced content lives under `data/`, so the actual matched paths are `data/projects/*/memory/MEMORY.md`. Since `.gitattributes` patterns match relative to their own location, place this file inside `data/` instead of the repo root.)

Move the file to `data/.gitattributes`:
```
projects/*/memory/MEMORY.md merge=memmerge
```

- [ ] **Step 2: Write `install.sh`**

```bash
#!/usr/bin/env sh
set -eu

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$REPO_ROOT/data"

git -C "$REPO_ROOT" config merge.memmerge.driver "python3 $REPO_ROOT/memmerge.py %O %A %B %P"

CRON_CMD="*/15 * * * * cd $REPO_ROOT && /usr/bin/env python3 $REPO_ROOT/sync.py >> $HOME/.claudesync/sync.log 2>&1"
CRON_MARKER="# claude-sync"

mkdir -p "$HOME/.claudesync"

EXISTING_CRON="$(crontab -l 2>/dev/null || true)"
if ! printf '%s\n' "$EXISTING_CRON" | grep -qF "$CRON_MARKER"; then
  { printf '%s\n' "$EXISTING_CRON"; echo "$CRON_CMD $CRON_MARKER"; } | crontab -
  echo "Installed cron entry."
else
  echo "Cron entry already present; skipping."
fi

echo "claude-sync installed. Merge driver configured; cron runs every 15 minutes."
```

- [ ] **Step 3: Write the failing test for idempotency**

`tests/test_install_script.py`:
```python
import subprocess
from pathlib import Path

INSTALL_SH = Path(__file__).resolve().parent.parent / "install.sh"


def test_install_script_is_valid_posix_shell():
    result = subprocess.run(["sh", "-n", str(INSTALL_SH)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_install_script_configures_merge_driver(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    install_copy = repo / "install.sh"
    install_copy.write_text(INSTALL_SH.read_text())
    install_copy.chmod(0o755)
    memmerge_stub = repo / "memmerge.py"
    memmerge_stub.write_text("# stub\n")

    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    env = {"HOME": str(fake_home), "PATH": "/usr/bin:/bin"}

    subprocess.run(["sh", str(install_copy)], cwd=repo, check=True, env=env, capture_output=True, text=True)

    result = subprocess.run(
        ["git", "config", "merge.memmerge.driver"], cwd=repo, capture_output=True, text=True
    )
    assert "memmerge.py" in result.stdout
```

- [ ] **Step 4: Make `install.sh` executable and run the tests**

Run: `chmod +x install.sh && pytest tests/test_install_script.py -v`
Expected: PASS (2 tests). If the crontab-dependent portion of `install.sh` fails in a sandboxed test environment lacking a `crontab` binary, that's an environment limitation, not a script bug — the merge-driver assertion (the part under test) does not depend on `crontab` and must still pass.

- [ ] **Step 5: Commit**

```bash
git add install.sh data/.gitattributes tests/test_install_script.py
git commit -m "feat: add install script for merge driver and cron setup"
```

---

## Task 9: `README.md` and repo `CLAUDE.md`

**Files:**
- Create: `README.md`
- Create: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing (documentation only); describes the finished system from Tasks 1–8.

- [ ] **Step 1: Write `README.md`**

```markdown
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

1. `git pull --rebase` to fetch other machines' changes.
2. Applies newly-pulled repo content out to the local `~/.claude/` paths.
3. Detects local changes (new/edited/deleted files) by comparing content
   hashes against `~/.claudesync/manifest.json`, and mirrors them into this
   repo's `data/` directory.
4. Commits and pushes if anything changed, retrying once on a rejected push.

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
```

- [ ] **Step 2: Write `CLAUDE.md`**

```markdown
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
- `sync.py` — orchestrates one full sync cycle: pull, apply remote
  changes down to `~/.claude/`, collect local changes up into `data/`,
  commit, push (retrying once on a rejected push).

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
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: add README and repo CLAUDE.md"
```
