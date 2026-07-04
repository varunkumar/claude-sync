import importlib


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


def test_data_dir_is_repo_root_slash_data(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDESYNC_REPO_ROOT", str(tmp_path))
    import paths
    importlib.reload(paths)
    assert paths.data_dir() == tmp_path / "data"


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
