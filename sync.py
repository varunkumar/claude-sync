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
