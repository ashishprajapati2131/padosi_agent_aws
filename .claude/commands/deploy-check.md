# /deploy-check — Pre-deployment checklist

Run these checks before deploying to GoDaddy:

## 1. System check
```bash
python manage.py check
```

## 2. Pending migrations check  
```bash
python manage.py makemigrations --check --dry-run
```

## 3. Static files dry run
```bash
python manage.py collectstatic --noinput --dry-run
```

## 4. Run tests
```bash
python manage.py test apps.home apps.agents
```

## Manual checklist (verify with user)
- [ ] `.env` has `DEBUG=False` in production
- [ ] `SECRET_KEY` is set (not empty)
- [ ] `ALLOWED_HOSTS` includes the domain
- [ ] `CSRF_TRUSTED_ORIGINS` includes `https://padosiagent.com`
- [ ] `RAZORPAY_KEY` and `RAZORPAY_SECRET` are real (not test) keys for production
- [ ] `BREVO_OTP_FALLBACK=false` in production
- [ ] No new unreviewed migrations

Report results of automated checks. List any failures.
