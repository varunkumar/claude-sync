import os
from pathlib import Path


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDESYNC_CLAUDE_HOME", str(Path.home() / ".claude")))


def repo_root() -> Path:
    default = Path(__file__).resolve().parent
    return Path(os.environ.get("CLAUDESYNC_REPO_ROOT", str(default)))


def data_dir() -> Path:
    return repo_root() / "data"


def state_dir() -> Path:
    return Path(os.environ.get("CLAUDESYNC_STATE_DIR", str(Path.home() / ".claudesync")))


def manifest_path() -> Path:
    return state_dir() / "manifest.json"


def settings_path() -> Path:
    return claude_home() / "settings.json"
