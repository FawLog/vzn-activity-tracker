# VZN Activity Tracker — product decisions

## Purpose and release boundary

VZN Activity Tracker is an independent service for alliance officers and, later, authenticated members. It has no integration with unrelated host applications. Officers must review screenshot/OCR imports before publication. Private officer notes must never be public.

Foundation v0.1 includes authentication, pages, the database, FID-based manual player creation, simple manual event creation, and audit records. It contains no OCR, screenshot import, public personal records, Discord OAuth, or real analytics. Do not describe this release as a finished tracker.

## Event treatment

- **SvS Preparation:** store raw individual points, grounded alliance/state totals, event history, and relative shares only when denominators are complete. No individual target or equalization.
- **Alliance Mobilization / Alliance Showdown:** store raw points and participation over time. No quotas or individual targets.
- **Foundry / Canyon:** keep legions, registration vs attendance, main vs substitute, and evidence completeness separate. Registered-but-absent is more serious than not registered. Registered substitutes must enter independently; confirmed absence is a no-show for both main and substitute players. Positive points prove scored activity but are not a proportional effectiveness measure. Both roles follow identical attendance rules. For Foundry, a reviewed explicit zero personal Arsenal Points is a no-show for a selected player unless excused/no-duty; a missing score remains unknown. Canyon retains its previous evidence rules until separately approved. Preserve officer-added vs player-affirmed registration when evidence supports it.
- **Bear Trap:** attendance consistency is primary. Damage is informational and cannot determine a performance score.
- **Alliance Championship:** registration only; automated battle outcome does not indicate individual commitment.
- **Winter Siege:** registration first; confirmed participation only when evidence distinguishes it from passive defensive points.
- **SvS Battle / Castle:** officer-only notes; optional top-N points are informational and cannot penalize unlisted players.
- **Fortress / Stronghold:** optional participation without extensive garrison tracking.
- **Crazy Joe / Alliance Contribution:** excluded from mandatory scoring.

## Non-negotiable data principles

- Contribution, attendance regularity, and reliability after registration remain independent. No universal usefulness score. Officer-approved Overall Activity is an advisory screening index only, never an automated kick decision.
- Confirmed presence, confirmed absence, excused/no duty, and unknown/incomplete evidence remain distinct.
- Missing from top-N does not mean zero.
- FID is the primary identity. Preserve nickname history, membership intervals, and event-date roster snapshots.
- Preserve original evidence, parsing version, OCR confidence, manual corrections, author, and timestamps when uploads are implemented.
- Never add raw points from unlike event types.
- Private officer notes are attributed and auditable.
- Never promise complete attendance analysis from partial roster/result screens.

## Delivery order

0. Foundation: domain, HTTPS, admin, pages, database, independent deployment.
1. Roster and manual entry: identity history, event editor, manual results, published reports.
2. Review-first raw-score OCR for SvS Preparation, Mobilization, and Showdown.
3. Attendance OCR for Foundry/Canyon and Bear with substitute/zero-point handling.
4. Optional events and officer notes.
5. Discord OAuth2 and role mapping before multiple officers can edit.

## Manual entry UX

Load the current alliance roster automatically as unconfirmed candidates, not historical proof. Officers can paste exact names or FIDs and tab-separated scores; ambiguous or unmatched entries require correction. Championship records registration only in the UI. Technical completeness and eligibility controls belong in a review step, not ordinary entry. Only explicit historical roster and evidence confirmation permit negative assessments. Preserve existing hidden metrics and do not infer absence from zero or missing score alone.

## OCR initial scope

Bear Hunt, Alliance Championship and Alliance Mobilization first. Foundry and Canyon automated parsing deferred until actual registration and results mail examples are available. English and Russian labels are supported on a best-effort basis; localized layouts and unrecognized labels require review. Never assume the screenshot is complete. Mobilization podium and ordinary ranking rows must be separated; preserve the mission ratio in preview, import completed missions and points only. No inferred absence from OCR.

## Analytics v1

Only published session evidence contributes. Date range is inclusive, max 366 days, alliance scoped; player history may span alliances in the same group. Current roster is display context, never a historical denominator. Registration and attendance counts distinguish positive, negative, excused, unknown; percentages are known eligible outcomes only and paired with coverage counts. Missing rows are not absences, and no-duty is excluded. Bear cycle is one event: present if either trap confirms presence, absent only when both traps explicitly confirm eligible absence, otherwise unknown (both excused/no-duty is excused). Foundry/Canyon reliability is per registered legion, independent of registration rate and raw points. Mobilization scores are observed samples, not a measure of attendance; no cross-type point sums. Legacy events without session evidence remain visible as uncovered events, not invented statistics. Raw metric totals use decimal strings to preserve integer precision. Draft/reopened/deleted events are excluded immediately. No cached materialized rankings or new migrations in this phase.

## Group Bear cycles
New Bear events are anchored to the active primary alliance, one per group/date; each trap has its own active host alliance, up to 30 traps. Existing records are not merged or deleted. Group trap numbers are independent of the local in-game trap number. Historical home alliance is derived only from observed primary-alliance intervals, never from current membership or host. Unknown historical homes are included in group analytics only. Attendance is once per cycle; absence requires explicit evidence for every recorded trap (and at least the original two slots); incomplete cycles remain unknown. Additional trap planning/completeness and historical roster correction need further UI support before negative attendance can be treated as exhaustive.

Bear cycle completeness is explicitly confirmed at publication. Legacy cycles default to incomplete; positive attendance counts, negative cycle outcomes remain unknown until complete. Date-only historical attribution excludes same-day newly observed memberships rather than guessing intra-day affiliation.

## Officer-attested automatic attendance
An explicit final review snapshots the selected event-date roster and all actual session attendees. Missing eligible roster members become absent; excused/no-duty are explicit exceptions. Bear uses all expected traps across hosts, Foundry/Canyon both legions. Registered legion no-shows remain distinct from event attendance. Partial publication preserves unknown. Reopening removes the event from analytics and retains the prior review as a starting point; final publication recomputes the snapshot, partial publication clears it. Current roster is only a proposed starting point; officer verifies historical membership. Future event kinds are not enabled by this change.

## Overall Activity screening (officer-approved)
Overall is the default Rankings view for active current members in the selected scope. It is an advisory index, not a measure of worth, and never triggers sanctions. Attendance 50%, recorded contribution 30%, registered reliability 20%; renormalize over available dimensions and display effective weight and provisional coverage. Attendance combines known event attendance and Championship registration; excused/no duty and unknown are excluded. Registered no-shows also reduce reliability. Contribution uses per-event midrank percentile of recorded Mobilization points among recorded peers, averages across events, preserves explicit zero, and labels incomplete peer lists provisional. No Bear damage, Foundry/Canyon points, power or spending in the index. SvS and Showdown are not yet supported. Missing events remain unobserved, never absences, including for new joiners. Last activity includes confirmed registration, attendance or positive recorded contribution. A score with limited evidence is labeled provisional, no evidence is unscored. Current membership limits the screening list, not historical eligibility. Keep individual rankings available. No schema change.

Group Bear final review proposes active members of every recorded host alliance, with historical homes preferred; officers must verify event-date eligibility. A missing historical home requires explicit officer assignment for eligible players; known historical homes cannot be overridden by the request. Non-attendees in the confirmed roster of either host are absent unless excused/no-duty. Reopen and finalize again to repair an earlier incomplete roster; prior exceptions and session evidence remain available. Overview scope permits every active alliance separately or the whole group.

## Foundry Battle registration and results workflow (approved November 27, 2026)

- One event dated on the Sunday of the battle, with Legion 1 and Legion 2. Thursday selection mail and Sunday results are independent saved draft stages per legion; both may be imported on Sunday. No automatic publication. One reusable screenshot loader with explicit registration/results mode and separate parsers. Do not classify a mixed batch automatically.
- Registration mail: selected Combatants (main) and Substitutes, not all applicants. Read section counts, validate unique FIDs per role against the mail, review ambiguous sections and matches. Do not interpret matchmaking power or alliance rank as personal points. Results mail: Personal Arsenal Points including explicit zero, exclude Legion Tally/MVP; parse outcome, opponent tag/name/state, team scores independently. Overlapping pages deduplicate by FID; conflicts and changed nicknames require review, including historical aliases. Unknown or missing is never zero. No production import of historical sample mail.
- Both completed legions and an officer-attested historical alliance roster are required to finalize event-wide negative outcomes. Event registration is positive if selected for either legion, negative if confirmed eligible and selected for neither. Attendance is one outcome per event: positive if any legion has positive points, missed if neither and complete evidence. No-show is a separate per-selected-legion failure; explicit zero counts as absence even if physically present. Excused/no-duty are explicit overrides; partial evidence must not turn missing players into absences. A player attending one legion is not penalized for being unselected in the other, but any actual second commitment failure is retained. Distinguish missed without registration, missed with no-show, and unknown registration. Preserve registered author when known; do not infer self-registration from selection mail.
- Overall weights stay 50/30/20: event attendance affects attendance, registered-legion no-show affects reliability as well. Points, match outcome and win rate are informational only. Show NR/NS and per-event registration/attendance, separate reliability. Rates exclude excused/no-duty/unknown. Count victories and defeats per verified legion, not per event; unknown outcomes excluded from win-rate denominator; report by period and alliance scope. Store battle outcome/score/opponent per session in an additive migration, never change previous migrations.
- Test explicit zero vs missing, both roles, cross-legion attendance, partial reports, duplicates, conflicting OCR, renamed players, and independent results. Existing Bear/Canyon semantics and privileged deployment controls unchanged. All merges use explicit squash; all six CI jobs must succeed before merge.

- Clarification: the game permits selection into only one Foundry legion per cycle (owner-confirmed). The defensive cross-legion deduplication remains for inconsistent imported evidence; it is not an expected gameplay scenario. Once both registration lists are saved and verified, show an automatic draft registration breakdown against the proposed event-date roster: selected in either = registered, absent from both = not registered, otherwise unknown. No manual marking of ordinary unregistered members. Officer reviews only roster exceptions and completeness; draft preview does not enter published analytics. The final review persists historical event attendance after both results are complete.

- Foundry registration accepts either the selection mail or the final in-game Legion 1/2 Combatants dialog in the same registration uploader. Detect the dialog from its title; verify the legion, Join/30 and Substitute/10 counts, Troop Power and Participants only footer. Read Join as main and Substitute as substitute per player, regardless of rank grouping; Voted and troop power are not registration origin or points. Ignore clipped/unreadable rows with warnings. Deduplicate by FID and review role/count conflicts. Officers should capture the final selection after registration closes, with Participants only enabled and overlapping pages; dialog has no event date, so verify the event manually. Either format may be used for either legion. No changes to attendance, reliability, migration or deployment policy.

- Foundry in-game registration: troop power is optional, never a prerequisite for extracting an otherwise unambiguous nickname and Join/Substitute role. Preserve card boundaries and reject ambiguous/clipped nicknames; role counts and FID review remain mandatory.
