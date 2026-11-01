#!/usr/bin/env bash
set -e

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

PROJECT_DIR="${1:-$PWD}"
DEPLOY_USER="${2:-$USER}"

echo "===================================================="
echo " Starting Deployment on GoDaddy Server"
echo " Time: $(date)"
echo " Project Directory: $PROJECT_DIR"
echo " Deploy User: $DEPLOY_USER"
echo "===================================================="

if [ -d "$PROJECT_DIR" ]; then
    cd "$PROJECT_DIR"
else
    echo "ERROR: Project directory $PROJECT_DIR does not exist!"
    exit 1
fi

echo "==> Current Working Directory: $(pwd)"
mkdir -p tmp

# ── Free resources before heavy work ──────────────────────────────
# GoDaddy CloudLinux has strict per-user process/memory limits.
# Previous failed deploys or rollbacks can leave stale Python/Passenger
# workers that eat into the limit, causing "cannot fork()" on git pull.
echo "==> Cleaning up stale processes to free CloudLinux resources..."
# GoDaddy CloudLinux counts threads (nlwp) towards the NPROC limit.
# Each Passenger Python worker consumes 8-12 threads.
# Killing python workers releases ~30 threads instantly so git pull can fork.
# Passenger automatically spawns fresh workers upon restart.txt touch.
pkill -9 -u "$USER" -f 'python3.11_bin' 2>/dev/null || true
pkill -9 -u "$USER" -f 'passenger_wsgi' 2>/dev/null || true
pkill -9 -u "$USER" -f 'virtualenv/padosiagentdjango' 2>/dev/null || true
# Kill leftover collectstatic / migrate processes from failed deploys
pkill -9 -u "$USER" -f 'manage.py collectstatic' 2>/dev/null || true
pkill -9 -u "$USER" -f 'manage.py migrate' 2>/dev/null || true
# Give OS a moment to reclaim process & thread slots
sleep 3
echo "==> Process cleanup done. $(ps -u "$USER" --no-headers 2>/dev/null | wc -l) processes running."

# One deploy at a time: two overlapping deploys would run pip/collectstatic
# twice in parallel inside the same CloudLinux resource limits.
if command -v flock >/dev/null 2>&1; then
    exec 9>"tmp/deploy.lock"
    if ! flock -w 900 9; then
        echo "ERROR: another deployment is still running; giving up after 15 minutes."
        exit 1
    fi
fi

# Heavy steps run at low CPU priority so live requests are served first.
NICE=""
if command -v nice >/dev/null 2>&1; then
    NICE="nice -n 10"
fi

# Remember what is live now, so rollback_godaddy.sh can return to it. Only when
# HEAD is a finished deploy: a retried attempt must not record the half-pulled code.
CURRENT_HEAD="$(git rev-parse HEAD)"
if [ ! -f tmp/.last_deployed_commit ] || [ "$(cat tmp/.last_deployed_commit)" = "$CURRENT_HEAD" ]; then
    echo "$CURRENT_HEAD" > tmp/.previous_deployed_commit
fi

# A rollback leaves a detached HEAD; get back on main so the pull works.
if ! git symbolic-ref -q HEAD >/dev/null; then
    git checkout main
fi

echo "==> Pulling latest code from Git..."
# Retry git pull up to 3 times — CloudLinux may need a moment to reclaim
# process slots after the cleanup above.
for _pull_try in 1 2 3; do
    if git pull origin main; then
        break
    fi
    echo "==> git pull attempt $_pull_try failed; waiting 5s for resources to free up..."
    sleep 5
    if [ "$_pull_try" -eq 3 ]; then
        echo "==> ERROR: git pull failed after 3 attempts."
        exit 1
    fi
done
NEW_COMMIT="$(git rev-parse HEAD)"

echo "==> Detecting Python virtualenv..."
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
    echo "ERROR: Could not locate Python binary!"
    exit 1
fi

echo "==> Using Python binary: $PY_BIN"
echo "==> Python version: $($PY_BIN --version 2>&1)"
echo "==> Using Pip binary: $PIP_BIN"

echo "==> Verifying Production Environment Configuration..."
$PY_BIN manage.py verify_production_env || echo "WARNING: Production environment configuration has warnings."

# Compare against the last deploy that finished successfully (not the
# pre-pull HEAD), so a deploy that failed half-way is fully redone next time.
STATE_FILE="tmp/.last_deployed_commit"
LAST_COMMIT="$(cat "$STATE_FILE" 2>/dev/null || true)"
RUN_ALL=0
if [ -z "$LAST_COMMIT" ] || ! git cat-file -e "${LAST_COMMIT}^{commit}" 2>/dev/null; then
    echo "==> No record of a previous successful deploy: running every step."
    RUN_ALL=1
    CHANGED=""
else
    CHANGED="$(git diff --name-only "$LAST_COMMIT" "$NEW_COMMIT")"
    echo "==> Files changed since last successful deploy ($LAST_COMMIT):"
    echo "${CHANGED:-  (none)}" | head -50
fi

changed() {
    [ "$RUN_ALL" = "1" ] && return 0
    echo "$CHANGED" | grep -Eq "$1"
}

REQ_CHANGED=0
if changed '^requirements\.txt$'; then REQ_CHANGED=1; fi

if [ "$REQ_CHANGED" = "1" ]; then
    echo "==> Installing / upgrading Python dependencies..."
    $NICE "$PIP_BIN" install --disable-pip-version-check -r requirements.txt
else
    echo "==> requirements.txt unchanged: skipping pip install."
fi

if [ "$REQ_CHANGED" = "1" ] || changed '/migrations/[^/]+\.py$'; then
    echo "==> Creating automated pre-migration database backup..."
    $NICE "$PY_BIN" manage.py backup_database --tag pre_deploy --retention 7 || { echo "ERROR: backup failed, aborting before migrate"; exit 1; }
    echo "==> Running database migrations..."
    $NICE "$PY_BIN" manage.py migrate --noinput
else
    echo "==> No migration files changed: skipping migrate."
fi

if [ "$REQ_CHANGED" = "1" ] || [ ! -f staticfiles/staticfiles.json ] \
        || changed '(^|/)static/|^padosi_agent/(settings|storage)\.py$'; then
    echo "==> Collecting static files..."
    $NICE "$PY_BIN" manage.py collectstatic --noinput
else
    echo "==> No static files changed: skipping collectstatic."
fi

echo "==> Restarting Passenger WSGI application..."
touch tmp/restart.txt

echo "$NEW_COMMIT" > "$STATE_FILE"

echo "===================================================="
echo " Deployment completed successfully! ($NEW_COMMIT)"
echo " Time: $(date)"
echo "===================================================="
