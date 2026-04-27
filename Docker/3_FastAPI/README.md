# FastAPI + Postgres — Bare Docker Experiment

## What This Is

A minimal FastAPI app connected to a Postgres database, wired together using plain Docker — no Compose. The goal was to understand Docker networking, volumes, and container communication from first principles before using any automation tools.

---

## Project Structure

```
.
├── app.py
├── requirements.txt
└── Dockerfile
```

---

## What We Built

### `app.py`
A minimal FastAPI app with two endpoints:
- `GET /` — health check, returns `{"status": "ok"}`
- `GET /db` — connects to Postgres using env vars, returns `{"db": "connected"}`

Database credentials are read from environment variables at runtime — never hardcoded.

### `requirements.txt`
```
fastapi
uvicorn
psycopg2-binary
```

### `Dockerfile`
```dockerfile
FROM python:3.12-slim

# Create non-root user — never run as root in production
RUN addgroup --system appgroup && \
    adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy requirements first — pip install gets its own cached layer
# This means code changes don't trigger a re-install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code after dependencies — cache is preserved on code-only changes
COPY . .

# Switch to non-root after all installs — pip needs root to write to system dirs
USER appuser

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## How to Run It

### 1. Build the FastAPI image
```bash
docker build -t fastapi-app .
```

### 2. Create a network
```bash
docker network create fastapi-network
```

Containers on the same user-defined network can reach each other by container name. Docker runs an internal DNS server at `127.0.0.11` that resolves container names to IPs automatically.

### 3. Run Postgres
```bash
docker run -d \
  --name postgres \
  --network fastapi-network \
  -e POSTGRES_PASSWORD=secret \
  -e POSTGRES_USER=myuser \
  -e POSTGRES_DB=mydb \
  postgres:16
```

No `-p` flag — Postgres is intentionally internal only. Nothing outside Docker can reach it.

### 4. Run FastAPI
```bash
docker run -d \
  --name fastapi \
  --network fastapi-network \
  -e DB_HOST=postgres \
  -e DB_NAME=mydb \
  -e DB_USER=myuser \
  -e DB_PASSWORD=secret \
  -p 8000:8000 \
  fastapi-app
```

`DB_HOST=postgres` works because Docker DNS resolves the container name `postgres` to its IP on the network.

### 5. Test
```
http://localhost:8000/
http://localhost:8000/db
```

### 6. Hot reloading
To implement hot reloading, bind mount the current working directory in host to the working directory (code directory) in the container
docker run -d \
  --name fastapi \
  --network fastapi-network \
  -e DB_HOST=postgres \
  -e DB_NAME=mydb \
  -e DB_USER=myuser \
  -e DB_PASSWORD=secret \
  -p 8000:8000 \
  -v $(pwd):/app \
  fastapi-app 

---

## Key Concepts Learned

### Layer Caching
Docker caches each instruction as a layer. Once a layer is invalidated, everything below it rebuilds. `requirements.txt` is copied and installed before application code so that code changes don't trigger a re-install of dependencies.

### Non-Root User
The default Docker process runs as root. If an attacker exploits the app and escapes the container, they land on the host as root. Creating and switching to a non-root user limits the blast radius. `pip install` happens before the user switch because it needs write access to system directories.

### User-Defined Networks
Containers on the default bridge network can only talk by IP. Containers on a user-defined bridge network get DNS — they resolve each other by container name. Always create a named network rather than using the default.

### Secrets at Runtime
Credentials are never baked into the image via `ENV` in the Dockerfile. They are injected at runtime via `-e` flags. Anything in the image is readable via `docker history` or `docker inspect`.

### Port Exposure
Only the service that needs to be publicly accessible gets `-p host:container`. Internal services (Postgres, Redis) have no port mapping — they are only reachable by other containers on the same network.

---

## Cleanup

```bash
docker stop fastapi postgres
docker rm fastapi postgres
docker network rm fastapi-network
docker image rm fastapi-app
```

---

## Why We Did This Without Compose

Docker Compose automates exactly what we did manually here — creating networks, passing environment variables, managing start order. Doing it by hand first means Compose is automation of understood concepts, not a magic black box.