# VZN Activity Tracker agent instructions

## Role and approach

Act as a senior full-stack/backend engineer. Inspect existing code and current infrastructure before changing anything. Treat this repository as the source of truth, extend its architecture, and keep changes small, reviewable, and runnable. Do not refactor unrelated areas or invent missing product rules.

Use modern TypeScript/JavaScript and Python 3.12. Prefer explicit types, async/await, focused handlers, separate business logic, clear data access, predictable errors, and environment-based configuration. Never commit hardcoded secrets, `.env`, production databases, backups, browser traces, or private evidence.

## Environment separation is mandatory

### EXTERNAL BUILD RUNNER

Only a confirmed non-production build host may perform the following. The default is GitHub Actions on a GitHub-hosted Ubuntu runner in a private repository; Windows is not required.

- npm dependency installation and lockfile generation;
- Vite production builds and TypeScript/Vitest runs;
- Docker image builds;
- Playwright, Chromium, screenshots, and visual comparison;
- responsive/browser QA at 1440×900, 1280×800, and 390×844.

Do not claim these checks unless they actually ran outside the production VPS.

### REMOTE — production VPS

The production host is resource-constrained and already runs unrelated services. Host inventory, addresses, usernames, filesystem layout outside this application, and third-party integration details are intentionally not versioned.

Never run Chromium, Playwright, a Vite dev server, `npm run build`, frontend dependency installation, Docker builds, OCR, or other resource-heavy development tasks on the VPS. Production receives prebuilt `frontend/dist` and a prebuilt backend image. Light health checks, database migrations at app startup, and SQLite backup verification are allowed.

## Existing services are out of scope

All pre-existing sites, processes, containers, databases, network services, firewall rules, and backups must remain untouched. Never stop, restart, or delete unrelated services; run Docker prune; edit unrelated Compose files; change unrelated data or network policy; or reboot the server. VZN must use an independent Compose project, a loopback-only backend port, and its own application root selected during the controlled deployment stage.

Before any infrastructure change:

1. Inspect current state read-only.
2. Back up only the VZN file being changed.
3. Validate exact targets.
4. Run `nginx -t` before a graceful Nginx reload.
5. Recheck the private out-of-band inventory of existing services afterward.

If sudo, Docker socket, DNS provider, or external-runner access is unavailable, prepare the exact safe operation and report the blocker. Do not work around missing authority.

## Product invariants

- FID is the primary player identity; preserve nickname history and membership intervals.
- Contribution, attendance, and reliability remain separate. The officer-approved Overall Activity screening index may summarize them transparently, with explicit evidence limitations. Never create a universal usefulness score or automatic exclusion decision.
- Raw points from different event types are never summed.
- Missing from a partial top-N list does not mean zero.
- Presence is explicitly confirmed present, confirmed absent, excused/no duty, or unknown.
- Registered-but-absent differs from not registered; registered substitutes must enter independently and have the same attendance obligations as main players; confirmed absence is a no-show for either role.
- Bear damage and Foundry/Canyon points are informational, not proportional effectiveness scores.
- OCR must be review-first and cannot publish directly.
- Officer notes are private and audited.
- No public personal records until appropriate member authentication/authorization exists.
- Do not introduce attendance penalties, point quotas, minimum targets, or fabricated metrics.

Read `PRODUCT_DECISIONS.md` before changing data semantics.

## Application structure

- `backend/app/api`: HTTP routing and authorization boundaries.
- `backend/app/services`: sessions and business/data-access operations.
- `backend/migrations`: append-only, checksummed migrations. Never edit an applied migration; add a new one.
- `frontend/src/components`: shared app UI.
- `frontend/src/pages`: route surfaces.
- `frontend/src/lib`: API, auth, routing, formatting, and types.
- `deploy/nginx`: isolated VZN virtual host only.

Keep API routes versioned under `/api/v1`. Every mutation must enforce server-side authorization and CSRF. Preserve same-origin cookies. Keep production API docs and debug mode disabled.

## Design system

Follow `DESIGN_SYSTEM.md` and the accepted references in `docs/concepts/`. The interface is a restrained Arctic Intelligence operations workspace: open tables/rails, precise dividers, compact typography, meaningful state colors, and minimal motion. Avoid generic SaaS card grids, fake charts/data, neon sci-fi framing, decorative pills, marketing heroes, or random icons. All true app controls and text remain code-native.

## Mandatory database migration checklist

Whenever a migration is added, complete this checklist in the same commit/PR, before pushing:

1. Add the next contiguous numbered SQL file under `backend/migrations/`. Never edit or remove previously applied migrations.
2. Search the entire repository for the previous schema version, including `migration_version`, migration return-value assertions, explicit migration filenames, migration fixture lists, and expected missing-file/gap messages. Do not rely on updating only the migration tests.
3. Explicitly inspect and update all affected assertions in:
   - `backend/tests/test_api.py` — health endpoint expected migration version;
   - `backend/tests/test_backup.py` — backup/restore expected migration version;
   - `backend/tests/test_migrations.py` — latest-version assertions, historical migration subsets, missing-file checks, gap fixture, and upgrade/idempotency tests.
4. Check any other version-dependent fixtures or documentation discovered by the repository-wide search. Preserve intentionally historical version expectations and do not change CI/deployment/security controls without owner approval.
5. Run the full backend suite (`PYTHONPATH=backend python -m pytest backend/tests -q`) on a non-production runner and confirm migration, health, backup/restore, and upgrade tests pass. Do not weaken assertions or skip tests to obtain a green build. Verify all six CI jobs on the exact final PR head before merging.

This checklist is mandatory for every future migration, even an additive one-column migration. The recurring failure to update health and backup assertions was observed again when adding migration 0024 (PR #85).

## Verification

For backend changes, run unit tests in a safe development environment. For frontend changes, run TypeScript/build/Vitest and browser QA on the external runner, never on the production VPS. Compare browser screenshots with the accepted concepts using the same target dimensions and inspect layout, copy, typography, palette, controls/icons, empty states, and responsive behavior.

Production deployment must verify:

- `/api/v1/health` and container health;
- unauthorized API access returns 401;
- login, CSRF, logout, player creation, and event creation;
- data survives a restart of only the VZN backend;
- DNS, TLS hostname, HTTP→HTTPS, security headers, and SPA fallback;
- `nginx -t` and graceful reload;
- all services in the private out-of-band baseline remain healthy;
- before/after memory, CPU, disk, and logs.

Use SQLite's online backup API. Never copy a live WAL database directly. See `DEPLOYMENT.md` for update, backup, restore, and rollback procedures.

## Merge policy

Use explicit squash-merge only, with the verified PR head SHA and all six CI jobs successful. Verify that the resulting main commit has exactly one parent. Do not bypass autodeploy provenance checks or change privileged controls without owner approval.
