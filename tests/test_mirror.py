import json

import mirror


def test_copy_file_creates_parent_dirs_and_copies_bytes(tmp_path):
    src = tmp_path / "src.md"
    src.write_bytes(b"content")
    dst = tmp_path / "nested" / "dst.md"

    mirror.copy_file(src, dst)

    assert dst.read_bytes() == b"content"


def test_remove_file_deletes_existing_file(tmp_path):
    f = tmp_path / "f.md"
    f.write_text("x")

    mirror.remove_file(f)

    assert not f.exists()


def test_remove_file_is_noop_when_missing(tmp_path):
    mirror.remove_file(tmp_path / "missing.md")  # must not raise


def test_extract_plugin_settings_pulls_only_plugin_keys():
    settings = {
        "hooks": {"SessionStart": []},
        "enabledPlugins": {"superpowers": True},
        "extraKnownMarketplaces": {"googlechrome": {"source": "x"}},
        "effortLevel": "medium",
    }

    extracted = mirror.extract_plugin_settings(settings)

    assert extracted == {
        "enabledPlugins": {"superpowers": True},
        "extraKnownMarketplaces": {"googlechrome": {"source": "x"}},
    }


def test_extract_plugin_settings_defaults_missing_keys_to_empty_dict():
    assert mirror.extract_plugin_settings({}) == {
        "enabledPlugins": {},
        "extraKnownMarketplaces": {},
    }


def test_sync_plugins_to_repo_writes_only_plugin_keys(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "hooks": {"SessionStart": []},
        "enabledPlugins": {"superpowers": True},
    }))
    plugins_json_path = tmp_path / "data" / "plugins.json"

    mirror.sync_plugins_to_repo(settings_path, plugins_json_path)

    written = json.loads(plugins_json_path.read_text())
    assert written == {"enabledPlugins": {"superpowers": True}, "extraKnownMarketplaces": {}}


def test_sync_plugins_to_repo_noop_when_settings_missing(tmp_path):
    plugins_json_path = tmp_path / "data" / "plugins.json"
    mirror.sync_plugins_to_repo(tmp_path / "missing_settings.json", plugins_json_path)
    assert not plugins_json_path.exists()


def test_apply_plugins_from_repo_merges_preserving_other_keys(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({
        "hooks": {"SessionStart": ["python3 hook.py"]},
        "enabledPlugins": {"old-plugin": True},
    }))
    plugins_json_path = tmp_path / "plugins.json"
    plugins_json_path.write_text(json.dumps({
        "enabledPlugins": {"superpowers": True, "github": True},
        "extraKnownMarketplaces": {},
    }))

    mirror.apply_plugins_from_repo(settings_path, plugins_json_path)

    result = json.loads(settings_path.read_text())
    assert result["hooks"] == {"SessionStart": ["python3 hook.py"]}
    assert result["enabledPlugins"] == {"superpowers": True, "github": True}


def test_apply_plugins_from_repo_creates_settings_when_missing(tmp_path):
    settings_path = tmp_path / "settings.json"
    plugins_json_path = tmp_path / "plugins.json"
    plugins_json_path.write_text(json.dumps({
        "enabledPlugins": {"superpowers": True},
        "extraKnownMarketplaces": {},
    }))

    mirror.apply_plugins_from_repo(settings_path, plugins_json_path)

    result = json.loads(settings_path.read_text())
    assert result == {"enabledPlugins": {"superpowers": True}, "extraKnownMarketplaces": {}}


def test_apply_plugins_from_repo_noop_when_plugins_json_missing(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"hooks": {}}))
    mirror.apply_plugins_from_repo(settings_path, tmp_path / "missing.json")
    assert json.loads(settings_path.read_text()) == {"hooks": {}}
