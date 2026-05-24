# Databases Mastery — Senior Engineer Reference

---

## Module 1 — Field Type Decisions (Postgres)

| Use case | Field type | Reason |
|---|---|---|
| PK, internal table | `BIGSERIAL` | Fast, sequential, no exposure |
| PK, exposed externally / distributed | `UUID` (v7) | Non-guessable, collision-safe, index-friendly |
| Owned config, dynamic keys | `JSONB` | Flexible, queried together |
| Independent relational data | Normalized table | Relations, type safety |
| Money | `NUMERIC(10,2)` or `INTEGER` cents | Exact decimal |
| Never money | ~~`FLOAT`~~ | Binary precision loss |
| Enum values | `TextChoices` + `CHECK` constraint | App readable + DB enforced |
| Fixed-length codes | `CHAR(n)` | e.g. `CHAR(2)` country code |
| Variable text, no length meaning | `TEXT` | Same as VARCHAR internally |
| Timestamps | `TIMESTAMPTZ` | UTC storage, timezone-aware |

### Key Notes

**UUID v4 vs v7**
- v4 = random → index fragmentation at scale
- v7 = time-ordered + random → sequential inserts, healthy index

```sql
-- v4 (avoid for PKs at scale)
id UUID DEFAULT gen_random_uuid() PRIMARY KEY

-- v7 (preferred)
CREATE EXTENSION IF NOT EXISTS pg_uuidv7;
id UUID DEFAULT uuid_generate_v7() PRIMARY KEY
```

**JSONB vs Normalized table**
- JSONB: data owned by parent, queried together, schema varies
- Normalized: independent existence, needs relations, needs type enforcement
- Never use EAV (`key TEXT, value TEXT`) — no types, no constraints, ugly queries

**Money — never FLOAT**
```sql
-- FLOAT breaks
SELECT 0.1::FLOAT + 0.2::FLOAT = 0.3::FLOAT;  -- FALSE

-- NUMERIC is exact
SELECT 0.1::NUMERIC + 0.2::NUMERIC = 0.3::NUMERIC;  -- TRUE

-- Best: store as integer cents
total_cents INTEGER  -- 9999 = $99.99
```

**Enum — Django TextChoices + CHECK constraint**
```python
class UserStatus(models.TextChoices):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    SUSPENDED = 'suspended'
```
```sql
-- Add via RunSQL migration
ALTER TABLE users ADD CONSTRAINT valid_status 
CHECK (status IN ('active', 'inactive', 'suspended'));
```

**Timestamps — always TIMESTAMPTZ**
```python
# settings.py
USE_TZ = True  # verify this is True
```

---

## Module 2 — Indexing Strategy

| Scenario | Action |
|---|---|
| Column in WHERE/JOIN on large table | Add B-tree index |
| Low cardinality column (`status`, `boolean`) | Partial index or skip |
| JSONB queries | GIN index |
| Multiple columns in WHERE | Composite index, most selective first |
| Foreign key column | Always index |
| Write-heavy table | Minimize indexes |
| Production table | Always `CONCURRENTLY` |

### Index Types

| Type | Use case |
|---|---|
| B-tree (default) | `=`, `<`, `>`, `BETWEEN`, `ORDER BY` |
| GIN | Array contains, JSONB keys, full-text search |
| Hash | Equality only — B-tree usually better |
| Partial | Index subset of rows |
| Composite | Multiple columns in WHERE |

### Key Notes

**Composite index — column order matters**
```sql
CREATE INDEX idx_orders_user_status ON orders (user_id, status);

-- Uses index ✓
WHERE user_id = 'abc' AND status = 'pending'
WHERE user_id = 'abc'

-- Does NOT use index ✗
WHERE status = 'pending'
```

**Partial index for low cardinality**
```sql
-- Don't index status directly (4 values, low cardinality)
-- Index only the rows you query
CREATE INDEX idx_orders_pending ON orders (user_id) 
WHERE status = 'pending';
```

**GIN for JSONB**
```sql
CREATE INDEX idx_users_preferences ON users USING GIN (preferences);
SELECT * FROM users WHERE preferences @> '{"notifications": true}';
```

**Always CONCURRENTLY in production**
```python
class Migration(migrations.Migration):
    atomic = False  # required for CONCURRENTLY

    operations = [
        migrations.RunSQL(
            sql="CREATE INDEX CONCURRENTLY idx_posts_user_id ON posts (user_id)",
            reverse_sql="DROP INDEX CONCURRENTLY idx_posts_user_id",
        )
    ]
```

**Detecting missing indexes**
```sql
EXPLAIN ANALYZE SELECT * FROM orders WHERE user_id = 'abc';
-- Look for: Seq Scan = bad on large table
-- Look for: Index Scan = good
```

---

## Module 3 — Schema Design Decisions

| Scenario | Decision | Reason |
|---|---|---|
| Likes on multiple entity types | Two tables, not polymorphic | FK integrity, clean indexes |
| Tags (shared across entities) | Normalized + junction table | Independent existence, reverse lookup |
| Junction table PK | Composite PK, no `id` | Free unique index, no duplicates |
| Soft delete | `deleted_at` + custom manager | FK integrity, restore support |
| Hierarchical data (shallow) | Self-referential FK | Simple, ORM friendly |
| Hierarchical data (deep/large) | `ltree` extension | Recursive query performance |
| Polymorphic relations | Avoid | No FK enforcement, messy queries |

### Key Notes

**Soft delete pattern**
```python
class PostManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)

class Post(models.Model):
    deleted_at = models.DateTimeField(null=True, blank=True)
    objects = PostManager()       # excludes deleted
    all_objects = models.Manager()  # includes deleted
```
```sql
-- Partial index — deleted posts don't pollute active queries
CREATE INDEX idx_posts_active ON posts (user_id, created_at) 
WHERE deleted_at IS NULL;
```

**Self-referential FK (nested comments)**
```sql
CREATE TABLE comments (
    id UUID PRIMARY KEY,
    parent_id UUID REFERENCES comments(id),  -- NULL = top level
    body TEXT
);
```
```sql
-- Recursive query to fetch full thread
WITH RECURSIVE comment_tree AS (
    SELECT id, parent_id, body, 0 AS depth
    FROM comments WHERE post_id = 'abc' AND parent_id IS NULL
    UNION ALL
    SELECT c.id, c.parent_id, c.body, ct.depth + 1
    FROM comments c
    JOIN comment_tree ct ON c.parent_id = ct.id
)
SELECT * FROM comment_tree ORDER BY depth;
```

**Junction table — composite PK**
```sql
CREATE TABLE post_tags (
    post_id UUID REFERENCES posts(id),
    tag_id UUID REFERENCES tags(id),
    PRIMARY KEY (post_id, tag_id)  -- no separate id needed
);
```

---

## Module 4 — Query Patterns That Matter

| Scenario | Pattern | Key point |
|---|---|---|
| Concurrent update on shared resource | `select_for_update()` | Must be in `transaction.atomic()` |
| Insert or update | `update_or_create()` / `ON CONFLICT` | Needs unique constraint on lookup field |
| Bulk insert | `bulk_create(batch_size=N)` | Single query per batch |
| Bulk update | `.update()` on queryset | Never loop + save |
| Large dataset pagination | Cursor/keyset | Offset kills at scale |
| Admin/small data pagination | Offset | Fine, page numbers work |
| Per-group latest/first row | `DISTINCT ON` / Subquery | Avoid N+1 |

### Key Notes

**SELECT FOR UPDATE — race condition prevention**
```python
from django.db import transaction

with transaction.atomic():
    event = Event.objects.select_for_update().get(id=event_id)
    if event.available_seats <= 0:
        raise ValueError("No seats available")
    event.available_seats -= 1
    event.save()
```

**Upsert**
```python
User.objects.update_or_create(
    google_id=google_id,           # lookup field
    defaults={'token': new_token}  # fields to update
)
```
```sql
INSERT INTO users (google_id, token) VALUES ('abc', 'token123')
ON CONFLICT (google_id) DO UPDATE SET token = EXCLUDED.token;
```

**Bulk operations**
```python
# Bulk insert
posts = [Post(**row) for row in csv_rows]
Post.objects.bulk_create(posts, batch_size=500)

# Bulk update — single query
Post.objects.filter(status='published', created_at__lt=cutoff).update(status='archived')
```

**Cursor pagination vs Offset**
```python
# Offset — slow at scale (scans + discards N rows)
Post.objects.all().order_by('-created_at')[page * size:(page + 1) * size]

# Cursor — always fast, no duplicates
Post.objects.filter(
    created_at__lt=last_seen_created_at
).order_by('-created_at')[:20]
```

**Per-group latest row**
```sql
SELECT DISTINCT ON (user_id) id, user_id, title, created_at
FROM posts ORDER BY user_id, created_at DESC;
```

---

## Module 5 — Migrations in Production

| Operation | Safe? | Pattern |
|---|---|---|
| Add nullable column | ✅ Always safe | Direct migration |
| Add non-nullable column | ⚠️ Dangerous | 3-step: nullable → backfill → constrain |
| Add index | ⚠️ Locks table | `CREATE INDEX CONCURRENTLY` + `atomic=False` |
| Rename column | ⚠️ Breaks deploys | Dual-write → backfill → switch → cleanup |
| Delete column | ⚠️ Order matters | Remove from code first, drop column second |
| Backfill large table | ⚠️ Lock risk | Always batch, never single query |
| Out of sync schema | Use sparingly | `--fake` migration |

### Key Notes

**Adding non-nullable column — 3 steps**

Step 1 — add nullable:
```python
migrations.AddField(model_name='post', field=models.TextField(null=True), name='summary')
```

Step 2 — backfill in batches:
```python
def backfill_summary(apps, schema_editor):
    Post = apps.get_model('blog', 'Post')
    while True:
        ids = list(Post.objects.filter(summary__isnull=True).values_list('id', flat=True)[:1000])
        if not ids:
            break
        Post.objects.filter(id__in=ids).update(summary='')
```

Step 3 — add constraint:
```python
migrations.AlterField(model_name='post', field=models.TextField(null=False, default=''), name='summary')
```

**Rename column — 5 steps**
1. Add new column (nullable)
2. Deploy: dual-write to both old + new columns
3. Backfill new column from old
4. Deploy: read from new column
5. Drop old column

**Delete column — correct order**
1. Remove column from all Django model/serializer/query code
2. Deploy code
3. Run migration to drop column

**Fake migration**
```bash
python manage.py migrate --fake blog 0012
python manage.py migrate --fake-initial
```

---

## Module 6 — MongoDB Applied

| Decision | Rule |
|---|---|
| Postgres vs Mongo | Postgres default. Mongo when document = natural unit, schema evolves fast, no complex relations |
| Embed vs Reference | Embed: bounded, always read together, owned. Reference: unbounded, independent, queried separately |
| Tags in Mongo | Embed as array — bounded, owned by post |
| Comments in Mongo | Reference — unbounded, queried separately |
| Aggregation | Pipeline stages — unwind arrays, group, sort, limit |
| `$lookup` | Use sparingly — heavy use = wrong schema |
| Transactions | Supported but expensive — use Postgres if needed constantly |
| Indexes | Same intuition as Postgres — fields in WHERE/sort/lookup |

### Embed vs Reference Decision

| Question | Embed | Reference |
|---|---|---|
| Read together always? | ✅ | |
| Unbounded growth? | | ✅ |
| Independent existence needed? | | ✅ |
| 1-to-few (< ~20 items)? | ✅ | |
| 1-to-many (hundreds+)? | | ✅ |
| Queried separately? | | ✅ |

### Key Notes

**MongoEngine models**
```python
from mongoengine import Document, EmbeddedDocument, fields

class UserPreferences(EmbeddedDocument):
    theme = fields.StringField(default='light')
    notifications = fields.BooleanField(default=True)

class Post(Document):
    user = fields.ReferenceField('User', required=True)
    title = fields.StringField(required=True)
    tags = fields.ListField(fields.StringField())  # embed — bounded
    created_at = fields.DateTimeField()
    
    meta = {
        'collection': 'posts',
        'indexes': ['user', 'tags', '-created_at']
    }
```

**Aggregation pipeline**
```python
pipeline = [
    {"$unwind": "$tags"},
    {"$group": {"_id": "$tags", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}},
    {"$limit": 5}
]
result = Post.objects.aggregate(pipeline)
```

---

## Module 7 — Decision Framework

### Postgres vs MongoDB

```
Do entities relate to each other?           → Postgres
Need transactions across entities?          → Postgres
Data integrity critical?                    → Postgres
Document is the natural read unit?          → Mongo
Schema varies wildly per row?               → Mongo
Write-heavy, schema evolving, early stage?  → Mongo
Not sure?                                   → Postgres
```

### Multi-tenant Patterns

| Pattern | How | When |
|---|---|---|
| Row-level (shared schema) | `tenant_id` on every table | Startups, cost-sensitive |
| Separate schema per tenant | Postgres schemas | Mid-scale, compliance |
| Separate DB per tenant | Multiple DB configs | Enterprise, data residency |

**Row-level with auto-filter middleware:**
```python
class TenantMiddleware:
    def __call__(self, request):
        tenant = Tenant.objects.get(domain=request.get_host())
        request.tenant = tenant
        set_current_tenant(tenant)
        return self.get_response(request)

class TenantManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(tenant=get_current_tenant())
```

### Connection Pooling — PgBouncer

```yaml
services:
  pgbouncer:
    image: edoburu/pgbouncer
    environment:
      DB_HOST: postgres
      POOL_MODE: transaction      # always transaction mode with Django
      MAX_CLIENT_CONN: 1000
      DEFAULT_POOL_SIZE: 20
```

```python
# Django — point to PgBouncer, not Postgres directly
DATABASES = {
    'default': {
        'HOST': 'pgbouncer',
        'CONN_MAX_AGE': 0,  # let pgbouncer handle pooling
    }
}
```

### Read Replicas

```python
DATABASES = {
    'default': {'HOST': 'postgres-primary'},  # writes
    'replica': {'HOST': 'postgres-replica'},  # reads
}

class PrimaryReplicaRouter:
    def db_for_read(self, model, **hints):
        return 'replica'
    def db_for_write(self, model, **hints):
        return 'default'
    def allow_migrate(self, db, app_label, **hints):
        return db == 'default'

DATABASE_ROUTERS = ['myapp.routers.PrimaryReplicaRouter']

# Force primary read when freshness critical
Post.objects.using('default').get(id=post_id)
```

---

*Generated from 7-Week Senior Engineer Mastery Plan — Databases Module*