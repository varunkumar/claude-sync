import json
import subprocess
from pathlib import Path

import basename


def _write_jsonl(path: Path, records):
    with path.open("w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


def _run_git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(path: Path, remote_url: str = None):
    path.mkdir(parents=True, exist_ok=True)
    _run_git(["init"], cwd=path)
    _run_git(["config", "user.email", "test@test.com"], cwd=path)
    _run_git(["config", "user.name", "Test"], cwd=path)
    (path / "README.md").write_text("hi")
    _run_git(["add", "README.md"], cwd=path)
    _run_git(["commit", "-m", "init"], cwd=path)
    if remote_url:
        _run_git(["remote", "add", "origin", remote_url], cwd=path)
    return path


def test_resolve_finds_cwd_in_first_matching_line(tmp_path):
    project_dir = tmp_path / "-Users-varunkumar-projects-claude-sync"
    project_dir.mkdir()
    fake_cwd = tmp_path / "nonexistent" / "claude-sync"
    _write_jsonl(
        project_dir / "session.jsonl",
        [
            {"type": "summary"},
            {"type": "user", "cwd": str(fake_cwd)},
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


def test_normalize_remote_url_maps_https_and_ssh_to_same_key():
    https = basename.normalize_remote_url("https://github.com/varunkumar/claude-sync.git")
    scp = basename.normalize_remote_url("git@github.com:varunkumar/claude-sync.git")
    ssh = basename.normalize_remote_url("ssh://git@github.com/varunkumar/claude-sync.git")
    assert https == scp == ssh == "github.com/varunkumar/claude-sync"


def test_normalize_remote_url_strips_no_dot_git_suffix():
    assert basename.normalize_remote_url("https://github.com/varunkumar/claude-sync") == "github.com/varunkumar/claude-sync"


def test_normalize_remote_url_lowercases_host_only():
    assert basename.normalize_remote_url("https://GitHub.com/Varunkumar/Claude-Sync.git") == "github.com/Varunkumar/Claude-Sync"


def test_resolve_prefers_git_remote_over_cwd_basename(tmp_path):
    repo_dir = tmp_path / "repos" / "my-checkout"
    _init_repo(repo_dir, remote_url="git@github.com:varunkumar/claude-sync.git")

    project_dir = tmp_path / "encoded-project"
    project_dir.mkdir()
    _write_jsonl(project_dir / "session.jsonl", [{"cwd": str(repo_dir)}])

    assert basename.resolve_project_basename(project_dir) == "github.com/varunkumar/claude-sync"


def test_resolve_falls_back_to_cwd_basename_when_no_remote(tmp_path):
    repo_dir = tmp_path / "repos" / "no-remote-repo"
    _init_repo(repo_dir)

    project_dir = tmp_path / "encoded-project"
    project_dir.mkdir()
    _write_jsonl(project_dir / "session.jsonl", [{"cwd": str(repo_dir)}])

    assert basename.resolve_project_basename(project_dir) == "no-remote-repo"


def test_resolve_falls_back_to_cwd_basename_when_cwd_deleted(tmp_path):
    project_dir = tmp_path / "encoded-project"
    project_dir.mkdir()
    _write_jsonl(
        project_dir / "session.jsonl",
        [{"cwd": str(tmp_path / "repos" / "deleted-repo")}],
    )

    assert basename.resolve_project_basename(project_dir) == "deleted-repo"


def test_resolve_returns_same_key_for_worktree_as_main_checkout(tmp_path):
    main_repo = tmp_path / "repos" / "claude-sync"
    _init_repo(main_repo, remote_url="git@github.com:varunkumar/claude-sync.git")

    worktree_dir = tmp_path / "repos" / "claude-sync-feature-x"
    _run_git(["worktree", "add", "-b", "feature-x", str(worktree_dir)], cwd=main_repo)

    project_dir_main = tmp_path / "encoded-main"
    project_dir_main.mkdir()
    _write_jsonl(project_dir_main / "session.jsonl", [{"cwd": str(main_repo)}])

    project_dir_worktree = tmp_path / "encoded-worktree"
    project_dir_worktree.mkdir()
    _write_jsonl(project_dir_worktree / "session.jsonl", [{"cwd": str(worktree_dir)}])

    main_key = basename.resolve_project_basename(project_dir_main)
    worktree_key = basename.resolve_project_basename(project_dir_worktree)

    assert main_key == worktree_key == "github.com/varunkumar/claude-sync"
