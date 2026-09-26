#!/usr/bin/env bash
set -e

# ==============================================================================
# PadosiAgent Instant One-Click Rollback Script (GoDaddy cPanel / Passenger WSGI)
# Usage:
#   ./scripts/rollback_godaddy.sh               # Rolls back to previous commit
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
if [ -z "$TARGET_COMMIT" ]; then
    STATE_FILE="tmp/.last_deployed_commit"
    if [ -f "$STATE_FILE" ]; then
        LAST_SAVED="$(cat "$STATE_FILE" 2>/dev/null || true)"
        CURRENT_HEAD="$(git rev-parse HEAD)"
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

# 4. Collect static files
echo "==> Re-collecting static files..."
$PY_BIN manage.py collectstatic --noinput

# 5. Restart Passenger WSGI
echo "==> Restarting Passenger WSGI application..."
mkdir -p tmp
touch tmp/restart.txt
echo "$ROLLED_COMMIT" > tmp/.last_deployed_commit

echo "===================================================="
echo " Rollback completed successfully to commit $ROLLED_COMMIT"
echo " Time: $(date)"
echo "===================================================="
