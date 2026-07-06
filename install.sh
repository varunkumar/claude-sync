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
VERSION="$(cat "$CODE_REPO_ROOT/VERSION" 2>/dev/null || echo unknown)"

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

# Offset each machine's sync to a random minute within the 15-minute grid,
# rather than every machine hitting :00/:15/:30/:45 at once and racing on push.
RAND_MINUTE=$(( $(od -An -N2 -tu2 /dev/urandom | tr -d ' ') % 15 ))
CRON_MINUTES="$RAND_MINUTE,$((RAND_MINUTE + 15)),$((RAND_MINUTE + 30)),$((RAND_MINUTE + 45))"
CRON_CMD="$CRON_MINUTES * * * * cd $CODE_REPO_ROOT && /usr/bin/env python3 $CODE_REPO_ROOT/sync.py >> $STATE_DIR/sync.log 2>&1"
CRON_MARKER="# claude-sync"

# Re-running this script (e.g. to pick up an upgrade) replaces any existing
# claude-sync cron line rather than leaving a stale one in place, so changes
# to the schedule or to CODE_REPO_ROOT actually take effect.
EXISTING_CRON="$(crontab -l 2>/dev/null || true)"
OTHER_CRON="$(printf '%s\n' "$EXISTING_CRON" | grep -vF "$CRON_MARKER" || true)"
{ printf '%s\n' "$OTHER_CRON"; echo "$CRON_CMD $CRON_MARKER"; } | crontab -
echo "Cron entry set at minute offset :$RAND_MINUTE."

echo "$VERSION" > "$STATE_DIR/installed_version"
echo "claude-sync $VERSION installed. Data repo: $DATA_REPO_DIR. Merge driver configured; cron runs every 15 minutes (offset :$RAND_MINUTE)."
