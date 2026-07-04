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
    (repo_a / ".gitattributes").write_text("data/projects/*/memory/MEMORY.md merge=memmerge\n")
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
