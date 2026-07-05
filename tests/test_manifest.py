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
