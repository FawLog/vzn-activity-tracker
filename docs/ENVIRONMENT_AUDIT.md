# Environment boundary

This repository deliberately contains no host-specific environment audit. Detailed infrastructure findings are maintained out of band because they can disclose usernames, addresses, filesystem paths, neighboring applications, network topology, service inventory, operational incidents, or third-party integration details.

The versioned constraints are limited to facts required to build and operate this application safely:

- Windows is optional and is not required for development or delivery.
- Dependency installation, frontend builds, Docker builds, Chromium, Playwright, and screenshot capture run only on an approved external runner.
- Production receives a prebuilt frontend and a prebuilt backend image.
- The application uses an isolated root, a loopback-only backend listener, persistent SQLite storage, and an isolated Nginx server block.
- Existing host services and data are out of scope and must be validated against a private baseline before and after deployment.
- Production addresses, DNS-provider details, certificate paths, privileged usernames, and artifact-transfer paths are supplied out of band at deployment time.
- No `.env`, database, backup, browser trace, production log, credential, or private audit report belongs in Git.

Before deployment, the operator must repeat the read-only capacity, DNS, TLS, permissions, and existing-service checks on the target host. Results must be stored in a private operational record rather than committed here.
