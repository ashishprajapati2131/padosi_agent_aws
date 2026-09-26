#!/usr/bin/env bash
# ==============================================================================
# Setup Automated Cron Jobs for PadosiAgent on GoDaddy cPanel
# ==============================================================================

DEPLOY_USER="${USER:-m69qf6gyhm3n}"
PROJECT_DIR="${1:-/home/$DEPLOY_USER/public_html}"
PY_BIN="/home/$DEPLOY_USER/virtualenv/padosiagentdjango/src/3.11/bin/python"

if [ ! -f "$PY_BIN" ]; then
    PY_BIN="$(command -v python3)"
fi

echo "================================================================="
echo " PadosiAgent GoDaddy cPanel Automated Crontab Configuration"
echo " User: $DEPLOY_USER"
echo " Project Directory: $PROJECT_DIR"
echo " Python Binary: $PY_BIN"
echo "================================================================="

CRON_1="*/10 * * * * cd $PROJECT_DIR && $PY_BIN manage.py reconcile_fulfillment >> logs/cron_reconcile.log 2>&1"
CRON_2="0 2 * * * cd $PROJECT_DIR && $PY_BIN manage.py backup_database --tag daily --retention 14 >> logs/cron_backup.log 2>&1"

echo ""
echo "Recommended Crontab Entries:"
echo "-----------------------------------------------------------------"
echo "# 1. Every 10 minutes: Reconcile unfulfilled subscriptions / invoices:"
echo "$CRON_1"
echo ""
echo "# 2. Every night at 02:00 AM: Automated Database Backup (14-day retention):"
echo "$CRON_2"
echo "-----------------------------------------------------------------"
echo ""
echo "To automatically install these into your user crontab, run:"
echo "  (crontab -l 2>/dev/null; echo \"$CRON_1\"; echo \"$CRON_2\") | crontab -"
