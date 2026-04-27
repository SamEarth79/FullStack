# FastAPI + Postgres — Docker Compose Setup

## What This Is

The same FastAPI + Postgres setup from the bare Docker experiment, now managed with Docker Compose. Compose automates everything that was done manually — creating networks, passing environment variables, managing start order, handling volumes — from a single YAML file.

---

## Project Structure

```
.
├── docker-compose.yml
├── env/
│   ├── backend.env
│   └── db.env
└── backend/
    ├── app.py
    ├── requirements.txt
    └── Dockerfile.backend
```

---

## Files

### `env/db.env`
```
POSTGRES_DB=my_db
POSTGRES_USER=myuser
POSTGRES_PASSWORD=secret
```

### `env/backend.env`
```
DB_HOST=postgres
DB_NAME=my_db
DB_USER=myuser
DB_PASSWORD=secret
```

`DB_HOST=postgres` is the service name from `docker-compose.yml`. Compose puts all services on the same network and Docker DNS resolves service names to container IPs automatically.

Note: do not use quotes around values in `.env` files. Docker reads them literally — `"myuser"` with quotes becomes the value, not `myuser`.

### `backend/Dockerfile.backend`
```dockerfile
FROM python:3.12-slim

RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `docker-compose.yml`
```yaml
services:
  postgres:
    image: postgres:16
    env_file: env/db.env
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U myuser -d my_db"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: backend/
      dockerfile: Dockerfile.backend
    ports:
      - "8000:8000"
    env_file: env/backend.env
    volumes:
      - ./backend:/app
    command: uvicorn app:app --host 0.0.0.0 --port 8000 --reload
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  postgres_data:
```

---

## How to Run It

### Start everything
```bash
docker-compose up
```

### Start in background
```bash
docker-compose up -d
```

### Rebuild images and start
```bash
docker-compose up --build
```

Use `--build` when you change `requirements.txt`, the Dockerfile, or any system dependency. Code changes don't need a rebuild — the bind mount handles them.

### Stop and remove containers and network
```bash
docker-compose down
```

### Stop and also remove volumes
```bash
docker-compose down -v
```

Use `-v` carefully — this deletes the Postgres volume and all your data.

### Test
```
http://localhost:8000/
http://localhost:8000/db
```

---

## Hot Reloading

The backend service has two things that enable hot reloading in development:

**Bind mount** — mounts the local `backend/` directory into `/app` inside the container. Changes saved locally are immediately visible inside the container.

```yaml
volumes:
  - ./backend:/app
```

**--reload flag** — overrides the Dockerfile's CMD at runtime. Uvicorn watches for file changes and restarts automatically.

```yaml
command: uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

The Dockerfile CMD stays production-ready without `--reload`. The override only applies when running via Compose in development.

To verify — edit `app.py`, save it, and watch the logs:

```bash
docker-compose logs -f backend
```

Uvicorn detects the change and reloads without any restart needed.

---

## Key Concepts

### What Compose Actually Does

Compose reads the YAML file and translates it into Docker API calls — the same calls made manually with bare Docker. Every line in `docker-compose.yml` maps to a flag in a `docker run` command:

| `docker run` flag | Compose equivalent |
|---|---|
| `--name postgres` | service name |
| `--network fastapi-network` | automatic — Compose creates a default network |
| `-e DB_HOST=postgres` | `environment:` or `env_file:` |
| `-p 8000:8000` | `ports:` |
| `-v ./backend:/app` | `volumes:` under the service |
| `--build .` | `build:` |
| `uvicorn ... --reload` | `command:` |

### Default Network

Compose automatically creates one network for the project and attaches all services to it. No explicit network configuration is needed for services to reach each other by name. The network is named `projectfolder_default`.

### depends_on vs Readiness

`depends_on` controls start order — it does not guarantee the service is ready. Postgres container starting is not the same as Postgres accepting connections. Postgres takes a few seconds to initialize after the container starts.

The fix is a health check combined with `condition: service_healthy`:

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U myuser -d my_db"]
  interval: 5s
  timeout: 5s
  retries: 5
```

Compose waits until Postgres passes the health check before starting the backend. Without this, FastAPI starts immediately and fails to connect.

The `-d my_db` flag on `pg_isready` is important — without it, `pg_isready` tries to connect to a database named after the user, which doesn't exist.

### Named Volume vs Bind Mount

The Postgres service uses a named volume — Docker manages the storage location, data survives container deletion and recreation.

The backend service uses a bind mount — a specific host path is mounted into the container, used for development hot reloading. Not used in production.

| | Named Volume | Bind Mount |
|---|---|---|
| Managed by | Docker | You |
| Survives `docker-compose down` | ✅ | ✅ (it's your local files) |
| Survives `docker-compose down -v` | ❌ | ✅ |
| Use case | Database data | Dev hot reloading |

### Environment Variables and Secrets

Credentials are in `.env` files, not hardcoded in `docker-compose.yml`. The `.env` files should be in `.gitignore` — never committed to version control.

Passwords must match between `db.env` and `backend.env`. A mismatch causes an authentication error that looks like a connection error.

### Rebuilding vs Hot Reloading

| Change | Action needed |
|---|---|
| `app.py` or any code | Nothing — bind mount handles it |
| `requirements.txt` | `docker-compose up --build` |
| `Dockerfile` | `docker-compose up --build` |

Compose does not rebuild automatically on code changes. `--build` must be passed explicitly when the image itself needs to change.

---

## Useful Commands

```bash
# See status of all services
docker-compose ps

# Follow logs for a specific service
docker-compose logs -f backend
docker-compose logs -f postgres

# Open a shell inside a running service
docker-compose exec backend bash
docker-compose exec postgres psql -U myuser -d my_db

# Rebuild without starting
docker-compose build

# Remove stopped containers
docker-compose rm
```

---

## Cleanup

```bash
# Stop and remove containers and network
docker-compose down

# Also remove the Postgres volume (deletes all data)
docker-compose down -v

# Remove dangling images from builds
docker image prune
```