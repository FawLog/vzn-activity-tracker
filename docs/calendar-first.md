# Calendar-first workflow

Accepted direction: Calendar is the primary officer workspace; Events remains a historical/audit fallback. Schedule, actual event, session and evidence stay separate in storage. Do not materialize empty events when forecasting or opening a schedule. Use shared existing OCR, roster review, publication and analytics services.

## Delivery
- v3.6: embed existing editor for linked records and explicit session selection, refresh evidence status after saves; retain explicit creation/link controls for now.
- v3.7: lazy creation at first explicit data-entry action, atomic links, no duplicate drafts, no write on open.
- v3.8: explicit reviewed Bear cycle/legion grouping and ambiguity resolution; no date-only Bear grouping.
- v3.9: Event History and navigation; preserve historical imports and corrections.
- v3.10: final integration verification before v4.

This PR does not introduce new OCR parsers or change analytics. Multi-session events must have a session link before opening the embedded editor. Creating/deleting sessions in the embedded editor is intentionally disabled; existing schedule controls and history remain available. Existing session tabs and final review still operate across the parent event. Local calendar controls are disabled during unsaved changes or busy operations; global app navigation is not yet guarded. Archived workspace editing is not enabled. No backend/schema/CI changes.
