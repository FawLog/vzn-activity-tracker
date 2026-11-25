# VZN Activity Tracker

VZN Activity Tracker is the foundation for **VZN // Arctic Intelligence**, an evidence-first activity platform for a Whiteout Survival alliance. This release provides a real React interface, a versioned FastAPI API, SQLite migrations, one-administrator authentication, manual player/event creation, and an audit trail. It does not claim to be a finished analytics tracker.

## Current scope

- Pages: Overview, Players, Player Profile, Events, Event Details, Rankings, Admin, and Login.
- Real administrator session with an opaque server-side cookie, CSRF validation, scrypt password hashing, and login throttling.
- Manual player creation using FID as the primary identity.
- Manual event creation with draft/published status.
- SQLite nickname history, membership intervals, event participant foundations, and attributed audit records.
- WhiteoutStats free-tier alliance roster sync (`info,roster`) with FID-based profiles, typed history, safe transfer observations, and a 12-hour SQLite-backed schedule.
- No OCR, screenshot import, Discord OAuth, paid Frosty endpoints, automatic scoring, or fabricated demo results.
- Roster records and event details are restricted to the administrator in this foundation release.

## Repository layout

```text
backend/             FastAPI application, migrations, backup utility, tests
frontend/            React + TypeScript + Vite application and Playwright spec
deploy/nginx/        Isolated Nginx server block for vzn.fawlog.cc
docs/concepts/       Accepted ImageGen design references
scripts/             Secret initialization and SQLite backup entrypoints
compose.yaml         Backend-only production Compose project
```

## Development environments

The production VPS is intentionally not a frontend build or browser-test host.

- **EXTERNAL BUILD RUNNER:** dependency installation, TypeScript, Vitest, Vite build, Docker image build, Playwright/Chromium, screenshots, and visual comparison. The default is a GitHub-hosted Ubuntu runner in a private repository; Windows is optional and not required.
- **REMOTE — VPS:** Nginx, one prebuilt FastAPI image, SQLite, backups, health checks, and light smoke tests only.

The VPS must not run frontend dependency installation, Vite builds, Docker builds, Chromium, or Playwright. `.github/workflows/ci.yml` runs those tasks on GitHub-hosted Ubuntu and produces checksummed frontend and backend artifacts plus real browser screenshots. Code must remain in a private repository unless the owner explicitly approves otherwise.

## External CI workflow

After the source is pushed to an approved private GitHub repository, the one-time manual bootstrap workflow creates `frontend/package-lock.json` on a GitHub-hosted runner and uploads it as an artifact. That file must be reviewed and committed before the ordinary CI workflow is enabled. The ordinary CI then performs:

- a policy check that rejects a missing lockfile, followed by `npm ci`;
- TypeScript, Vitest, and the Vite production build;
- backend dependency checks, pytest, and migration tests;
- a loadable Docker image build and restart smoke test;
- a full FastAPI plus built-frontend browser stack;
- Chromium tests and real screenshots at 1440×900, 1280×800, and 390×844.

The bootstrap workflow never commits or pushes. A maintainer must add its lockfile artifact to Git before any ordinary `npm ci` run. No GitHub repository, remote, or external upload is created automatically by this source tree.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Deployment, backup, and rollback](DEPLOYMENT.md)
- [Design system](DESIGN_SYSTEM.md)
- [Product decisions](PRODUCT_DECISIONS.md)
- [Environment audit](docs/ENVIRONMENT_AUDIT.md)
- [QA status and fidelity ledger](docs/QA_STATUS.md)
- [Agent operating rules](AGENTS.md)
- [Changelog](CHANGELOG.md)

## WhiteoutStats configuration

WhiteoutStats is optional. To enable it, add the API key only to the root-owned
production environment file (mode `0600`), never to a frontend value or Git:

```dotenv
WHITEOUTSTATS_API_KEY="wos_..."
```

The backend uses `Authorization: Bearer`, a 75-second bounded client timeout,
and only `GET /v1/alliances/{kid}/{tag}?include=info,roster&wait=30`. Without
the key, alliances can still be created and the UI reports that sync is not
configured. The default interval is intentionally fixed at 720 minutes.
