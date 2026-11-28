# Calendar v2.2a — anchored fixed-interval forecast

Stacked on v2.1 (PR 48); no merge is implicit. Use the existing calendar series API with exact
minute intervals (including user-selected fractional hours). The officer supplies the first
occurrence, owner, precision, optional end, count and local repeat pattern, then reviews every
generated date. A reference rule is only a suggestion; the first occurrence uses explicit confidence
and all later copies are estimated. No time, end date or state start date is inferred. State start
date is optional and used only for a local warning against the upstream server-timeline unlock day.
No age is persisted or invented. Multi-run events use the repeat rule only, not automatic phase
creation. Conflicting SvS/Showdown duration and Castle/SvS rotation are explicitly flagged.

The existing transaction rejects exact duplicate starts (or ambiguous date-only starts on the same
day) for the same owner, event and phase in new recurring plans, including cancelled entries. This
is not a general overlap detector; different known times or phases can coexist. Prior idempotent
request hashes are unchanged. Existing schedules are never modified by forecast creation.

Monthly and multi-weekday rules cannot safely be represented by the v1 fixed-interval series schema.
They are not converted to 30 days or guessed. Bear cooldown is not a game repeat suggestion;
officers can explicitly set their own cadence. The first slice supports calendar event types already
supported by v1; expanding to all catalog-only types, variable rules, durable per-state anchor/age
profiles and automated cross-event rotation reconciliation require the next slice. No migration,
actual event records, analytics, CI/CD or production changes.
