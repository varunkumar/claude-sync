import os
from pathlib import Path


def claude_home() -> Path:
    return Path(os.environ.get("CLAUDESYNC_CLAUDE_HOME", str(Path.home() / ".claude")))


def state_dir() -> Path:
    return Path(os.environ.get("CLAUDESYNC_STATE_DIR", str(Path.home() / ".claudesync")))


def repo_root_config_path() -> Path:
    return state_dir() / "repo_root"


def repo_root() -> Path:
    env_override = os.environ.get("CLAUDESYNC_REPO_ROOT")
    if env_override:
        return Path(env_override)
    config_path = repo_root_config_path()
    if config_path.is_file():
        return Path(config_path.read_text().strip())
    raise RuntimeError(
        f"No data repo configured (checked CLAUDESYNC_REPO_ROOT and {config_path}). "
        "Run install.sh <data-repo-git-url> to set one up."
    )


def data_dir() -> Path:
    return repo_root()


def manifest_path() -> Path:
    return state_dir() / "manifest.json"


def project_names_path() -> Path:
    return state_dir() / "project_names.json"


def settings_path() -> Path:
    return claude_home() / "settings.json"
