#!/usr/bin/env bash
set -e

# ==============================================================================
# PadosiAgent Instant One-Click Rollback Script (GoDaddy cPanel / Passenger WSGI)
# Usage:
#   ./scripts/rollback_godaddy.sh               # Rolls back to the commit live before the last deploy
#   ./scripts/rollback_godaddy.sh <commit_sha>  # Rolls back to specific commit
# ==============================================================================

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

PROJECT_DIR="${PROJECT_DIR:-$PWD}"
TARGET_COMMIT="$1"

cd "$PROJECT_DIR"

echo "===================================================="
echo " Initiating Rollback on GoDaddy Server"
echo " Time: $(date)"
echo " Project Directory: $PROJECT_DIR"
echo "===================================================="

# 1. Determine target rollback commit
CURRENT_HEAD="$(git rev-parse HEAD)"
if [ -z "$TARGET_COMMIT" ]; then
    # Written by deploy_godaddy.sh just before it pulls.
    PREV_SAVED="$(cat tmp/.previous_deployed_commit 2>/dev/null || true)"
    if [ -n "$PREV_SAVED" ] && [ "$PREV_SAVED" != "$CURRENT_HEAD" ]             && git cat-file -e "${PREV_SAVED}^{commit}" 2>/dev/null; then
        TARGET_COMMIT="$PREV_SAVED"
    fi
fi
if [ -z "$TARGET_COMMIT" ]; then
    STATE_FILE="tmp/.last_deployed_commit"
    if [ -f "$STATE_FILE" ]; then
        LAST_SAVED="$(cat "$STATE_FILE" 2>/dev/null || true)"
        if [ "$LAST_SAVED" != "$CURRENT_HEAD" ] && [ -n "$LAST_SAVED" ]; then
            TARGET_COMMIT="$LAST_SAVED"
        fi
    fi
    if [ -z "$TARGET_COMMIT" ]; then
        TARGET_COMMIT="HEAD~1"
    fi
fi

echo "==> Target rollback commit: $TARGET_COMMIT"

# 2. Detect Python binary
DEPLOY_USER="${USER:-m69qf6gyhm3n}"
if [ -f "/home/$DEPLOY_USER/virtualenv/padosiagentdjango/src/3.11/bin/python" ]; then
    PY_BIN="/home/$DEPLOY_USER/virtualenv/padosiagentdjango/src/3.11/bin/python"
    PIP_BIN="/home/$DEPLOY_USER/virtualenv/padosiagentdjango/src/3.11/bin/pip"
elif [ -f "/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/bin/python" ]; then
    PY_BIN="/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/bin/python"
    PIP_BIN="/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/bin/pip"
elif command -v python3 >/dev/null 2>&1; then
    PY_BIN="$(command -v python3)"
    PIP_BIN="$(command -v pip3 || command -v pip)"
else
    PY_BIN="python"
    PIP_BIN="pip"
fi

# 3. Checkout target commit
echo "==> Checking out target commit $TARGET_COMMIT..."
git checkout "$TARGET_COMMIT"
ROLLED_COMMIT="$(git rev-parse HEAD)"

# 4. Dependencies: reinstall only if requirements.txt differs between the two commits.
if ! git diff --quiet "$ROLLED_COMMIT" "$CURRENT_HEAD" -- requirements.txt; then
    echo "==> requirements.txt differs: reinstalling dependencies..."
    "$PIP_BIN" install --disable-pip-version-check -r requirements.txt
else
    echo "==> requirements.txt unchanged: skipping pip install."
fi

# Migrations are NOT reversed automatically (a reverse can drop data). List them for a human.
MIGRATION_DIFF="$(git diff --name-status "$ROLLED_COMMIT" "$CURRENT_HEAD" -- '*/migrations/*.py' || true)"
if [ -n "$MIGRATION_DIFF" ]; then
    echo "===================================================="
    echo " WARNING: migrations differ between $ROLLED_COMMIT and $CURRENT_HEAD"
    echo " The database schema was NOT rolled back. Review these and, if needed,"
    echo " reverse them by hand (manage.py migrate <app> <previous_migration>)"
    echo " after checking for data loss; restore_database is the last resort."
    echo "$MIGRATION_DIFF"
    echo "===================================================="
fi

# 5. Collect static files
echo "==> Re-collecting static files..."
$PY_BIN manage.py collectstatic --noinput

# 6. Restart Passenger WSGI
echo "==> Restarting Passenger WSGI application..."
mkdir -p tmp
touch tmp/restart.txt
echo "$ROLLED_COMMIT" > tmp/.last_deployed_commit

echo "===================================================="
echo " Rollback completed successfully to commit $ROLLED_COMMIT"
echo " Time: $(date)"
echo "===================================================="
