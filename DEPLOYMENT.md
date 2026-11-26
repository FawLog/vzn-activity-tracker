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

No workflow directly deploys to production and no production secret is stored in GitHub Actions. Optional event-driven deployment is described in deploy/autodeploy/README.md.

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

The installer verifies root ownership, archive paths, checksums, commit identity, service state, matching TLS certificate/key inputs, and port availability. Its disk preflight budgets three times the uncompressed backend OCI payload, the frontend and deployment payloads, 256 MiB of installation overhead, and a 512 MiB post-install reserve. It then loads the prebuilt image, extracts the prebuilt frontend, initializes secrets interactively, starts only the VZN Compose project, renders an isolated Nginx configuration, validates `nginx -t`, and performs a health check. It performs no build and installs no packages.

Artifact staging first copies every input into a root-owned temporary snapshot; validation and extraction use only that immutable snapshot, which is atomically promoted after all checks pass. Application installation writes a root-only marker before durable changes. A handled error or signal stops only the VZN Compose project, restores the pre-existing Nginx state, and moves partial VZN files to a root-only recovery directory under `/var/backups/vzn-activity-tracker/`; it never prunes Docker. If a reboot or uncatchable interruption leaves a marked partial application root, rerunning the same commit's no-argument deployer first isolates that state and then starts a clean attempt. An unmarked directory or a marker from another commit is never changed automatically and requires manual review.

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

## Updates, backup, and restore

`vzn-deploy` is intentionally a first-install-only command. It refuses an existing
application root, so it cannot accidentally recreate production secrets or an
empty SQLite database over a working installation. Every later version uses the
separate no-argument root-owned `vzn-update` command staged from the same exact
CI artifact set.

The updater verifies the same commit identity, SHA-256 files, root-owned
staging, artifact paths, Docker/Nginx state, existing VZN health and conservative
disk reserve as the first installer. It never runs a build, changes Nginx,
touches another Compose project, or asks for an administrator password. It
keeps the existing `.env` and changes only its non-secret `VZN_IMAGE_TAG` line
atomically; the session secret and administrator password hash remain byte-for-byte
unchanged. The SQLite directory is retained in place.

Before loading a new image or changing the frontend link, the updater creates and
verifies an online SQLite backup. It saves the prior `.env`, Compose file, release
link and transaction record under `/var/backups/vzn-activity-tracker/`, then uses
only the VZN Compose project to recreate the backend. If local or public health
does not recover, it stops only VZN, restores the verified database through the
SQLite backup API, restores the old image tag, Compose file and frontend link, and
starts only the previous VZN backend. The prior image is deliberately retained;
no Docker image, volume or system-wide prune runs.

An uncatchable interruption leaves `/srv/vzn-activity-tracker/.vzn-updating` as a
root-only evidence marker. The next update refuses to run rather than guessing
whether a migration completed. Inspect the named root-only transaction and backup,
restore manually if required, verify health, and remove the marker only after the
owner has recorded the recovery.

For an existing first-install deployment whose old staging helper does not support
updates, the owner must first verify the updated helper from the reviewed
deployment artifact and install that root-owned copy. This is a controlled helper
upgrade, not an application deployment:

```sh
# Run only after verifying the SHA-256 of this file in the reviewed deployment artifact.
sudo install -o root -g root -m 0755 \
  /absolute/private/path/to/reviewed-source/deploy/root/stage-vzn-artifacts \
  /usr/local/sbin/vzn-stage-vzn-artifacts
sudo /usr/local/sbin/vzn-stage-vzn-artifacts --update /absolute/private/path/to/artifacts
sudo /usr/local/sbin/vzn-update
```

The owner should capture the pre-update health, VZN container status, RAM/disk and
the private baseline before this sequence, then repeat the production checklist
after it. The updater's public HTTPS health check has a bounded retry budget
(15 attempts, 3-second connect timeout, 5-second request timeout, 1-second delay).
It accepts only an HTTP-successful `/api/v1/health` JSON response with `status=ok`,
`database=ready`, and a numeric migration version. A retry is mitigation for a
transient readiness failure, not a diagnosis of Nginx configuration propagation.

Use the application backup command, which calls SQLite's online backup API and then `PRAGMA integrity_check`. Never copy a live WAL database directly. Keep an encrypted off-host copy; an on-server backup alone is not disaster recovery.

Restore only during an authorized maintenance window. Stop only the VZN backend,
preserve a fresh verified backup of the current database, then use the application
command inside a trusted VZN image: `python -m app.backup restore
/data/backups/<verified-backup>.sqlite3 --database /data/vzn.sqlite3`. This uses
SQLite's backup API rather than a raw database/WAL copy. Start only VZN and repeat
the health, login, persistence, log, resource, and unrelated-service baseline
checks.

## Rollback

For a code-only rollback, restore the previous backend image tag and atomically repoint the frontend release link. For a schema rollback, restore the verified backup taken immediately before the update; never reverse SQLite migrations ad hoc. Validate the full production checklist afterward.

## Roster avatar images (operator-managed CSP)

Roster rows use the already stored provider `avatar_url`, not a new API call or a server-side image proxy. The frontend accepts HTTPS URLs only, sends no referrer, lazy-loads images and falls back to a local icon if an image is absent or blocked. WhiteoutStats URLs from the obsolete `gof-format-avatar.akamaized.net` hostname are normalized to the verified `gof-formal-avatar.akamaized.net` hostname on import; migration `0007` corrects existing profile URLs. The Nginx template permits only that exact HTTPS CDN origin in `img-src`; the normal updater intentionally leaves an active Nginx vhost unchanged.

Before changing avatar CSP in production, inspect only distinct HTTPS hostnames from the existing VZN SQLite `player_whiteoutstats_profiles.avatar_url` values (no player identifiers, full URLs, tokens or new WhiteoutStats requests). Verify the observed hosts are legitimate provider/game avatar CDNs. Back up the active VZN-only Nginx virtual host, permit only the exact verified origins in the existing `img-src 'self' data:` directive, preserve every other directive and service, run `nginx -t`, and gracefully reload Nginx. Verify the delivered CSP and actual image loading in an authenticated roster. Never add a general `https:` or wildcard to CSP; do not alter unrelated vhosts. Restore the backed-up vhost if validation fails.

## Google Vision OCR preview (foundation)

Optional `GOOGLE_VISION_API_KEY` in the existing root-protected production `.env` is passed only to the backend via Compose. Restrict the key to Cloud Vision API and preferably to the production egress IP; enable billing and set project quota/budget alerts. Do not expose it to frontend, CI, logs, or chat. Do not restart production merely to configure an unused key; apply it during the next authorized deployment. Service-account JSON authentication is supported and takes precedence over API key; no silent fallback on failure. Store the file under the existing mounted data directory, in `/data/secrets/google-vision.json` inside the container. On the host create `data/secrets` with owner root:10001 and mode 0750 and install the JSON root:10001 mode 0440. Set `GOOGLE_APPLICATION_CREDENTIALS=/data/secrets/google-vision.json` in the protected production `.env`. The backend runs as UID/GID 10001. Never include this directory in exports, backup bundles, logs or Git. The existing SQLite online backup does not copy the credentials directory. Reuse a bot credential only with owner approval; a dedicated least-privilege service account is preferable. Restart only during authorized deployment. The preview accepts one PNG/JPEG under 900 KiB per request to fit the existing 1 MiB Nginx limit. It returns text and word coordinates, does not write event results or retain images, and is not yet the final evidence-import workflow. No Nginx change is required. Tests mock Google; real credentials are never used in CI.
