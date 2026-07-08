import json
import re
import subprocess
from pathlib import Path
from typing import Iterator, Optional

_SCP_STYLE_RE = re.compile(r"^[\w.-]+@([\w.-]+):(.+)$")
_URL_STYLE_RE = re.compile(r"^\w+://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$")


def normalize_remote_url(url: str) -> str:
    """Canonicalize a git remote URL to a stable, protocol-agnostic key,
    e.g. both 'git@github.com:org/repo.git' and 'https://github.com/org/repo'
    normalize to 'github.com/org/repo'."""
    url = url.strip()
    match = _SCP_STYLE_RE.match(url) if "://" not in url else None
    if match is None:
        match = _URL_STYLE_RE.match(url)
    if match is None:
        return url
    host, path = match.group(1).lower(), match.group(2).strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    return f"{host}/{path}"


def get_git_remote_url(repo_dir: Path) -> Optional[str]:
    """Return the 'origin' remote URL for the git repo/worktree at repo_dir,
    or None if it isn't a git repo, has no origin, or no longer exists."""
    if not repo_dir.is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def resolve_project_key(cwd: Path) -> str:
    """Resolve a stable project key for cwd: the normalized git remote URL
    when one can be determined (this also unifies worktrees with their main
    checkout, since they share the same remote), otherwise the directory's
    own basename (e.g. when it has no remote, or has been deleted/moved)."""
    remote = get_git_remote_url(cwd)
    if remote:
        return normalize_remote_url(remote)
    return cwd.name


def resolve_project_basename(project_dir: Path) -> Optional[str]:
    for jsonl_path in sorted(project_dir.glob("*.jsonl")):
        try:
            with jsonl_path.open() as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cwd = record.get("cwd")
                    if cwd:
                        return resolve_project_key(Path(cwd))
        except OSError:
            continue
    return None


def resolve_project_basename_cached(project_dir: Path, name_cache: dict) -> Optional[str]:
    """Resolve a project's basename, falling back to a previously-cached
    result if no jsonl with a cwd remains (e.g. it was rotated away since the
    last successful resolution)."""
    name = resolve_project_basename(project_dir)
    if name is not None:
        name_cache[project_dir.name] = name
        return name
    return name_cache.get(project_dir.name)


def iter_project_dirs(claude_home: Path) -> Iterator[Path]:
    projects_root = claude_home / "projects"
    if not projects_root.is_dir():
        return
    for entry in sorted(projects_root.iterdir()):
        if entry.is_dir():
            yield entry
