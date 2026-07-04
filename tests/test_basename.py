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
