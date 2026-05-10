# 01 — Project Setup & Custom User Model

## What this covers
- Tool choices and why (uv over pip/poetry)
- Django project structure for production
- Settings architecture (base/dev/prod split)
- Custom User model — the most critical early decision

---

## Tool Stack

| Tool | Purpose | Why |
|---|---|---|
| `uv` | Python version + virtualenv + package manager | Replaces pyenv + venv + pip. Rust-based, 10-100x faster, generates a lock file automatically |
| `django-debug-toolbar` | Dev-only query inspection | Detects N+1s, shows SQL, measures request time |
| `python-dotenv` | Load `.env` into environment | Keeps secrets out of code |

---

## Project Initialization

```bash
mkdir django-blog && cd django-blog
uv init
uv python install 3.12.7
uv python pin 3.12.7          # creates .python-version — commit this
uv add django==5.0.6
uv add django-debug-toolbar --dev    # --dev = never goes to prod
uv add python-dotenv
uv run django-admin startproject config .   # 'config' not 'myproject', dot = current dir
```

**Why `config` for the project package?**
The inner folder is configuration, not application code. Naming it `config` makes that explicit. Every app you write lives in `apps/`.

**Why the trailing dot in `startproject`?**
Without it Django creates a nested directory: `project/project/manage.py`. The dot puts everything in the current directory cleanly.

---

## Directory Structure

```
django-blog/
├── apps/
│   ├── users/          ← auth domain
│   └── blog/           ← blog domain
├── config/
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py     ← shared settings
│   │   ├── dev.py      ← debug, sqlite, console email
│   │   └── prod.py     ← env vars, postgresql, security headers
│   ├── urls.py
│   ├── wsgi.py         ← points to settings.prod
│   └── asgi.py
├── .env                ← never committed
├── .gitignore
├── .python-version     ← commit this
├── manage.py           ← points to settings.dev by default
├── pyproject.toml
└── uv.lock             ← commit this, ensures reproducible installs
```

**Why split apps into their own `apps/` folder?**
Keeps domain code separate from configuration. Scales cleanly as the project grows. Each app is a self-contained module responsible for one domain.

---

## Settings Architecture

### base.py — shared across all environments
```python
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # 3 parents — file is 3 levels deep

SECRET_KEY = os.environ['SECRET_KEY']   # [] not .get() — missing key should crash loudly

AUTH_USER_MODEL = 'users.User'          # must be set before first migration

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.users',
    'apps.blog',
]
```

### dev.py — local development
```python
from .base import *

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']

INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
INTERNAL_IPS = ['127.0.0.1']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

### prod.py — production
```python
from .base import *
import os

DEBUG = False
ALLOWED_HOSTS = os.environ['ALLOWED_HOSTS'].split(',')
SECRET_KEY = os.environ['SECRET_KEY']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DB_NAME'],
        'USER': os.environ['DB_USER'],
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST': os.environ['DB_HOST'],
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

**Why `os.environ['KEY']` not `os.environ.get('KEY')`?**
`.get()` returns `None` silently. In production a missing `SECRET_KEY` should crash at startup, not fail mysteriously at runtime. Fail fast, fail loud.

### manage.py — load .env before anything
```python
from dotenv import load_dotenv

def main():
    load_dotenv()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
    ...
```

### wsgi.py — production default
```python
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.prod')
```

---

## .env file (never commit this)
```bash
DJANGO_SETTINGS_MODULE=config.settings.dev
SECRET_KEY=django-insecure-local-dev-key-change-in-prod
```

---

## App Registration — the name matters

When apps live inside `apps/`, their `AppConfig.name` must reflect the full Python path:

```python
# apps/users/apps.py
class UsersConfig(AppConfig):
    name = 'apps.users'        # full Python import path
    # app_label defaults to 'users' — the last segment
```

Django derives `app_label = 'users'` automatically from the last segment of `name`. This is what you use in `AUTH_USER_MODEL = 'users.User'` — app_label, not full path.

---

## Custom User Model

### The rule
**Always define a custom User model at the start of every project.**
If you start with Django's default `auth.User` and later need to change it, you cannot — the migration graph is locked. A custom model costs 10 minutes now and saves enormous pain later.

### The model
```python
# apps/users/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """
    Custom user model. Extends AbstractUser — identical for now but freely extensible.
    """
    email = models.EmailField(unique=True)   # override base: adds unique=True, removes blank=True

    USERNAME_FIELD = 'email'         # email is the login identifier
    REQUIRED_FIELDS = ['username']   # collected by createsuperuser but not the login field

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'

    def __str__(self):
        return self.email
```

**Why redeclare `email` if `AbstractUser` already has it?**
Django's default: `email = models.EmailField(blank=True)` — optional, not unique.
Our override: `email = models.EmailField(unique=True)` — required, database-level UNIQUE index.
The override pushes the constraint to the database. Application bugs can't create duplicate emails.

**Why `REQUIRED_FIELDS = ['username']` and not `['username', 'email']`?**
`REQUIRED_FIELDS` = fields prompted during `createsuperuser` after `USERNAME_FIELD`.
Since `USERNAME_FIELD = 'email'`, Django already prompts for email first.
Adding email to `REQUIRED_FIELDS` would prompt for it twice — Django raises `auth.E002`.

### Register in settings
```python
# config/settings/base.py
AUTH_USER_MODEL = 'users.User'   # must be set before the first migration
```

### Always reference User indirectly
```python
# In models — use settings reference
from django.conf import settings
author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

# In views/elsewhere — use get_user_model()
from django.contrib.auth import get_user_model
User = get_user_model()
```
Never import your User model directly. If `AUTH_USER_MODEL` ever changes, indirect references update automatically.

---

## Database Tables Created

After `migrate`, Django creates these tables:

| Table | Owner | Purpose |
|---|---|---|
| `django_content_type` | contenttypes | One row per model. Powers permissions and generic relations. |
| `auth_permission` | auth | All `add/change/delete/view` permissions, auto-created per model. |
| `auth_group` | auth | Named permission groups e.g. "editors" |
| `auth_group_permissions` | auth | Junction — which permissions belong to which group |
| `users_user` | your code | Your custom User table |
| `users_user_groups` | your code | Junction — user ↔ group membership |
| `users_user_user_permissions` | your code | Junction — direct user ↔ permission assignments |
| `django_admin_log` | admin | Audit log of every admin action |
| `django_session` | sessions | Active browser sessions, keyed by session cookie |
| `django_migrations` | Django internals | Tracks applied migrations. `migrate` reads this to know what to skip. |

**Migration dependency order:** `contenttypes → auth → users → admin → sessions`
Each depends on the previous. Django enforces this order automatically.

---

## Key Commands Reference

```bash
uv run python manage.py check             # validate settings and models
uv run python manage.py makemigrations    # generate migration files from model changes
uv run python manage.py migrate           # apply pending migrations to the database
uv run python manage.py createsuperuser   # create an admin user
uv run python manage.py shell             # interactive Python shell with Django loaded
uv run python manage.py runserver         # start dev server
```

---

## Concepts to Know Cold

**QuerySet laziness** — `Model.objects.filter(...)` builds a query object. No SQL runs until you iterate, slice, or call `.first()`, `.count()`, `.exists()`.

**`blank` vs `null`** — `blank=True` = form/serializer allows empty string. `null=True` = database allows NULL. Never use `null=True` on string fields — pick one representation of "nothing".

**`app_label` vs `name`** — `name = 'apps.users'` is the Python import path. `app_label = 'users'` is the short identifier Django uses in permission strings, `AUTH_USER_MODEL`, and table name prefixes.

**Migration state** — Django tracks applied migrations in `django_migrations`. `--fake` writes a row without running SQL. Use when manually applying a migration or syncing environments.