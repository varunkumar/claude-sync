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

    targets = sync.local_project_targets(home, data, {})

    assert targets == [(project_dir / "memory", data / "projects" / "claude-sync" / "memory")]


def test_local_project_targets_skips_projects_with_no_resolvable_cwd(tmp_path):
    home = tmp_path / ".claude"
    data = tmp_path / "data"
    project_dir = home / "projects" / "empty-project"
    (project_dir / "memory").mkdir(parents=True)
    (project_dir / "session.jsonl").write_text('{"type": "summary"}\n')

    assert sync.local_project_targets(home, data, {}) == []


def test_local_project_targets_falls_back_to_cached_name_when_jsonl_is_gone(tmp_path):
    home = tmp_path / ".claude"
    data = tmp_path / "data"
    project_dir = home / "projects" / "-Users-varunkumar-projects-claude-sync"
    (project_dir / "memory").mkdir(parents=True)

    targets = sync.local_project_targets(home, data, {project_dir.name: "claude-sync"})

    assert targets == [(project_dir / "memory", data / "projects" / "claude-sync" / "memory")]
