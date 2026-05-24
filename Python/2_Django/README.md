# Django Master Reference

Quick-lookup cheatsheet for starting and working on any Django project.

---

## 1. Project Initialization

```bash
mkdir project-name && cd project-name
uv init
uv python install 3.12.7
uv python pin 3.12.7
uv add django==5.0.6
uv add django-debug-toolbar python-dotenv --dev
uv run django-admin startproject config .
mkdir apps
uv run python manage.py startapp appname
mv appname apps/appname
git init
```

---

## 2. Directory Structure

```
project/
├── apps/
│   ├── users/          ← auth domain
│   └── blog/           ← feature domain
├── config/
│   ├── settings/
│   │   ├── base.py     ← shared
│   │   ├── dev.py      ← debug, sqlite
│   │   └── prod.py     ← env vars, postgres, security
│   ├── urls.py
│   ├── wsgi.py         ← points to settings.prod
│   └── asgi.py
├── .env                ← never commit
├── .gitignore
├── .python-version     ← commit this
├── manage.py           ← points to settings.dev
├── pyproject.toml
└── uv.lock             ← commit this
```

---

## 3. Settings Split

```python
# base.py
from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # 3 parents
SECRET_KEY = os.environ['SECRET_KEY']   # [] = crash loudly if missing
AUTH_USER_MODEL = 'users.User'          # set before first migration

# dev.py
from .base import *
DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1']
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# prod.py
from .base import *
import os
DEBUG = False
ALLOWED_HOSTS = os.environ['ALLOWED_HOSTS'].split(',')
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
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = 31536000
```

---

## 4. App Registration

```python
# apps/users/apps.py
class UsersConfig(AppConfig):
    name = 'apps.users'        # full Python path
    # app_label = 'users'      # auto-derived from last segment

# config/settings/base.py
INSTALLED_APPS = [
    ...
    'apps.users',
    'apps.blog',
]
```

---

## 5. Custom User Model — Always

```python
# apps/users/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    email = models.EmailField(unique=True)   # override: adds unique, removes blank
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']           # email NOT here — already prompted

    def __str__(self):
        return self.email

# config/settings/base.py
AUTH_USER_MODEL = 'users.User'   # before first migration — no exceptions
```

**Always reference User indirectly:**
```python
# models.py
author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

# views/logic
from django.contrib.auth import get_user_model
User = get_user_model()
```

---

## 6. Models

```python
class Post(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        ARCHIVED = 'archived', 'Archived'

    title = models.CharField(max_length=250)
    slug = models.SlugField(unique=True, max_length=250)
    body = models.TextField()
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='posts',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    tags = models.ManyToManyField('Tag', blank=True, related_name='posts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
```

### Field rules
```
CharField/TextField   → blank=True for optional strings, never null=True
DateTimeField         → null=True, blank=True for optional timestamps
ForeignKey            → always set on_delete and related_name
ManyToManyField       → blank=True if optional, related_name always
SlugField             → use over CharField for URL identifiers
```

### `blank` vs `null`
```
blank=True  → form/serializer allows empty string (app level)
null=True   → database allows NULL (db level)
Never null=True on string fields — use blank=True only
```

### `on_delete` options
```
CASCADE    → delete this row when related object deleted
SET_NULL   → set FK to NULL (requires null=True)
PROTECT    → prevent deletion of related object
```

### ManyToMany — auto vs explicit junction
```python
# Auto junction — no extra data needed
tags = models.ManyToManyField(Tag, related_name='posts')

# Explicit junction — need extra fields on relationship
class PostTag(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

tags = models.ManyToManyField(Tag, through='PostTag', related_name='posts')
```

### related_name — when required
```python
# Two FKs to same model — related_name required on both
author = models.ForeignKey(User, related_name='authored_posts', ...)
editor = models.ForeignKey(User, related_name='edited_posts', ...)

# Disable reverse accessor
fk = models.ForeignKey(User, related_name='+', ...)
```

---

## 7. ORM

```python
# Lazy — no query yet
qs = Post.objects.filter(status='published')
qs = qs.select_related('author')
qs = qs.prefetch_related('tags', 'comments')

# Evaluates — query fires
list(qs)
qs.first()
qs.count()     # COUNT — no objects fetched
qs.exists()    # EXISTS — no objects fetched

# Debug SQL
print(qs.query)

# Verify query count
from django.db import connection, reset_queries
from django.conf import settings
settings.DEBUG = True
reset_queries()
# ... run queries ...
print(len(connection.queries))
```

### N+1 — detect and fix
```python
# N+1 — 1 + N queries
posts = Post.objects.all()
for post in posts:
    print(post.author.email)   # query per post

# Fix — ForeignKey/OneToOne
posts = Post.objects.select_related('author')
# SQL: LEFT OUTER JOIN (null=True FK) or INNER JOIN (null=False FK)

# Fix — ManyToMany/reverse FK
posts = Post.objects.prefetch_related('tags', 'comments')
# SQL: separate query with IN (id1, id2, ...) — always 2 queries total

# Fix — only need count
from django.db.models import Count
posts = Post.objects.annotate(comment_count=Count('comments'))
post.comment_count   # integer, no Comment objects loaded
```

### Q objects, F objects, annotations
```python
from django.db.models import Q, F, Count, Avg

# Q — complex filters
Post.objects.filter(Q(status='published') | Q(author=user))
Post.objects.filter(Q(title__icontains='django') & ~Q(status='archived'))

# F — reference another field
Post.objects.filter(updated_at__gt=F('created_at'))

# Annotations — computed fields
Post.objects.annotate(
    comment_count=Count('comments'),
    avg_rating=Avg('ratings__score'),
)
```

---

## 8. Migrations

```bash
uv run python manage.py makemigrations        # generate from model changes
uv run python manage.py migrate               # apply pending
uv run python manage.py showmigrations        # show applied/pending state
uv run python manage.py sqlmigrate blog 0001  # show SQL for a migration
uv run python manage.py migrate --fake        # mark applied without running SQL
```

Migration dependency order: `contenttypes → auth → users → blog → admin → sessions`

---

## 9. Serializers

```python
# Read serializer — nested objects
class PostSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    comment_count = serializers.SerializerMethodField()

    class Meta:
        model = Post
        fields = ['id', 'title', 'author', 'tags', 'comment_count']

    def get_comment_count(self, obj):
        return obj.comments.count()

# Write serializer — ID input, server-injected fields excluded
class PostCreateSerializer(serializers.ModelSerializer):
    tags = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tag.objects.all(), required=False
    )

    class Meta:
        model = Post
        fields = ['title', 'slug', 'body', 'status', 'tags']
        # author NOT here — injected in perform_create

    def create(self, validated_data):
        tags = validated_data.pop('tags', [])
        post = Post.objects.create(**validated_data)
        post.tags.set(tags)
        return post

    def update(self, instance, validated_data):
        tags = validated_data.pop('tags', None)
        post = super().update(instance, validated_data)
        if tags is not None:
            post.tags.set(tags)
        return post
```

### Validation layers
```python
# Field-level
password = serializers.CharField(min_length=8)

# Field-level custom
def validate_email(self, value):
    if 'spam' in value:
        raise serializers.ValidationError("Invalid email.")
    return value

# Cross-field
def validate(self, data):
    if data['password'] != data['confirm_password']:
        raise serializers.ValidationError("Passwords don't match.")
    return data
```

### Related field options
```
PrimaryKeyRelatedField  → input: IDs, output: IDs
Nested serializer       → input/output: full objects (read_only for output-only)
StringRelatedField      → output: __str__() value
SlugRelatedField        → input/output: specific field value
SerializerMethodField   → output: computed value, always read_only
```

### Three data sources
```
Client sends:     fields client controls — title, body, tag IDs
URL provides:     identifiers — slug, parent resource ID
Server injects:   author=request.user, post=from URL kwargs
```

---

## 10. Views

### APIView — maximum control
```python
class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=201)
```

### Generic Views — standard patterns
```python
class PostListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return Post.objects.select_related('author').filter(status='published')

    def get_serializer_class(self):
        return PostCreateSerializer if self.request.method == 'POST' else PostSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)
```

### ViewSet — full resource
```python
class PostViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthorOrReadOnly]
    lookup_field = 'slug'

    def get_queryset(self):
        ...

    def get_serializer_class(self):
        if self.action == 'list': return PostSerializer
        if self.action == 'retrieve': return PostDetailSerializer
        return PostCreateSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthorOrReadOnly()]

    @action(detail=True, methods=['post'])
    def publish(self, request, slug=None):
        post = self.get_object()
        post.publish()
        return Response(PostSerializer(post).data)
```

```python
# urls.py
router = DefaultRouter()
router.register('posts', PostViewSet, basename='post')
# basename required when using get_queryset() not class-level queryset
urlpatterns = router.urls
```

### When to use which
```
APIView      → auth, search, custom non-resource operations
Generics     → 1-2 operations, simple resources
ViewSet      → full CRUD resource + custom actions
```

---

## 11. Permissions

```python
# apps/blog/permissions.py
class IsAuthorOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(obj, 'author', None) == request.user
```

```
has_permission()        → model-level, every request
has_object_permission() → object-level, only when self.get_object() called
SAFE_METHODS            → ('GET', 'HEAD', 'OPTIONS')

# Always use self.get_object() — never Post.objects.get(pk=pk)
# Direct get() bypasses has_object_permission() silently
```

```python
# Per-action permissions
def get_permissions(self):
    if self.action in ['list', 'retrieve']:
        return [AllowAny()]          # instances — ()
    return [IsAuthorOrReadOnly()]    # instances — ()

# vs class attribute — no ()
permission_classes = [IsAuthenticated, IsAuthorOrReadOnly]
```

---

## 12. JWT Authentication

```python
# config/settings/base.py
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

INSTALLED_APPS += [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
]
```

```
Access token:   15min, stateless, sent with every request
Refresh token:  7 days, blacklisted on logout

Login  → access + refresh
API    → Authorization: Bearer <access_token>
Expire → POST /token/refresh/ → new access + new refresh, old blacklisted
Logout → blacklist refresh token
```

```python
# Logout view
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            token = RefreshToken(request.data['refresh'])
            token.blacklist()
            return Response(status=204)
        except KeyError:
            return Response({'detail': 'Refresh token required.'}, status=400)
        except TokenError:
            return Response({'detail': 'Token invalid or expired.'}, status=400)
```

---

## 13. Middleware

```python
# Custom middleware pattern
class RequestTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response   # called once at startup

    def __call__(self, request):
        # pre-processing
        start = time.time()

        response = self.get_response(request)   # calls next middleware/view

        # post-processing
        duration = (time.time() - start) * 1000
        logger.info(f"[{request.method}] {request.path} — {duration:.2f}ms")
        return response

# Register in settings
MIDDLEWARE += ['apps.users.middleware.RequestTimingMiddleware']
# Put timing middleware first — captures total time including all other middleware
```

---

## 14. Signals

```python
# apps/blog/signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone
from .models import Post

@receiver(pre_save, sender=Post)
def set_published_at(sender, instance, **kwargs):
    if instance.status == Post.Status.PUBLISHED and instance.published_at is None:
        instance.published_at = timezone.now()

# apps/blog/apps.py — connect signals on startup
class BlogConfig(AppConfig):
    name = 'apps.blog'

    def ready(self):
        import apps.blog.signals  # noqa
```

### When to use signals
```
Use:     genuinely decoupled apps, reacting to third-party model events
Don't:   same-app logic, when you control both sides, when order matters
Rule:    if you can see the function call in the code — don't use a signal
```

---

## 15. URLs

```python
# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.users.urls')),
    path('api/', include('apps.blog.urls')),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns

# apps/users/urls.py
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', TokenObtainPairView.as_view(), name='auth-login'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', MeView.as_view(), name='auth-me'),
]
```

---

## 16. Key Commands

```bash
uv run python manage.py check                  # validate config
uv run python manage.py makemigrations         # generate migrations
uv run python manage.py migrate                # apply migrations
uv run python manage.py createsuperuser        # create admin user
uv run python manage.py shell                  # Django shell
uv run python manage.py runserver              # dev server
uv run python manage.py sqlmigrate app 0001    # show migration SQL
uv run python manage.py showmigrations         # migration status
uv run pytest                                  # run all tests
uv run pytest -v -k "test_login"              # filtered, verbose
```

---

## 17. Database Tables (fresh project)

```
django_content_type          → one row per model, powers permissions
auth_permission              → add/change/delete/view per model
auth_group                   → named permission groups
auth_group_permissions       → group ↔ permission junction
users_user                   → custom User model
users_user_groups            → user ↔ group junction
users_user_user_permissions  → user ↔ permission junction
django_admin_log             → admin action audit log
django_session               → browser session storage
django_migrations            → applied migration tracking
token_blacklist_outstandingtoken  → issued refresh tokens
token_blacklist_blacklistedtoken  → blacklisted refresh tokens
```

---

## 18. Checklist — Starting a New Django Project

```
[ ] uv init, python pin, add django
[ ] startproject config .
[ ] mkdir apps, move apps into it
[ ] Create settings/base.py, dev.py, prod.py
[ ] Fix BASE_DIR — 3 parents deep
[ ] Set SECRET_KEY from env, never hardcode
[ ] Create custom User model BEFORE first migration
[ ] Set AUTH_USER_MODEL in base.py
[ ] Register apps with full path (apps.users)
[ ] makemigrations + migrate
[ ] Set up .env, .gitignore
[ ] Install DRF + simplejwt + debug-toolbar
[ ] Register debug toolbar URLs in urls.py
[ ] git init + first commit
[ ] Write factories before writing tests
```