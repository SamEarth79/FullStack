# 03 — Views, Serializers & Authentication

## What this covers
- Serializers — internals, validation, read/write asymmetry, nested relations
- Views — APIView, Generic Views, ViewSets — when to use each
- Permissions — model-level, object-level, per-action
- JWT Authentication — theory, access/refresh tokens, blacklisting
- Full auth flow — register, login, refresh, logout

---

## Serializers

### What a serializer actually does
Three distinct jobs — not just "model to JSON":

```
1. Deserialization  → take raw JSON, validate it, convert to Python objects
2. Validation       → field rules, cross-field rules, business rules
3. Serialization    → take Python objects, convert to JSON-serializable data
```

### How validation works internally
```python
serializer = PostCreateSerializer(data=request.data)
serializer.is_valid(raise_exception=True)
# 1. Runs field-level type checks (max_length, EmailField format, etc.)
# 2. Runs validate_<fieldname>() methods
# 3. Runs validate() cross-field method
# 4. Populates serializer.validated_data if all pass
# raise_exception=True throws ValidationError automatically on failure
```

### Serializer vs ModelSerializer
```python
# Plain Serializer — full control, more verbose
class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

# ModelSerializer — auto-generates fields from model
class RegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'username', 'password']
    # DRF inspects User._meta.fields and maps Django fields to DRF fields
    # Also auto-generates validators (unique=True → UniquenessValidator)
```

### Field arguments
| Argument | What it does |
|---|---|
| `read_only=True` | Output only — ignored on input. Use for ids, timestamps. |
| `write_only=True` | Input only — never in response. Use for passwords. |
| `required=False` | Field is optional on input. |
| `allow_blank=True` | Allows empty string. |
| `source='author.email'` | Read from nested attribute. |
| `min_length`, `max_length` | CharField constraints. |

### Three validation layers
```python
# Layer 1 — field declaration (automatic)
password = serializers.CharField(min_length=8)

# Layer 2 — custom field-level
def validate_email(self, value):
    if value.endswith('@tempmail.com'):
        raise serializers.ValidationError("Temporary emails not allowed.")
    return value   # must return value

# Layer 3 — cross-field
def validate(self, data):
    if data['password'] != data['confirm_password']:
        raise serializers.ValidationError("Passwords do not match.")
    return data   # must return data
```

### `create()` and `update()`
```python
# save() calls create() if no instance, update() if instance provided
serializer = PostCreateSerializer(data=request.data)
serializer.save()   # → calls create()

serializer = PostCreateSerializer(instance=post, data=request.data)
serializer.save()   # → calls update()
```

### `fields = '__all__'` is a security risk
```python
# Wrong — exposes is_staff, is_superuser, password, everything
class Meta:
    fields = '__all__'

# Right — always list fields explicitly
class Meta:
    fields = ['id', 'email', 'username']
```

---

## Related Fields — How serializers handle relationships

### Default — Primary Key
```python
class PostSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ['id', 'title', 'author', 'tags']
# Output: {"author": 3, "tags": [1, 2]}
```

### Nested Serializer — full object
```python
class PostSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)
# Output: {"author": {"id": 3, "email": "..."}, "tags": [...]}
```

### StringRelatedField — calls `__str__`
```python
author = serializers.StringRelatedField()
# Output: {"author": "samarth@abc.com"}
```

### PrimaryKeyRelatedField — ID input, resolves to objects
```python
tags = serializers.PrimaryKeyRelatedField(
    many=True,
    queryset=Tag.objects.all(),
    required=False,
)
# Client sends: {"tags": [1, 2]}
# DRF resolves: validated_data['tags'] = [<Tag: Django>, <Tag: Python>]
# Invalid ID → automatic validation error
```

---

## Read/Write Asymmetry — The Right Pattern

Different serializers per use case. Never one god serializer.

```python
class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug']


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username']


class PostSerializer(serializers.ModelSerializer):
    """List — no body, nested objects for reading."""
    author = AuthorSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = ['id', 'title', 'slug', 'author', 'status',
                  'tags', 'published_at', 'created_at']


class PostDetailSerializer(serializers.ModelSerializer):
    """Single post — full fields."""
    author = AuthorSerializer(read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = ['id', 'title', 'slug', 'body', 'author', 'status',
                  'tags', 'published_at', 'created_at', 'updated_at']


class PostCreateSerializer(serializers.ModelSerializer):
    """Create/update — tag IDs input, author injected server-side."""
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        required=False,
    )

    class Meta:
        model = Post
        fields = ['title', 'slug', 'body', 'status', 'tags']
        # author NOT in fields — injected in perform_create

    def create(self, validated_data):
        tags = validated_data.pop('tags', [])        # remove M2M before create
        post = Post.objects.create(**validated_data)  # create without tags
        post.tags.set(tags)                           # set M2M after
        return post

    def update(self, instance, validated_data):
        tags = validated_data.pop('tags', None)
        post = super().update(instance, validated_data)
        if tags is not None:
            post.tags.set(tags)
        return post


class CommentSerializer(serializers.ModelSerializer):
    author = AuthorSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ['id', 'author', 'body', 'created_at']


class CommentCreateSerializer(serializers.ModelSerializer):
    """Create — just body. Post and author injected server-side."""
    class Meta:
        model = Comment
        fields = ['body']

    def create(self, validated_data):
        return Comment.objects.create(**validated_data)
```

### Why ManyToMany can't be set in `create(**kwargs)`
```python
# Wrong — raises error, object must exist first
Post.objects.create(tags=[tag1, tag2])

# Right — create first, set M2M after
post = Post.objects.create(**validated_data)
post.tags.set(tags)
```

### Three sources of data
```
Client sends:     fields the client controls — title, body, status, tag IDs
URL provides:     object identifiers — post slug, parent resource ID
Server injects:   identity/ownership — author always from request.user
```

---

## Views — Three Layers

### Layer responsibilities
```
Serializer   → data validation + shape
View         → orchestration (thin)
Model        → business logic (domain rules)
```

### Layer 1 — APIView
Base class. Methods map directly to HTTP verbs. Maximum control.

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            token = RefreshToken(request.data['refresh'])
            token.blacklist()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except KeyError:
            return Response({'detail': 'Refresh token required.'}, status=400)
        except TokenError:
            return Response({'detail': 'Token invalid or expired.'}, status=400)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
```

**Use APIView for:** auth, search, custom operations, anything non-standard.

---

### Layer 2 — Generic Views
Pre-built views for standard patterns. Provide queryset + serializer, DRF handles the rest.

```python
from rest_framework import generics, permissions

# GET /api/posts/ and POST /api/posts/
class PostListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        return Post.objects.select_related('author')\
                           .prefetch_related('tags')\
                           .filter(status=Post.Status.PUBLISHED)

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return PostCreateSerializer
        return PostSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


# GET/PUT/PATCH/DELETE /api/posts/{slug}/
class PostDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PostDetailSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return Post.objects.select_related('author')\
                           .prefetch_related('tags', 'comments')
```

| Generic Class | Methods | Use case |
|---|---|---|
| `ListAPIView` | GET | List all |
| `CreateAPIView` | POST | Create |
| `RetrieveAPIView` | GET | Single object |
| `UpdateAPIView` | PUT, PATCH | Update |
| `DestroyAPIView` | DELETE | Delete |
| `ListCreateAPIView` | GET, POST | List + create |
| `RetrieveUpdateDestroyAPIView` | GET, PUT, PATCH, DELETE | Full object ops |

**Use generics for:** simple resources with 1-2 operations, operations with very different logic.

---

### Layer 3 — ViewSets
Combines all operations. Router auto-generates URLs.

```python
from rest_framework import viewsets
from rest_framework.decorators import action
from django.db.models import Q

class PostViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthorOrReadOnly]
    lookup_field = 'slug'

    def get_queryset(self):
        user = self.request.user
        if self.action in ['list', 'retrieve']:
            if user.is_authenticated:
                return Post.objects.filter(
                    Q(status=Post.Status.PUBLISHED) | Q(author=user)
                ).select_related('author').prefetch_related('tags', 'comments')
            return Post.objects.filter(
                status=Post.Status.PUBLISHED
            ).select_related('author').prefetch_related('tags', 'comments')
        return Post.objects.select_related('author').prefetch_related('tags', 'comments')

    def get_serializer_class(self):
        if self.action == 'list':
            return PostSerializer
        elif self.action == 'retrieve':
            return PostDetailSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return PostCreateSerializer
        return PostSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    # POST /api/posts/{slug}/publish/
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def publish(self, request, slug=None):
        post = self.get_object()
        post.status = Post.Status.PUBLISHED
        post.published_at = timezone.now()
        post.save()
        return Response(PostSerializer(post).data)

    # GET /api/posts/my-posts/
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_posts(self, request):
        posts = Post.objects.filter(author=request.user)\
                            .select_related('author')\
                            .prefetch_related('tags')
        return Response(PostSerializer(posts, many=True).data)
```

```python
# apps/blog/urls.py
from rest_framework.routers import DefaultRouter
from .views import PostViewSet

router = DefaultRouter()
router.register('posts', PostViewSet, basename='post')
# basename required when ViewSet uses get_queryset() not class-level queryset attribute

urlpatterns = router.urls
```

**Router generates automatically:**
```
GET     /api/posts/                  → list
POST    /api/posts/                  → create
GET     /api/posts/{slug}/           → retrieve
PUT     /api/posts/{slug}/           → update
PATCH   /api/posts/{slug}/           → partial_update
DELETE  /api/posts/{slug}/           → destroy
POST    /api/posts/{slug}/publish/   → publish (detail=True custom action)
GET     /api/posts/my-posts/         → my_posts (detail=False custom action)
```

**Use ViewSets for:** resources with 3+ operations, standard CRUD + custom actions.

---

### When to use which
| Situation | Use |
|---|---|
| Auth, search, custom operations | `APIView` |
| 1-2 operations, very different logic | Generic views |
| Full resource CRUD + custom actions | `ViewSet` |

---

### `perform_create` vs `perform_update`
```python
def perform_create(self, serializer):
    serializer.save(author=self.request.user)
    # Merges kwargs into validated_data before calling create()
    # Client never sends author — always injected from session

def perform_update(self, serializer):
    serializer.save()
    # Default — only override if injecting extra data on update
    # e.g. serializer.save(last_edited_by=self.request.user)
```

### `basename` — when it's required
```python
# Not needed — router infers from class-level queryset
class PostViewSet(viewsets.ModelViewSet):
    queryset = Post.objects.all()   # router reads model from here

# Required — router can't inspect a method
class PostViewSet(viewsets.ModelViewSet):
    def get_queryset(self):         # router can't read this
        return Post.objects.filter(...)

router.register('posts', PostViewSet, basename='post')
# Generates URL names: 'post-list', 'post-detail'
```

---

## Permissions

### Model-level vs Object-level
```
has_permission()        → Can this user do this action on ANY object?
has_object_permission() → Can this user do this action on THIS object?
```

```python
# apps/blog/permissions.py
from rest_framework import permissions

class IsAuthorOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(obj, 'author', None) == request.user
        # getattr with None — safe if model has no 'author' field
```

### `has_object_permission` only runs via `self.get_object()`
```python
# Wrong — bypasses object-level permissions
post = Post.objects.get(pk=pk)

# Right — triggers has_object_permission()
post = self.get_object()
```

### Per-action permissions
```python
def get_permissions(self):
    if self.action in ['list', 'retrieve']:
        return [permissions.AllowAny()]
    elif self.action == 'create':
        return [permissions.IsAuthenticated()]
    else:
        return [IsAuthorOrReadOnly()]

# Class attribute — no ()
permission_classes = [IsAuthenticated, IsAuthorOrReadOnly]

# get_permissions() return — always ()
return [IsAuthenticated(), IsAuthorOrReadOnly()]
```

### Permission check order
```
Request
  ↓ authentication_classes  → sets request.user
  ↓ has_permission()        → model-level, every request
  ↓ view logic
  ↓ self.get_object()
  ↓ has_object_permission() → object-level, only when get_object() called
  ↓ response
```

---

## JWT Authentication

### Token anatomy
```
HEADER.PAYLOAD.SIGNATURE

Payload claims:
  user_id  → who this token belongs to
  exp      → expiry unix timestamp
  iat      → issued at
  jti      → unique token ID — used for blacklisting
```

Payloads are base64 encoded — NOT encrypted. Anyone can read them.
Never store passwords, PII, or sensitive data in JWT claims.

### Signing — Symmetric vs Asymmetric
```
HS256 (symmetric):   one secret — signs AND verifies
                     use for single-service backends

RS256 (asymmetric):  private key signs, public key verifies
                     use when multiple services need to verify tokens
```

### How verification works
```
1. Re-compute signature from received header + payload
2. Compare with received signature — mismatch → reject
3. Check exp — expired → reject
4. Check jti against blacklist — blacklisted → reject
5. Fetch user from DB using user_id claim
6. Check user.is_active — inactive → reject
7. Set request.user
```

### Can you tamper with the payload?
No. Changing any byte in the payload produces a different signature.
Without the secret key, the attacker cannot forge a valid signature.

### Access + Refresh architecture
```
Access token:   15 minutes, stateless, sent with every API request
Refresh token:  7 days, blacklisted on logout, sent only to /token/refresh/

Login  → access (15min) + refresh (7days)
API    → Authorization: Bearer <access_token> — no DB lookup
Expire → POST /token/refresh/ → new access + new refresh, old refresh blacklisted
Logout → blacklist refresh token, access expires naturally in ≤15min
```

### simplejwt settings
```python
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,      # new refresh token on every refresh call
    'BLACKLIST_AFTER_ROTATION': True,   # old refresh token immediately blacklisted
    'AUTH_HEADER_TYPES': ('Bearer',),
}
```

### Blacklist tables
```
token_blacklist_outstandingtoken  → every issued refresh token tracked here
token_blacklist_blacklistedtoken  → blacklisted tokens reference outstanding tokens
```

---

## Full Auth Implementation

### URLs
```python
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

`TokenObtainPairView` reads `USERNAME_FIELD` from your User model automatically.
Our `USERNAME_FIELD = 'email'` so it expects `email + password` in the request body.

### Root URL config
```python
# config/urls.py
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.users.urls')),
    path('api/', include('apps.blog.urls')),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
```

Debug toolbar URLs must be registered or it raises `NoReverseMatch: 'djdt' is not a registered namespace`.

---

## `create_user` vs `create` — non-negotiable

```python
# Wrong — stores plain text password in database
User.objects.create(email='a@b.com', password='plaintext')

# Right — hashes with PBKDF2-SHA256 + random salt
User.objects.create_user(email='a@b.com', password='plaintext')

# Updating password — always use set_password()
user.set_password('newpassword')
user.save()
```

---

## API Endpoints Reference

```
POST   /api/auth/register/     → create account, returns tokens
POST   /api/auth/login/        → returns access + refresh tokens
POST   /api/auth/refresh/      → exchange refresh for new access token
POST   /api/auth/logout/       → blacklists refresh token
GET    /api/auth/me/           → current user profile (auth required)

GET    /api/posts/             → list posts (published + own drafts if auth)
POST   /api/posts/             → create post (auth required)
GET    /api/posts/{slug}/      → single post
PUT    /api/posts/{slug}/      → full update (author only)
PATCH  /api/posts/{slug}/      → partial update (author only)
DELETE /api/posts/{slug}/      → delete (author only)
```

---

## How many serializers per model?

One per use case, not one per model:

| Serializer | Purpose |
|---|---|
| `RegisterSerializer` | Create account |
| `UserSerializer` | Read profile |
| `PostSerializer` | List posts — no body, nested objects |
| `PostDetailSerializer` | Single post — full fields |
| `PostCreateSerializer` | Create/update — tag IDs input |
| `CommentSerializer` | Read comment — nested author |
| `CommentCreateSerializer` | Create comment — body only |