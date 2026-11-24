# Architecture

## Runtime shape

The production system has three independent layers:

1. Existing host Nginx serves the prebuilt React files and terminates TLS.
2. Nginx proxies `/api/` to one FastAPI/Uvicorn process bound to `127.0.0.1:8088`.
3. FastAPI stores application state in `/data/vzn.sqlite3` inside a dedicated bind-mounted data directory.

There is no production Node.js process, local OCR, Redis, task queue, or connection to unrelated host applications.

## Backend boundaries

- `app/api/router.py`: HTTP contracts and authorization boundaries.
- `app/services/sessions.py`: opaque sessions, CSRF validation, safe proxy address handling, and login throttling.
- `app/services/records.py`: explicit roster/event/audit data access.
- `app/database.py`: SQLite connections and ordered, checksummed migrations.
- `app/security.py`: scrypt password hashing and keyed identifiers.
- `migrations/`: append-only schema history.

Every mutation requires an authenticated server-side session and a matching `X-CSRF-Token`. The browser cookie contains only an unguessable session token; authentication state and expiry live in SQLite. Login rotates the session token to prevent fixation. Production cookies are HttpOnly, Secure, SameSite=Lax, and path-scoped to `/`.

The single-process login limiter is persisted in SQLite rather than memory. Nginx is the only intended caller of the backend. The backend exposes no direct public port.

Uvicorn accepts forwarded headers because Docker publishes the service only on host loopback and Nginx is the intended caller. Do not change the Compose binding to a public interface without replacing that trust model.

## Data model

- `players`: current identity keyed by FID.
- `player_nicknames`: dated nickname history.
- `player_memberships`: alliance membership intervals.
- `events`: event type, event date, and draft/published state.
- `event_participants`: future event-date results with explicit presence status, roster role, raw points, and evidence completeness.
- `audit_log`: attributed mutations.
- `admin_sessions`, `login_attempts`: security state.

The schema deliberately keeps raw event points event-specific. No cross-event sum or universal rating exists. Presence uses confirmed present, confirmed absent, excused, or unknown; partial evidence cannot manufacture an absence.

## Frontend boundaries

- `components/`: app shell, brand, page headers, and reusable feedback states.
- `pages/`: route-level surfaces.
- `lib/api.ts`: same-origin fetch client and CSRF attachment.
- `lib/auth.tsx`: session bootstrap and authentication state.
- `lib/router.ts`: minimal History API routing to avoid another runtime dependency.

The public Overview reveals no player records. All roster, event, ranking, and admin routes require the one administrator session until alliance-member authorization is implemented.

## Operational constraints

- One Uvicorn worker matches the 1 vCPU VPS.
- The backend container has a 256 MiB memory limit, read-only root filesystem, dropped capabilities, a small tmpfs, and bounded JSON logs.
- SQLite uses WAL mode and a 15-second busy timeout.
- Database backups use SQLite's online backup API followed by `PRAGMA integrity_check`.
- Static assets and the backend image are built outside production.

## Future extension points

Roster editing, event-specific result editors, evidence uploads, OCR review, and Discord OAuth can be added behind new migrations and services. OCR must create review drafts and must never publish directly. Discord role mapping must precede multi-officer editing rights.
