# Visual and functional QA status

## Verified external run

GitHub Actions run `45420765109` completed successfully for commit `2720a27f00e917e12103e735b0f88d74f1b286a2` on a GitHub-hosted Ubuntu runner. No dependency installation, frontend build, Docker build, Chromium, or Playwright process ran on production.

Results:

- committed lockfile policy: passed;
- backend dependency consistency, migration checks, and pytest: 16 passed;
- `npm ci`: passed, with 0 reported vulnerabilities;
- TypeScript: passed;
- Vitest: 2 passed;
- Vite production build: passed, 2,151 modules transformed;
- backend Docker build, health check, restart, and second health check: passed;
- Playwright full-stack tests: 6 passed at 1440×900, 1280×800, and 390×844;
- production frontend, backend image, deployment bundle, and browser evidence: uploaded.

The sole test warning is an upstream FastAPI/Starlette deprecation notice recommending the future `httpx2` test-client package. It does not affect runtime or the successful assertions and remains a dependency-maintenance item.

## Artifact ledger

| Artifact | GitHub artifact digest |
| --- | --- |
| `production-frontend-2720a27f00e917e12103e735b0f88d74f1b286a2` | `sha256:5eb3babcbaed469f8f6d7fe151520b7f00561e1cb7060309bb343743cfa98c28` |
| `production-backend-2720a27f00e917e12103e735b0f88d74f1b286a2` | `sha256:fd6e1cfdb77de0af67778bf5c5a27446a62f1e0ce538ea47a669200a74a06832` |
| `production-deployment-2720a27f00e917e12103e735b0f88d74f1b286a2` | `sha256:f1534550d1504d2f748b4f6760580a276b689b7b32b94667d2e008dd32b8cbf6` |
| `browser-evidence-2720a27f00e917e12103e735b0f88d74f1b286a2` | `sha256:52c278dc2c787d49fcb1c3cd44416c1a6cb7f5469c293a7f18a44ade4ea7b599` |

The production archives also contain their own SHA-256 files generated in CI. No workflow publishes or deploys them automatically.

## Visual review

The accepted concepts and the following real browser surfaces were inspected at original screenshot resolution:

- public Overview at desktop 1440 and mobile 390;
- Officer sign-in at desktop 1440 and mobile 390;
- authenticated Overview at desktop 1440 and mobile 390;
- Administration at desktop 1440 and mobile 390;
- the complete 1280 screenshot set was captured and retained in the browser-evidence artifact.

The first inspected mobile run revealed a crowded topbar that wrapped `Officer sign-in` and `Sign out`. The responsive CSS now hides the redundant topbar system status below 620 px while retaining status in the footer, and prevents the session action from wrapping. Run `45420765109` recaptured and verified the corrected public and authenticated mobile topbars.

No horizontal clipping, overlapping controls, unreadable form state, broken table layout, or desktop regression was observed after that correction. The long mobile screenshots intentionally show the full page rather than only the initial viewport.

## Fidelity ledger

| Comparison point | Source implementation | Verified result |
| --- | --- | --- |
| App shell | `AppShell.tsx`, 224 px desktop sidebar, utility topbar, status rail | Desktop shell and mobile off-canvas entry render correctly |
| Overview hierarchy | `OverviewPage.tsx`, evidence line, mountain band, events, independent signals | Public and authenticated states captured at all three viewports |
| Admin anatomy | `AdminPage.tsx`, Player/Event modes, explicit labels, audit table | Real player/event mutations and audit rows captured |
| Mobile login | `LoginPage.tsx`, password reveal control, return action, security note | 390×844 project passed and full-page render inspected |
| Palette and type | CSS tokens in `styles.css` | Computed browser output matches the restrained Arctic palette and hierarchy |
| Container model | Open rails/tables with limited panel framing | No generic metric-card grid or fabricated chart/data was introduced |
| Responsive behavior | Off-canvas navigation, stacked overview/admin, responsive tables | Desktop 1440/1280 and mobile 390 projects passed without observed overflow |

## Copy review

The implementation preserves the accepted brand, page title, evidence status, foundation statement, actions, navigation labels, and login copy. Intentional product corrections remain:

- no invented player or event examples;
- contribution, attendance, and reliability remain independent;
- no fake chart, metric, score, or marketing claim;
- player and event records remain private until authenticated;
- only events currently have draft/published state.

## Not covered by this CI stage

Production deployment, public DNS/TLS, production administrator login, persistence across a production restart, production logs/resources, and the private baseline of unrelated host services were intentionally not tested or changed. They belong to the separately authorized deployment stage.
