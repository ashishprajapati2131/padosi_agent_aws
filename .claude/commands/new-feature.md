# /new-feature — Add a new feature to PadosiAgent

## Instructions for Claude

Before implementing any new feature, do this checklist:

1. **Read CLAUDE.md** — understand which app owns this feature, what auth system applies, which patterns to follow
2. **Identify the app** — home / agents / admin_panel / insurance / distributors / chatbot / referral_championship
3. **Plan the files needed:**
   - View file in `apps/<app>/views/<feature>.py`
   - URL entry in `apps/<app>/urls.py`
   - Template in `templates/<app>/<feature>.html`
   - Migration if new model: `python manage.py makemigrations <app>`
   - FastAPI router if mobile API also needs it
4. **Present the plan** — list files to create/modify and ask user to confirm
5. **Implement** — follow existing auth patterns, naming conventions, and middleware stack
6. **Verify** — run `python manage.py check` after implementation

## Auth Pattern Reminder
- Agent views: session check `request.session.get('agent_id')`
- Admin views: `@admin_required` decorator
- Insurance views: `@insurance_required` decorator
- Public views: no auth required

## URL Routing Reminder
- Add new URL in the app's own `urls.py`
- Home app (`apps/home/urls.py`) has a catch-all `<slug:slug>/` — everything must be above it

## CSRF Reminder
- AJAX POST calls need `X-CSRFToken` header
- Cookie name is `padosi_csrf_token` (NOT `csrftoken`)
