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

echo "==> Pulling latest code from Git..."
git pull origin main

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

echo "==> Installing / upgrading Python dependencies..."
"$PIP_BIN" install -r requirements.txt

echo "==> Running database migrations..."
"$PY_BIN" manage.py migrate --noinput

echo "==> Collecting static files..."
"$PY_BIN" manage.py collectstatic --noinput

echo "==> Restarting Passenger WSGI application..."
mkdir -p tmp
touch tmp/restart.txt

echo "===================================================="
echo " Deployment completed successfully!"
echo " Time: $(date)"
echo "===================================================="
