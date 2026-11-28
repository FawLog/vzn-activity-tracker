# Calendar v2.1 — Game event catalog

The pinned whiteout-survival-data package is a game reference, not a state calendar. Build-time
projection uses the exact upstream events() registry (65 entries at 0.11.0), imports event artwork
when available, and exposes only schedule summaries, requirements, phases and coverage indicators.
It does not import the package root or require Node on production. Full scoring/rewards are deferred
to v2.4. No automatic schedules are generated here. The catalog is searchable from Calendar and
known existing event types have reference details. Unsupported calendar types remain unmapped.

Preserve absent fields. Do not equate category with scheduling scope or the Bear cooldown with an
alliance schedule. Source prose and structured rules can conflict (SvS preparation length and
extended fifth day); the catalog shows source data, and the next scheduling slice must resolve
conflicts explicitly before creating forecasts. Month and weekly rules must not be approximated as
fixed days. A version upgrade requires reviewing upstream membership and source changes; build
fails on unexpected version.

Next: anchor-based forecasting, then grouped phases and daily stages, then scoring and rewards.
No modifications to actual event records, analytics, migrations, CI/CD or production in v2.1.
