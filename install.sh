#!/usr/bin/env sh
set -eu

if [ $# -lt 1 ]; then
  echo "usage: $0 <data-repo-git-url>" >&2
  exit 1
fi

DATA_REPO_URL="$1"
CODE_REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${CLAUDESYNC_STATE_DIR:-$HOME/.claudesync}"
DATA_REPO_DIR="$STATE_DIR/repo"

mkdir -p "$STATE_DIR"

if [ ! -d "$DATA_REPO_DIR" ]; then
  git clone "$DATA_REPO_URL" "$DATA_REPO_DIR"
fi

echo "$DATA_REPO_DIR" > "$STATE_DIR/repo_root"

if ! git -C "$DATA_REPO_DIR" log -1 >/dev/null 2>&1; then
  printf '%s\n' "projects/*/memory/MEMORY.md merge=memmerge" > "$DATA_REPO_DIR/.gitattributes"
  git -C "$DATA_REPO_DIR" add .gitattributes
  git -C "$DATA_REPO_DIR" commit -m "claude-sync: bootstrap data repo"
  CURRENT_BRANCH="$(git -C "$DATA_REPO_DIR" branch --show-current)"
  git -C "$DATA_REPO_DIR" push -u origin "$CURRENT_BRANCH"
fi

git -C "$DATA_REPO_DIR" config merge.memmerge.driver "python3 $CODE_REPO_ROOT/memmerge.py %O %A %B %P"

CRON_CMD="*/15 * * * * cd $CODE_REPO_ROOT && /usr/bin/env python3 $CODE_REPO_ROOT/sync.py >> $STATE_DIR/sync.log 2>&1"
CRON_MARKER="# claude-sync"

EXISTING_CRON="$(crontab -l 2>/dev/null || true)"
if ! printf '%s\n' "$EXISTING_CRON" | grep -qF "$CRON_MARKER"; then
  { printf '%s\n' "$EXISTING_CRON"; echo "$CRON_CMD $CRON_MARKER"; } | crontab -
  echo "Installed cron entry."
else
  echo "Cron entry already present; skipping."
fi

echo "claude-sync installed. Data repo: $DATA_REPO_DIR. Merge driver configured; cron runs every 15 minutes."
