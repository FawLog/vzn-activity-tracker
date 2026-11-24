# Visual and functional QA status

## Design references inspected

The following accepted concepts were inspected at original resolution with `view_image` during implementation:

- `docs/concepts/overview-desktop.png`
- `docs/concepts/admin-desktop.png`
- `docs/concepts/login-mobile.png`
- `frontend/public/assets/arctic-range.png`

## Fidelity ledger

| Comparison point | Concept evidence | Source implementation | Status |
| --- | --- | --- | --- |
| App shell | Narrow dark sidebar, 58–60 px utility bar, bottom status rail | `AppShell.tsx`, 224 px sidebar, 58 px topbar, 36 px statusbar | Implemented in source; render not yet captured |
| Overview hierarchy | Page title, evidence line, mountain foundation band, event table, three independent signals | `OverviewPage.tsx` and responsive grid/band styles | Implemented in source; render not yet captured |
| Admin anatomy | Player/Event modes, explicit labels, strong focus, form rail plus audit table | `AdminPage.tsx` with real API-backed forms and audit list | Implemented in source; render not yet captured |
| Mobile login | Brand, system state, large sign-in heading, password control, return action, security note | `LoginPage.tsx` and 620 px responsive rules | Implemented in source; 390×844 render not yet captured |
| Palette and type | Midnight navy, graphite, steel-blue rules, ice cyan, warm off-white, compact grotesk type | CSS tokens in `styles.css` and documented values in `DESIGN_SYSTEM.md` | Source values locked; computed browser values not yet inspected |
| Icon treatment | Consistent thin/medium outlined navigation and control icons | Lucide icons at 1.5–1.8 stroke and controlled sizes | Implemented in source; optical alignment awaits browser review |
| Container model | Open bands, rails and tables; very limited panel framing | No bento/card metric grid; tables remain tables | Implemented in source |
| Responsive behavior | Desktop shell and standalone 390×844 login | Off-canvas navigation, stacked overview, scrollable tables, mobile login rules | Implemented in source; browser overflow checks pending |

## Above-the-fold copy review

The implementation preserves the accepted brand, page title, evidence status, core foundation statement, actions, navigation labels, and login copy. Intentional deviations from ImageGen copy are product corrections:

- Removed the invented `KE` example.
- Replaced generic “troop dispatch/tasks” signal copy with the agreed contribution/attendance/reliability definitions.
- Removed help, notification, and avatar controls because they have no foundation-release workflow.
- Did not claim that player records are drafts; only events currently have draft/published state.

No hero eyebrow, marketing claim, fake metric, fake player, or fake chart was added.

## Checks completed in the VPS session

- Python source parsed successfully with `ast`.
- Shell script syntax passed `bash -n`.
- JSON configuration parsed successfully.
- Git staged diff passed `git diff --cached --check`.
- No secret, private key, `.env`, or SQLite file was staged.
- All design concepts and the production image asset were inspected with `view_image`.

## Checks intentionally not run on production

The current Codex session runs on the production VPS. In accordance with the project constraints, it does not install frontend dependencies, run Vite builds, build Docker images, launch Chromium/Playwright, or start a development frontend on this host.

`.github/workflows/ci.yml` now prepares a complete GitHub-hosted Ubuntu run with TypeScript, Vitest, Vite, pytest, migration checks, Docker build/smoke test, Chromium, and real browser screenshots at 1440×900, 1280×800, and 390×844. None of those results is claimed until an approved private repository runs the workflow and its artifacts are inspected beside the accepted concepts. The external execution status and artifact identifiers must be appended here after that run.
