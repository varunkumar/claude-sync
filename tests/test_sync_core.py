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


def test_collect_local_changes_multi_does_not_delete_file_only_missing_from_one_root(tmp_path):
    # Two worktrees of the same project share one repo memory folder. The
    # main checkout has feedback_x.md (pushed previously); a second worktree
    # never received it locally, but that must not read as "deleted".
    repo_dir = tmp_path / "repo_memory"
    repo_dir.mkdir()
    (repo_dir / "feedback_x.md").write_text("- from main checkout\n")
    (repo_dir / "MEMORY.md").write_text("- shared entry\n")

    old_manifest = {
        "projects/demo/memory/feedback_x.md": manifest.hash_file(repo_dir / "feedback_x.md"),
        "projects/demo/memory/MEMORY.md": manifest.hash_file(repo_dir / "MEMORY.md"),
    }

    root_main = tmp_path / "worktree_main"
    root_main.mkdir()
    (root_main / "feedback_x.md").write_text("- from main checkout\n")
    (root_main / "MEMORY.md").write_text("- shared entry\n")

    root_worktree = tmp_path / "worktree_b"
    root_worktree.mkdir()
    (root_worktree / "MEMORY.md").write_text("- shared entry\n")  # never got feedback_x.md

    sync.collect_local_changes_multi(
        [root_main, root_worktree], repo_dir, old_manifest, prefix="projects/demo/memory"
    )

    assert (repo_dir / "feedback_x.md").exists(), "file present in another worktree must not be deleted"


def test_collect_local_changes_multi_deletes_when_absent_from_every_root(tmp_path):
    repo_dir = tmp_path / "repo_memory"
    repo_dir.mkdir()
    (repo_dir / "gone.md").write_text("stale")

    old_manifest = {"projects/demo/memory/gone.md": "oldhash"}

    root_a = tmp_path / "worktree_a"
    root_a.mkdir()
    root_b = tmp_path / "worktree_b"
    root_b.mkdir()

    sync.collect_local_changes_multi([root_a, root_b], repo_dir, old_manifest, prefix="projects/demo/memory")

    assert not (repo_dir / "gone.md").exists()


def test_collect_local_changes_multi_prefers_most_recently_modified_on_conflict(tmp_path):
    import os
    import time

    # A non-MEMORY.md conflict (e.g. a feedback file coincidentally written
    # in two worktrees) isn't expected to be union-mergeable prose, so it
    # still resolves to whichever copy was modified most recently.
    repo_dir = tmp_path / "repo_memory"
    repo_dir.mkdir()

    root_a = tmp_path / "worktree_a"
    root_a.mkdir()
    (root_a / "feedback_x.md").write_text("- older edit\n")

    root_b = tmp_path / "worktree_b"
    root_b.mkdir()
    (root_b / "feedback_x.md").write_text("- newer edit\n")

    now = time.time()
    os.utime(root_a / "feedback_x.md", (now - 100, now - 100))
    os.utime(root_b / "feedback_x.md", (now, now))

    sync.collect_local_changes_multi([root_a, root_b], repo_dir, old_manifest={}, prefix="projects/demo/memory")

    assert (repo_dir / "feedback_x.md").read_text() == "- newer edit\n"


def test_collect_local_changes_multi_union_merges_conflicting_memory_md(tmp_path):
    # MEMORY.md is the one file union-merged across worktrees (mirroring the
    # git-level memmerge driver used for cross-machine merges), since two
    # worktrees diverging on it before ever syncing is the realistic case:
    # every worktree gets its own MEMORY.md immediately.
    repo_dir = tmp_path / "repo_memory"
    repo_dir.mkdir()

    root_a = tmp_path / "worktree_a"
    root_a.mkdir()
    (root_a / "MEMORY.md").write_text("- shared entry\n- from A\n")

    root_b = tmp_path / "worktree_b"
    root_b.mkdir()
    (root_b / "MEMORY.md").write_text("- shared entry\n- from B\n")

    merged = sync.collect_local_changes_multi(
        [root_a, root_b], repo_dir, old_manifest={}, prefix="projects/demo/memory"
    )

    content = (repo_dir / "MEMORY.md").read_text()
    assert "- shared entry" in content
    assert "- from A" in content
    assert "- from B" in content
    assert merged == {"projects/demo/memory/MEMORY.md": manifest.hash_bytes(content.encode())}


def test_collect_local_changes_multi_pushes_new_file_from_either_root(tmp_path):
    repo_dir = tmp_path / "repo_memory"
    repo_dir.mkdir()
    root_a = tmp_path / "worktree_a"
    root_a.mkdir()
    root_b = tmp_path / "worktree_b"
    root_b.mkdir()
    (root_b / "new_entry.md").write_text("- new\n")

    snapshot = sync.collect_local_changes_multi(
        [root_a, root_b], repo_dir, old_manifest={}, prefix="projects/demo/memory"
    )

    assert (repo_dir / "new_entry.md").read_text() == "- new\n"
    assert snapshot == {"projects/demo/memory/new_entry.md": manifest.hash_file(root_b / "new_entry.md")}


def test_apply_remote_file_copies_when_repo_has_new_content(tmp_path):
    local_path = tmp_path / "CLAUDE.md"
    repo_path = tmp_path / "data" / "CLAUDE.md"
    repo_path.parent.mkdir(parents=True)
    repo_path.write_text("global instructions")

    sync.apply_remote_file(local_path, repo_path, old_manifest={}, key="global/CLAUDE.md")

    assert local_path.read_text() == "global instructions"


def test_is_mass_deletion_true_when_most_of_manifest_disappeared(tmp_path):
    old_manifest = {f"skills/{i}.md": "hash" for i in range(10)}
    current_manifest = {"skills/0.md": "hash"}

    assert sync.is_mass_deletion(old_manifest, current_manifest) is True


def test_is_mass_deletion_false_for_partial_deletion(tmp_path):
    old_manifest = {f"skills/{i}.md": "hash" for i in range(10)}
    current_manifest = {f"skills/{i}.md": "hash" for i in range(9)}

    assert sync.is_mass_deletion(old_manifest, current_manifest) is False


def test_is_mass_deletion_false_when_old_manifest_empty():
    assert sync.is_mass_deletion({}, {}) is False


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
        f.write('{"cwd": "' + str(tmp_path / "nonexistent" / "claude-sync") + '"}\n')

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
