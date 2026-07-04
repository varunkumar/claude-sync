#!/usr/bin/env sh
set -eu

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$REPO_ROOT/data"

git -C "$REPO_ROOT" config merge.memmerge.driver "python3 $REPO_ROOT/memmerge.py %O %A %B %P"

CRON_CMD="*/15 * * * * cd $REPO_ROOT && /usr/bin/env python3 $REPO_ROOT/sync.py >> $HOME/.claudesync/sync.log 2>&1"
CRON_MARKER="# claude-sync"

mkdir -p "$HOME/.claudesync"

EXISTING_CRON="$(crontab -l 2>/dev/null || true)"
if ! printf '%s\n' "$EXISTING_CRON" | grep -qF "$CRON_MARKER"; then
  { printf '%s\n' "$EXISTING_CRON"; echo "$CRON_CMD $CRON_MARKER"; } | crontab -
  echo "Installed cron entry."
else
  echo "Cron entry already present; skipping."
fi

echo "claude-sync installed. Merge driver configured; cron runs every 15 minutes."
