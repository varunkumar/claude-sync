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
