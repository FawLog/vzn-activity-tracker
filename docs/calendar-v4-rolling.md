# Calendar v4.2: rolling fixed-interval series

- Explicit opt-in persisted per new series; existing finite series are unchanged.
- The regular event form defaults to automatic renewal for eligible fixed intervals (at least one day, 2–60 initial occurrences). The user can disable it. Calendar-month and weekday series remain finite.
- Renewal runs at application startup and hourly, independently of WhiteoutStats. It materializes estimated occurrences up to 60 UTC days ahead. Existing manually confirmed, cancelled, linked, or edited rows are never overwritten.
- The immutable identity/duration template and independent next-start/sequence cursor are not inferred from the last displayed occurrence. Missed past dates are skipped, not backfilled. A single-occurrence edit is an exception. An explicit future-series shift moves the cursor; cancellation stops renewal.
- A matching date/time (including cancelled entries and date-only ambiguity) pauses the series with a visible conflict status rather than silently duplicating or overwriting records. Existing entries remain intact. Resume/reconciliation controls are future work; the current recovery is reviewing the existing schedule and creating a non-conflicting replacement.
- Renewal is transactional per series, scoped to active groups and active matching alliance/state ownership, uses the existing unique series/sequence constraint, and never creates events, sessions, results or attendance. No paid API or deployment-control changes.
