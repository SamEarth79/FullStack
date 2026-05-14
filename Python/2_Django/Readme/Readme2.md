# 02 — Models & Migrations

## What this covers
- Django ORM internals — how QuerySets work under the hood
- Model design — field types, relationships, constraints
- ManyToMany — auto-generated vs explicit junction tables
- Migration system — how Django tracks and applies schema changes
- Query optimization — select_related, prefetch_related, and proving it works

---

## ORM Internals — QuerySet Laziness

When you write:
```python
posts = Post.objects.filter(status='published')
```
**No SQL has run.** Django builds a `QuerySet` object — a description of the query, not the results.

The query hits the database only when the QuerySet is **evaluated**:

| Trigger | Evaluates? |
|---|---|
| `for post in posts:` | Yes — full fetch |
| `list(posts)` | Yes — full fetch |
| `posts[0]` | Yes — but does NOT populate cache |
| `posts.first()` | Yes — LIMIT 1 |
| `posts.count()` | Yes — COUNT query, no objects fetched |
| `posts.exists()` | Yes — EXISTS query, no objects fetched |
| `len(posts)` | Yes — full fetch |

### QuerySet Cache
Once evaluated, results are cached on the QuerySet object:
```python
qs = Post.objects.filter(status='published')
list(qs)   # hits DB, populates cache
list(qs)   # uses cache, no DB hit
qs[0]      # hits DB — slicing bypasses cache
qs[0]      # hits DB again — still bypasses cache
```

### Chaining — still one query
```python
qs = Post.objects.filter(status='published')      # no query
qs = qs.filter(author=user)                        # no query
qs = qs.select_related('author')                   # no query
posts = list(qs)                                   # ONE query combining all
```

### Inspecting generated SQL
```python
qs = Post.objects.filter(status='published').select_related('author')
print(qs.query)   # prints the SQL Django will generate
```

---

## Model Design

### Blog Schema

```
User (users app)
  ↓ ForeignKey (SET_NULL)
Post ←→ Tag (ManyToMany, auto junction: blog_post_tags)
  ↓ ForeignKey (CASCADE)
Comment → User (ForeignKey, SET_NULL)
```

### Field types used and why

| Field | Use case |
|---|---|
| `CharField(max_length=n)` | Short text. `max_length` required. Maps to `VARCHAR(n)`. |
| `TextField()` | Long unbounded text. No `max_length` at DB level. |
| `SlugField()` | CharField with slug validator. Use for URL-friendly identifiers. |
| `DateTimeField(auto_now_add=True)` | Set once at creation. Never updated. |
| `DateTimeField(auto_now=True)` | Updated on every `.save()`. |
| `DateTimeField(null=True, blank=True)` | Optional timestamp — e.g. `published_at` |
| `ForeignKey` | Many-to-one relationship. |
| `ManyToManyField` | Many-to-many. Django auto-creates junction table. |

### Field argument reference

| Argument | What it does |
|---|---|
| `unique=True` | Database UNIQUE constraint. No duplicates allowed. |
| `null=True` | Database allows NULL. Use for non-string optional fields. |
| `blank=True` | Form/serializer allows empty. Does NOT affect database. |
| `default=value` | Value used when field not provided at insert. |
| `on_delete=CASCADE` | Delete this row when related object is deleted. |
| `on_delete=SET_NULL` | Set FK to NULL when related object is deleted. Requires `null=True`. |
| `on_delete=PROTECT` | Prevent deletion of related object if this row exists. |
| `related_name='posts'` | Name of reverse accessor on the related model. |
| `related_name='+'` | Disable reverse accessor entirely. |

### `blank` vs `null` — the most confused pair
```python
# For strings — never null=True
name = models.CharField(max_length=100, blank=True)   # correct — empty string
name = models.CharField(max_length=100, null=True)    # wrong — two "nothing" values

# For non-strings — null=True for optional
published_at = models.DateTimeField(null=True, blank=True)   # correct
```

---

## The Blog Models

```python
# apps/blog/models.py
from django.db import models
from django.conf import settings


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(unique=True, max_length=50)

    class Meta:
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'
        ordering = ['name']

    def __str__(self):
        return self.name


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
        null=True,
        blank=True,
        related_name='posts',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='posts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Post'
        verbose_name_plural = 'Posts'
        ordering = ['-created_at']    # newest first by default

    def __str__(self):
        return self.title


class Comment(models.Model):
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comments',
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Comment'
        verbose_name_plural = 'Comments'
        ordering = ['created_at']

    def __str__(self):
        return self.body[:50]
```

### Key design decisions

**Why `Tag` is defined before `Post`?**
`Post` has a `ManyToManyField(Tag, ...)`. Defining `Tag` first means no forward reference string needed. Cleaner.

**Why `TextChoices` over boolean `is_draft`?**
A boolean breaks when requirements add `scheduled`, `archived`, `under_review`. `TextChoices` stores human-readable strings in the DB (`'draft'` not `0`) — readable in logs, psql, data migrations.

**Why `SET_NULL` on author, not `CASCADE`?**
If a user deletes their account, CASCADE would delete all their posts. On a blog platform, content has value independent of the author. `SET_NULL` keeps the post, sets author to NULL, show "deleted user" in UI.

**Why `ordering = ['-created_at']` on Post?**
The `-` prefix = descending. Newest posts first everywhere this model is queried, without specifying `.order_by()` every time.

---

## ManyToMany — Auto vs Explicit Junction Table

### Auto-generated (what we use for tags)
```python
tags = models.ManyToManyField(Tag, blank=True, related_name='posts')
```
Django creates `blog_post_tags` automatically:
```sql
CREATE TABLE blog_post_tags (
    id      INTEGER PRIMARY KEY,
    post_id INTEGER REFERENCES blog_post(id),
    tag_id  INTEGER REFERENCES blog_tag(id)
);
```

### Explicit `through` model (when you need extra data on the relationship)
```python
class PostTag(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

class Post(models.Model):
    tags = models.ManyToManyField(Tag, through='PostTag', related_name='posts')
```
Use `through` when you need metadata on the relationship itself.

---

## Related Managers & Reverse Accessors

### Forward direction — field name
```python
post.tags.all()       # 'tags' is the field name you declared
post.tags.add(tag)
post.tags.remove(tag)
```

### Reverse direction — related_name
```python
# related_name='posts' on Tag's side
tag.posts.all()       # all posts with this tag

# related_name='comments' on Post's side
post.comments.all()   # all comments on this post
```
Without `related_name`, Django generates `tag.post_set` — ugly and leaks internals.

### When `related_name` is required (not optional)
Two ForeignKeys pointing to the same model from the same model:
```python
class Post(models.Model):
    author = models.ForeignKey(User, related_name='authored_posts', ...)
    editor = models.ForeignKey(User, related_name='edited_posts', ...)
    # Without related_name both would try to create 'post_set' on User — clash
```
Django raises `fields.E304` if you forget.

---

## Query Optimization

### The N+1 problem
```python
posts = Post.objects.all()        # 1 query
for post in posts:
    print(post.author.email)      # 1 query PER post — N+1
```
100 posts = 101 queries.

### Fix with select_related (ForeignKey / OneToOne)
```python
posts = Post.objects.select_related('author')
# Generates a single LEFT OUTER JOIN
# Why LEFT OUTER JOIN? author is null=True — INNER JOIN would drop posts with no author
```

### Fix with prefetch_related (ManyToMany / reverse FK)
```python
posts = Post.objects.prefetch_related('tags', 'comments')
# Query 1: fetch all posts
# Query 2: SELECT ... WHERE post_id IN (1, 2, 3, ...) for tags
# Query 3: SELECT ... WHERE post_id IN (1, 2, 3, ...) for comments
# Python stitches results in memory
```
Always 3 queries total regardless of how many posts — never N+1.

### When to use annotate instead of prefetch
If you only need a **count**, don't fetch all related objects into memory:
```python
# Wrong — fetches all comment objects just to count them
posts = Post.objects.prefetch_related('comments')
count = len(post.comments.all())

# Right — database does the counting, returns an integer
from django.db.models import Count
posts = Post.objects.annotate(comment_count=Count('comments'))
count = post.comment_count
```

### Verifying query count in shell
```python
from django.db import connection, reset_queries
from django.conf import settings

settings.DEBUG = True
reset_queries()

# ... your query here ...

print(f"Total queries: {len(connection.queries)}")
for q in connection.queries:
    print(q['sql'])
```

### The SQL proof
```sql
-- select_related('author') generates:
SELECT blog_post.*, users_user.*
FROM blog_post
LEFT OUTER JOIN users_user ON (blog_post.author_id = users_user.id)
WHERE blog_post.slug = 'my-post'

-- prefetch_related('tags') generates:
SELECT blog_tag.*, blog_post_tags.post_id
FROM blog_tag
INNER JOIN blog_post_tags ON (blog_tag.id = blog_post_tags.tag_id)
WHERE blog_post_tags.post_id IN (1, 2, 3)   -- all fetched post IDs at once
```

---

## Migration System

### How it works
1. `makemigrations` — reads your models, compares to last known state, generates a migration file
2. `migrate` — reads `django_migrations` table, runs any migration files not recorded there
3. Each migration file is a Python class with `dependencies` and `operations`

### Migration dependency order
Django resolves dependencies automatically. For our app:
```
contenttypes → auth → users → blog → admin → sessions
```
`blog` depends on `users` because `Post.author` is a FK to `AUTH_USER_MODEL`.

### Key commands
```bash
uv run python manage.py makemigrations          # generate migrations
uv run python manage.py migrate                 # apply migrations
uv run python manage.py migrate --fake          # mark as applied without running SQL
uv run python manage.py showmigrations          # show applied/unapplied state
uv run python manage.py sqlmigrate blog 0001    # show SQL a migration will run
```

### Reading a migration file
```python
class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),  # must run auth up to 0012 first
    ]
    operations = [
        migrations.CreateModel(name='Post', fields=[...]),
        # ManyToMany junction tables are created implicitly — not explicit here
    ]
```

### Tables Django creates automatically
ManyToManyField junction tables do not appear as `CreateModel` in the migration file — Django creates them implicitly. But they exist in the database:
```python
# Verify in shell
from django.db import connection
connection.introspection.table_names()
# Shows blog_post_tags even though it's not in the migration file
```

---

## Always Reference User Indirectly

```python
# In models — settings reference (works at class definition time)
from django.conf import settings
author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

# In views/logic — get_user_model()
from django.contrib.auth import get_user_model
User = get_user_model()

# Never do this — tight coupling
from apps.users.models import User   # breaks if AUTH_USER_MODEL changes
```

---

## Database Tables After Setup

```
blog_tag                — Tag model
blog_post               — Post model
blog_post_tags          — Auto junction table for Post ↔ Tag ManyToMany
blog_comment            — Comment model
users_user              — Custom User model
users_user_groups       — Junction: User ↔ Group
users_user_permissions  — Junction: User ↔ Permission
auth_group              — Groups
auth_group_permissions  — Junction: Group ↔ Permission
auth_permission         — All model permissions
django_content_type     — One row per model. Powers permissions + generic relations.
django_migrations       — Applied migration log
django_admin_log        — Admin action audit log
django_session          — Browser session storage
```