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
    run_git(["add", "-A", "."], cwd=repo_root)
    if not has_staged_changes(repo_root):
        return False
    run_git(["commit", "-m", message], cwd=repo_root)
    try:
        git_push(repo_root)
    except subprocess.CalledProcessError:
        try:
            git_pull(repo_root)
            git_push(repo_root)
        except subprocess.CalledProcessError:
            # A conflict (e.g. in a file the memmerge driver doesn't cover,
            # such as the global CLAUDE.md) can leave the rebase started by
            # git_pull mid-flight. Abort it so the repo isn't left wedged for
            # the next cron run; the local commit made above is preserved.
            subprocess.run(["git", "rebase", "--abort"], cwd=repo_root)
            raise
    return True


def sync_once(home: Path, repo_root: Path, data: Path, state_manifest_path: Path) -> None:
    old_manifest = manifest.load_manifest(state_manifest_path)
    # `current` is populated by the collect_* calls below purely because their
    # signatures require an out-param to write into; it reflects local state
    # *before* the apply-down phase and is intentionally not what gets saved
    # to the manifest (see `final_manifest` below).
    current = {}

    global_local = home / "CLAUDE.md"
    global_repo = data / "global" / "CLAUDE.md"
    skills_local = home / "skills"
    skills_repo = data / "skills"
    project_targets = local_project_targets(home, data)
    settings_path = home / "settings.json"
    plugins_json_path = data / "plugins.json"

    # Collect local changes into the repo working tree *before* pulling, so
    # that a genuine conflict with concurrent remote changes to the same file
    # can be committed and reconciled by `git pull --rebase` (and thus by the
    # memmerge driver) instead of being silently clobbered by a plain copy.
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

    if not git_commit_and_push(repo_root, "claude-sync: update"):
        # Nothing local to commit, but another machine may have pushed
        # changes we don't have yet.
        git_pull(repo_root)

    # Apply the now-authoritative (possibly merged) repo content back down
    # into the local home directory.
    apply_remote_file(global_local, global_repo, old_manifest, "global/CLAUDE.md")
    apply_remote_changes(skills_local, skills_repo, old_manifest, "skills")
    for local_memory, repo_memory in project_targets:
        project_name = repo_memory.parent.name
        apply_remote_changes(local_memory, repo_memory, old_manifest, f"projects/{project_name}/memory")
    mirror.apply_plugins_from_repo(settings_path, plugins_json_path)

    # Re-snapshot from the repo/data side *after* the apply-down phase, rather
    # than saving the pre-apply `current` collected above. `data/` is the
    # authoritative post-merge state once the git commit/push/pull have
    # settled, and by this point local has been made to match it. Saving the
    # earlier, pre-apply snapshot would omit anything that arrived from a
    # remote machine this cycle (a merged MEMORY.md, a new skill, etc.),
    # causing it to be misdetected as a local change next cycle, and — worse —
    # a local deletion made in between two cycles could get silently
    # re-applied from the remote side because the manifest never reflected
    # the addition in the first place.
    final_manifest = {}
    if global_repo.is_file():
        final_manifest["global/CLAUDE.md"] = manifest.hash_file(global_repo)
    final_manifest.update(
        {f"skills/{rel}": digest for rel, digest in manifest.snapshot_tree(skills_repo).items()}
    )
    for local_memory, repo_memory in project_targets:
        project_name = repo_memory.parent.name
        prefix = f"projects/{project_name}/memory"
        final_manifest.update(
            {f"{prefix}/{rel}": digest for rel, digest in manifest.snapshot_tree(repo_memory).items()}
        )
    if plugins_json_path.is_file():
        final_manifest["plugins.json"] = manifest.hash_file(plugins_json_path)

    manifest.save_manifest(state_manifest_path, final_manifest)


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
