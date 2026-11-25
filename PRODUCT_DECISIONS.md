# VZN Activity Tracker — product decisions

## Purpose and release boundary

VZN Activity Tracker is an independent service for alliance officers and, later, authenticated members. It has no integration with unrelated host applications. Officers must review screenshot/OCR imports before publication. Private officer notes must never be public.

Foundation v0.1 includes authentication, pages, the database, FID-based manual player creation, simple manual event creation, and audit records. It contains no OCR, screenshot import, public personal records, Discord OAuth, or real analytics. Do not describe this release as a finished tracker.

## Event treatment

- **SvS Preparation:** store raw individual points, grounded alliance/state totals, event history, and relative shares only when denominators are complete. No individual target or equalization.
- **Alliance Mobilization / Alliance Showdown:** store raw points and participation over time. No quotas or individual targets.
- **Foundry / Canyon:** keep legions, registration vs attendance, main vs substitute, and evidence completeness separate. Registered-but-absent is more serious than not registered. Registered substitutes must enter independently; confirmed absence is a no-show for both main and substitute players. Positive points prove scored activity but are not a proportional effectiveness measure. Zero points or missing rank are treated identically for both roles; incomplete evidence stays unknown, and zero alone does not prove absence. Preserve officer-added vs player-affirmed registration when evidence supports it.
- **Bear Trap:** attendance consistency is primary. Damage is informational and cannot determine a performance score.
- **Alliance Championship:** registration only; automated battle outcome does not indicate individual commitment.
- **Winter Siege:** registration first; confirmed participation only when evidence distinguishes it from passive defensive points.
- **SvS Battle / Castle:** officer-only notes; optional top-N points are informational and cannot penalize unlisted players.
- **Fortress / Stronghold:** optional participation without extensive garrison tracking.
- **Crazy Joe / Alliance Contribution:** excluded from mandatory scoring.

## Non-negotiable data principles

- Contribution, attendance regularity, and reliability after registration remain independent. No universal usefulness score in v1.
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
