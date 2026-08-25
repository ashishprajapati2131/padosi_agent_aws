"""
Shared password hashing.

Admin login is the source of truth: bcrypt.hashpw / bcrypt.checkpw.
Every other account type (agent, distributor, insurance, client, FastAPI)
must hash and verify the same way so a password stored in `users` or
`auth_user` can be checked from either Django or FastAPI.
"""
import bcrypt

_BCRYPT_PREFIXES = ('$2a$', '$2b$', '$2x$', '$2y$')


def is_bcrypt_hash(stored_hash):
    value = (stored_hash or '').strip()
    if value.startswith('bcrypt$'):
        value = value.split('$', 1)[-1]
        if not value.startswith('$'):
            value = '$' + value
    return value.startswith(_BCRYPT_PREFIXES)


def hash_password(plain_password):
    """Create a bcrypt hash. Same call as admin create/update."""
    if plain_password is None:
        raise ValueError('Password is required')
    if not isinstance(plain_password, str):
        plain_password = str(plain_password)
    return bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _bcrypt_variants(stored_hash):
    value = (stored_hash or '').strip()
    if not value:
        return []
    if value.startswith('bcrypt$'):
        # Django hasher format: bcrypt$$2b$12$...
        raw = value.split('$', 1)[-1]
        if not raw.startswith('$'):
            raw = '$' + raw
        value = raw
    variants = [value]
    if value.startswith('$2y$') or value.startswith('$2a$') or value.startswith('$2x$'):
        variants.append('$2b$' + value[4:])
    return variants


def check_password_hash(plain_password, stored_hash):
    """
    Verify a password.

    Primary path matches admin login: bcrypt.checkpw().
    Also accepts Laravel $2y$ hashes and leftover Django pbkdf2 hashes.
    """
    if not plain_password or not stored_hash:
        return False
    if not isinstance(plain_password, str):
        plain_password = str(plain_password)
    stored_hash = stored_hash.strip()
    password_bytes = plain_password.encode('utf-8')

    for candidate in _bcrypt_variants(stored_hash):
        try:
            if bcrypt.checkpw(password_bytes, candidate.encode('utf-8')):
                return True
        except Exception:
            continue

    try:
        from django.contrib.auth.hashers import check_password as django_check_password
        if django_check_password(plain_password, stored_hash):
            return True
    except Exception:
        pass
    return False


def assign_password(user, plain_password):
    """Store a bcrypt hash on a Django or legacy user row."""
    user.password = hash_password(plain_password)
    return user.password
