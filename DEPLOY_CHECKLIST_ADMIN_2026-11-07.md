# Deploy checklist — admin panel audit changes (2026-11-07)

Full details: `ADMIN_PANEL_AUDIT_2026-11-07.md`. Do these on the production server, in order.

## 1. Before deploying
- [ ] Take a database backup (System → Backups, or `mysqldump`).
- [ ] Add to the production `.env`:
  - `SECURITY_ALERT_EMAIL=<team inbox>`. WAF auto-block alerts go here. Until now the variable was never read, and alerts went to a hard-coded personal Gmail address. If it is unset, alerts now go to `DEFAULT_FROM_EMAIL`.
  - Optional but recommended: `ADMIN_MFA_ENABLED=True` (admin login asks for an emailed OTP).
  - Optional: `REDIS_URL=redis://...`, and `pip install redis`, if the host offers Redis.

## 2. Deploy
- [ ] `git pull` / upload code, then `pip install -r requirements.txt`.
- [ ] `python manage.py migrate`. New migrations: `agents 0042_move_models_from_admin_panel` and `admin_panel 0016_move_models_to_agents`. They are **state-only (0 SQL statements)**, so no table is changed.
- [ ] `python manage.py collectstatic --noinput`
- [ ] `python manage.py check --deploy`
- [ ] Restart the app.

## 3. Right after deploy
- [ ] `python manage.py ensure_admin_indexes`: review the list of MISSING indexes. (Done on the local DB 2026-11-07; production is a separate DB and still showed 8 missing.)
- [ ] `python manage.py ensure_admin_indexes --apply`: creates only the missing ones. On large tables run it at a quiet hour.
- [ ] Optional: `python manage.py remove_stale_contenttypes`, to clear the old `admin_panel.*` content types of the moved models.

## 4. Browser check (10 minutes)
Log in as a **Super Admin**, then as a **staff** admin with a few permissions.
- [ ] Sidebar: staff see only links they can open (no click leads to "not permitted").
- [ ] Dashboard charts render (plan distribution, growth).
- [ ] Any list with pagination (Agents, Contacts, Reviews): page 2 keeps the search/filter.
- [ ] Pending Registrations: list, pagination and totals look right.
- [ ] Broadcast: send a test to a small target. "Recent Broadcasts" shows the sent count after a short while.
- [ ] Free Trial page opens (it used to crash when no trial dates existed).
- [ ] Admin login: 10 wrong passwords for one account → "Too many failed attempts" for 15 minutes.

## 5. What changed for staff admins (tell the team)
- Assigning a paid plan, changing a user's email/password, and marking payments are **Super Admin only**.
- The pincode heatmap, banner/popup settings, invite studio, single-invoice sync and account-deletion requests are now open to staff with the matching permission.
- Dashboard and sidebar counters may be up to 2 minutes old (cached).
