# Calendar v2.3a — reference stages and multi-day occurrence details

The pinned game catalog now exposes stage IDs, names and source notes. Week, month and agenda entries show a multi-day position and reference stage names where timing is unambiguous. Details offer stage selection, source notes and structured runs/phases.

The saved occurrence is the only schedule authority. Stage projection is read-only and estimated, never expands or rewrites the parent, never creates actual event records and never assigns unknown UTC times. Numeric daily stages require an explicit end and a date-only or midnight UTC start. Hall of Chief requires an explicit Season 1/2 phase; ambiguous variants are not projected. SvS preparation day 5 and Showdown final stage use the explicit extended-stage reference only when a timed anchor is available, clipped to the saved end. Date-only stays date-only.

Canyon battle remains its existing event type; reference voting, registration, matchmaking and battle phases are listed without guessing dates. Persisted multi-phase grouping and officer-reviewed cycle creation are a separate next increment, as is scoring/rewards. No migration or CI configuration changes.
