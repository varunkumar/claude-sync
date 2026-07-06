import json
from pathlib import Path
from typing import Iterator, Optional


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
                        return Path(cwd).name
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
