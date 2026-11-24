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

- `alliance_groups`: independent access and reporting boundary with one transactional primary alliance.
- `alliances`: primary/additional alliances, status, state metadata, and a separate future WhiteoutStats settings record.
- `players`: global technical identity keyed by FID; it is never duplicated per alliance.
- `player_group_profiles`: group-scoped player visibility and an explicitly unconfirmed legacy state.
- `player_nickname_observations`, `player_membership_observations`, `player_alliance_transitions`, and `player_primary_alliance_history`: evidence-first foundations for future roster synchronisation and transfer review. No automatic transfer classification runs yet.
- `events`: event type, event date, draft/published state, and nullable legacy / required-for-new `alliance_id` ownership.
- `event_participants`: preserved foundation results. `event_registrations`, `event_attendance_assessments`, and `event_result_entries` prepare a future separation of registration, attendance, and raw result facts.
- `audit_log`: attributed mutations.
- `admin_sessions`, `login_attempts`: security state.

The schema deliberately keeps raw event points event-specific. No cross-event sum or universal rating exists. Presence uses confirmed present, confirmed absent, excused, or unknown; partial evidence cannot manufacture an absence.

## Frontend boundaries

- `components/`: app shell, brand, page headers, and reusable feedback states.
- `pages/`: route-level surfaces.
- `lib/api.ts`: same-origin fetch client and CSRF attachment.
- `lib/auth.tsx`: session bootstrap and authentication state.
- `lib/router.ts`: minimal History API routing to avoid another runtime dependency.

All roster, event, ranking, and admin routes require the one administrator session until alliance-member authorization is implemented. Roster and event reads are group-scoped; global legacy routes are not used, so an ID cannot cross a future group authorization boundary.

## Operational constraints

- One Uvicorn worker matches the 1 vCPU VPS.
- The backend container has a 256 MiB memory limit, read-only root filesystem, dropped capabilities, a small tmpfs, and bounded JSON logs.
- SQLite uses WAL mode and a 15-second busy timeout.
- Database backups use SQLite's online backup API followed by `PRAGMA integrity_check`.
- Static assets and the backend image are built outside production.

## Future extension points

Roster editing, event-specific result editors, evidence uploads, OCR review, WhiteoutStats synchronisation, and Discord OAuth can be added behind new migrations and services. Initial group onboarding explicitly assigns legacy events to its primary alliance; it never invents roster observations or legacy membership. OCR must create review drafts and must never publish directly. Discord role mapping must precede multi-officer editing rights.
