# VZN Arctic Intelligence design system

## Accepted references

- `docs/concepts/overview-desktop.png` — primary 1440×900 operational workspace.
- `docs/concepts/admin-desktop.png` — form, table, and audit anatomy.
- `docs/concepts/login-mobile.png` — 390×844 authentication composition.
- `frontend/public/assets/arctic-range.png` — standalone production background asset.

These images are visual specifications, not shipped UI screenshots. Navigation, tables, forms, labels, and data remain code-native.

## Visual direction

The product is a restrained arctic intelligence workspace: tactical precision without cyberpunk spectacle. The defining motifs are a narrow operations rail, open data surfaces with precise dividers, a quiet mountain horizon, small factual status signals, and disciplined compact typography.

## Tokens

| Role | Value |
| --- | --- |
| App background | `#07111c` |
| Deep background | `#040c15` |
| Sidebar | `#081522` |
| Surface | `#0c1a29` |
| Raised surface | `#102235` |
| Border | `#29445b` |
| Main text | `#f1f0eb` |
| Secondary text | `#b7c8d8` |
| Muted text | `#7f97ab` |
| Action cyan | `#72d9f1` |
| Focus cyan | `#35dcf3` |
| Confirmed | `#59dda8` |
| Attention | `#f0b96a` |
| Confirmed problem | `#ef7f87` |

Green is only for confirmed success/presence, amber for attention/draft, red for confirmed errors/problems, and gray for unknown/unavailable. Color cannot substitute for text.

## Typography

Use Inter when installed, then Segoe UI Variable/Segoe UI/system sans. Headings are compact, 700–780 weight, with slightly negative tracking. Body copy is 11–15 px depending on context. Controls define their own type size and weight; browser defaults are never relied upon. Identifiers use a monospace stack.

## Layout and components

- Desktop app rail: 224 px.
- Utility topbar: 58 px; status bar: 36 px.
- Main content max width: 1280 px with 28 px desktop gutters.
- Surfaces use 1 px steel-blue dividers and 6–13 px radii. Avoid nested cards.
- Tables are the primary representation for records; do not transform record sets into card grids.
- Buttons: cyan filled primary, steel outlined secondary, compact quiet variant.
- Status labels: compact rectangular labels, not decorative pill collections.
- Empty states state what is missing and what action is valid; they never seed fake metrics.
- Icons use the Lucide family at 1.5–1.8 stroke weight and 16–22 px optical sizes.

## Responsive rules

At 820 px, the sidebar becomes an off-canvas navigation drawer. At 620 px, page actions become full-width, tables remain horizontally scrollable, and the overview banner stacks its image below its copy. Login removes the application rail and follows the accepted 390×844 composition with touch targets at least 44 px high.

## Motion

Motion is limited to navigation drawer transitions, hover/focus feedback, and a loading rail. `prefers-reduced-motion` reduces all non-essential motion.

## Content rules

No marketing hero, fake player, fake score, decorative metric, universal rating, or inferred absence. Above the fold, only the brand, operational page title, evidence status, verified-record foundation message, and available actions may appear.
