import sys
from pathlib import Path


def union_merge(local_text: str, remote_text: str) -> str:
    result = []
    seen = set()
    for line in local_text.splitlines():
        if line not in seen:
            result.append(line)
            seen.add(line)
    for line in remote_text.splitlines():
        if line not in seen:
            result.append(line)
            seen.add(line)
    return ("\n".join(result) + "\n") if result else ""


def main(argv) -> int:
    if len(argv) != 5:
        print("usage: memmerge.py <base> <local> <remote> <path>", file=sys.stderr)
        return 2
    _base_path, local_path, remote_path, _original_path = argv[1], argv[2], argv[3], argv[4]
    local_text = Path(local_path).read_text()
    remote_text = Path(remote_path).read_text()
    merged = union_merge(local_text, remote_text)
    Path(local_path).write_text(merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
