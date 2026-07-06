import importlib

import pytest


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


def test_repo_root_reads_persisted_config_file_when_no_env_override(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDESYNC_REPO_ROOT", raising=False)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("CLAUDESYNC_STATE_DIR", str(state_dir))
    data_repo = tmp_path / "data_repo"
    (state_dir / "repo_root").write_text(str(data_repo) + "\n")
    import paths
    importlib.reload(paths)
    assert paths.repo_root() == data_repo


def test_repo_root_raises_when_nothing_configured(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDESYNC_REPO_ROOT", raising=False)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("CLAUDESYNC_STATE_DIR", str(state_dir))
    import paths
    importlib.reload(paths)
    with pytest.raises(RuntimeError):
        paths.repo_root()


def test_data_dir_equals_repo_root(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDESYNC_REPO_ROOT", str(tmp_path))
    import paths
    importlib.reload(paths)
    assert paths.data_dir() == tmp_path


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
