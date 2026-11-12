# Uptime monitoring

## Why an outside check is needed

The built-in monitor (`apps/admin_panel/services/system_monitor.py`) runs inside
the app and is started by web traffic (`docs/CRON_JOBS.md`). If the server,
Apache or the app process is down, it cannot run and cannot email anyone. An
outside service has to watch the site.

## Endpoints

All return JSON, never error text, hostnames or credentials. All are public.

| URL | Checks | Healthy | Unhealthy |
|---|---|---|---|
| `/health/live` | App process answers. No database, no cache. | 200 | no answer / 5xx from Apache |
| `/health/ready` (same as `/health/`, `/healthz`) | Database + cache | 200 | 503 when the database fails |
| `/health/database` | `SELECT 1` | 200 | 503 |
| `/health/redis` | Cache round trip when `REDIS_URL` is set | 200 (`not_configured` when Redis is not used) | 503 |

The database result is kept for 10 seconds, so frequent probes cost at most one
`SELECT 1` every 10 seconds. Opening a connection gives up after
`DB_CONNECT_TIMEOUT` seconds (default 10).

## Setting up the outside monitor

Use any uptime service (UptimeRobot, Better Stack, Pingdom, Cloudflare Health
Checks). Create these monitors, alerting the admin email and a phone:

1. `https://padosiagent.com/health/live`, every 5 minutes. Fails = the server or app is down.
2. `https://padosiagent.com/health/database`, every 5 minutes. Fails while 1 passes = database problem.
3. `https://padosiagent.com/`, keyword check on a word from the homepage. Catches a broken page that still returns 200.
4. TLS certificate expiry and domain expiry alerts (a setting on monitor 1 in most services).

Alert after 2 failed checks in a row, not 1.

Side benefit: scheduled jobs here only start when a request arrives, so a
5-minute probe also keeps them running on time when the site is quiet.

## Reading the results

| live | database | Meaning |
|---|---|---|
| up | up | Fine |
| up | down | MySQL problem at the host. Check cPanel → phpMyAdmin, then hosting support |
| down | down | Server, Apache or the app is down. `touch tmp/restart.txt` from SSH; if SSH fails, hosting support |
