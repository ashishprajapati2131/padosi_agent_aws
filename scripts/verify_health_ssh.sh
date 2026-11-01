#!/usr/bin/env bash
set -e

PROJECT_DIR="${1:-$PWD}"
if [ -d "$PROJECT_DIR" ]; then
    cd "$PROJECT_DIR"
fi

DEPLOY_USER="${USER:-m69qf6gyhm3n}"
if [ -f "/home/$DEPLOY_USER/virtualenv/padosiagentdjango/src/3.11/bin/python" ]; then
    PY_BIN="/home/$DEPLOY_USER/virtualenv/padosiagentdjango/src/3.11/bin/python"
elif [ -f "/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/bin/python" ]; then
    PY_BIN="/home/m69qf6gyhm3n/virtualenv/padosiagentdjango/src/3.11/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PY_BIN="$(command -v python3)"
else
    PY_BIN="python"
fi

echo "==> Running internal health verification on GoDaddy server with $PY_BIN ..."
$PY_BIN -c "
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'padosi_agent.settings')
django.setup()

from django.db import connection
from django.core.cache import cache

# 1. Database Connectivity Probe
with connection.cursor() as cursor:
    cursor.execute('SELECT 1;')
    row = cursor.fetchone()
    if not row or row[0] != 1:
        raise RuntimeError('Database SELECT 1 verification failed')

# 2. Cache Connectivity Probe
cache.set('__deploy_health_probe__', 'ok', timeout=15)
cached_val = cache.get('__deploy_health_probe__')
if cached_val != 'ok':
    raise RuntimeError('Cache set/get probe failed')

print('==> Internal Server Health Verified: Database OK, Cache OK, Django Engine OK.')
"

echo "==> Internal health check succeeded!"
exit 0

