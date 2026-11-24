# Deployment, backup, and rollback

Deployment is a separate, controlled stage. This repository does not contain production IP addresses, privileged usernames, certificate locations, neighboring-service inventory, or artifact-transfer paths.

## 1. External build and test

Production is not a build host. Use `.github/workflows/ci.yml` on a GitHub-hosted Ubuntu runner in the approved private repository. Windows is optional.

Lockfile creation is intentionally separate:

1. Push the sanitized source to the private repository.
2. Run `.github/workflows/bootstrap-lockfile.yml` manually.
3. Download `frontend/package-lock.json`, review it, and commit it.
4. Enable the ordinary push/pull-request triggers and push the lockfile in the same commit.
5. Require all ordinary CI jobs to pass.

Ordinary CI never generates a replacement lockfile. It runs backend tests and migration checks, `npm ci`, TypeScript, Vitest, Vite, a Docker image build/restart smoke test, and Playwright against the built application. It produces checksummed frontend, backend-image, deployment, and browser-evidence artifacts.

No workflow deploys to production and no production secret is stored in GitHub Actions.

## 2. Host-specific configuration

The deployment owner creates `/etc/vzn-activity-tracker/deploy.conf` out of band as `root:root`, mode `0600`:

```text
VZN_PUBLIC_IPV4=<production IPv4>
VZN_CERTIFICATE_FULLCHAIN=<absolute full-chain path>
VZN_CERTIFICATE_PRIVATE_KEY=<absolute private-key path>
```

Do not commit this file or its resolved values. The root installer parses only these exact keys; it does not source the file as shell code. The Nginx file in `deploy/nginx/` is a template whose placeholders are rendered only by that installer.

Before installation, independently verify DNS, certificate coverage and expiry, free disk, free loopback port, Docker/Nginx health, and a private baseline of every unrelated production service. Do not run Docker prune or alter unrelated applications.

## 3. Artifact transfer and first installation

Download artifacts from one successful CI run into an operator-selected private directory and verify every supplied SHA-256 file. Never transfer a development `.env`, SQLite database, `node_modules`, browser report, or screenshot into the application root.

Two privilege models are supported and must be reviewed immediately before use:

- **A — one-time owner-operated installation:** the owner installs the staging helper, stages one exact artifact set, and runs the no-argument root deployer.
- **B — temporary restricted sudo:** the owner stages the artifacts, installs root-owned helpers, and temporarily grants the invoking user permission to execute only the digest-pinned no-argument deployer.

Exact generic commands and the revoke procedure are documented in `deploy/root/README.md`. Do not install or execute them until CI is green and production deployment is explicitly authorized.

The installer verifies root ownership, archive paths, checksums, commit identity, free space, service state, TLS inputs, and port availability. It loads the prebuilt image, extracts the prebuilt frontend, initializes secrets interactively, starts only the VZN Compose project, renders an isolated Nginx configuration, validates `nginx -t`, and performs a health check. It performs no build and installs no packages.

## 4. Production verification

After an explicitly authorized deployment, verify and record:

- DNS and HTTP-to-HTTPS behavior;
- certificate hostname, chain, and expiry;
- `/api/v1/health`;
- unauthenticated access to protected APIs returns 401;
- administrator login, CSRF enforcement, logout, and authorized mutations;
- SQLite data persists after restarting only the VZN backend;
- Nginx/application logs and RAM/disk use;
- every service in the private pre-deployment baseline remains healthy.

Do not declare deployment successful unless these checks actually ran.

## Backup and restore

Use the application backup command, which calls SQLite's online backup API and then `PRAGMA integrity_check`. Never copy a live WAL database directly. Keep an encrypted off-host copy; an on-server backup alone is not disaster recovery.

Restore only during an authorized maintenance window. Stop only the VZN backend, preserve the current database, restore a verified backup with the expected ownership/mode, start only VZN, and repeat the health, login, persistence, log, resource, and unrelated-service baseline checks.

## Rollback

For a code-only rollback, restore the previous backend image tag and atomically repoint the frontend release link. For a schema rollback, restore the verified backup taken immediately before the update; never reverse SQLite migrations ad hoc. Validate the full production checklist afterward.
