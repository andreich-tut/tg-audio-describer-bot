# Redis Integration Plan

## Context

Redis is partially integrated — client code, config, and OAuth SSE pub/sub exist, but dependencies and Docker service are missing.

**Requirements:**
- Will be used for other features beyond OAuth SSE in the future
- Docker Compose is the only deployment target
- Redis data should be persisted across container restarts

## Phase 1 — Dependencies

1. Add `redis[hiredis]>=5.0` to `[project.dependencies]` in `pyproject.toml`
2. Add `sse-starlette>=2.0` if not already in dependencies (needed by the OAuth SSE endpoint that uses Redis)
3. Rebuild Docker image to pick up new packages

## Phase 2 — Docker Compose Service

4. Add Redis service to `docker/docker-compose.yml`:
   - Image: `redis:7-alpine`
   - Persistent volume: `redis-data:/data`
   - Redis config: `appendonly yes` (AOF persistence for durability)
   - Health check: `redis-cli ping`
   - Restart policy: `unless-stopped`
   - Expose only on internal Docker network (no host port binding)
5. Add `redis-data` to the `volumes:` section
6. Add `depends_on: redis` (with health check condition) to the `bot` and `frontend` (webapp) services so they wait for Redis to be ready
7. Set `REDIS_URL=redis://redis:6379/0` in the service environment (override the localhost default for Docker networking)

## Phase 3 — Client Hardening

8. In `infrastructure/redis_client.py`:
   - Add connection retry logic on startup (Redis may take a moment to become ready)
   - Add a `ping()` health check function that other modules can call
   - Add `decode_responses=True` to avoid manual bytes decoding everywhere
   - Configure connection pool limits (`max_connections`) for future scaling
9. In `application/state.py`:
   - Call Redis ping during `initialize_state()` to fail fast if Redis is unreachable
   - Log Redis connection status on startup

## Phase 4 — Configuration & Docs

10. Verify `REDIS_URL` in `.env.example` has a clear comment explaining the format and the Docker default
11. Update `docs/ai-context/PROJECT.md`:
    - Add Redis to the dependencies/infrastructure section
    - Document the `REDIS_URL` env var
    - Note that Redis persistence uses AOF

## Phase 5 — Validation

12. `docker compose up` — verify Redis starts, passes health check, and bot/webapp connect
13. Test the OAuth SSE flow end-to-end (the only current Redis consumer)
14. Restart the Redis container — verify data directory persists and service recovers
