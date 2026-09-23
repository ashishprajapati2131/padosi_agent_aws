# /new-model — Add a new Django model

## Instructions for Claude

When adding a new Django model:

1. **Decide the app** — which app logically owns this data?
2. **Create model file** — in `apps/<app>/models/<name>.py` or add to existing `models.py`
3. **Export** — add to `apps/<app>/models/__init__.py` if using package pattern
4. **Set `db_table`** — explicit snake_case table name
5. **Always include** `created_at = models.DateTimeField(auto_now_add=True)` and `updated_at = models.DateTimeField(auto_now=True)`
6. **managed=False ONLY** for pre-existing Laravel/legacy tables
7. **Run migration:**
   ```bash
   python manage.py makemigrations <app>
   python manage.py migrate
   ```
8. **If FastAPI needs it** — also add SQLAlchemy model in `fastapi_app/models/<name>.py`

## Critical Rules
- `USE_TZ=False` — DateTimeField stores naive datetimes
- Do NOT use `managed=False` for new models you control
- BigAutoField is the default PK (set in settings)
- bcrypt passwords via `hash_password()` — NEVER Django's `make_password()`
