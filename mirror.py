import json
from pathlib import Path

PLUGIN_KEYS = ("enabledPlugins", "extraKnownMarketplaces")


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


def remove_file(path: Path) -> None:
    if path.is_file():
        path.unlink()


def extract_plugin_settings(settings: dict) -> dict:
    return {key: settings.get(key, {}) for key in PLUGIN_KEYS}


def sync_plugins_to_repo(settings_path: Path, plugins_json_path: Path) -> None:
    if not settings_path.is_file():
        return
    settings = json.loads(settings_path.read_text())
    plugins_json_path.parent.mkdir(parents=True, exist_ok=True)
    plugins_json_path.write_text(
        json.dumps(extract_plugin_settings(settings), indent=2, sort_keys=True) + "\n"
    )


def apply_plugins_from_repo(settings_path: Path, plugins_json_path: Path) -> None:
    if not plugins_json_path.is_file():
        return
    incoming = json.loads(plugins_json_path.read_text())
    settings = json.loads(settings_path.read_text()) if settings_path.is_file() else {}
    for key in PLUGIN_KEYS:
        if key in incoming:
            settings[key] = incoming[key]
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n")
