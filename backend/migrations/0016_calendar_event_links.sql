CREATE TABLE calendar_event_links (
 occurrence_id TEXT PRIMARY KEY REFERENCES calendar_occurrences(id) ON DELETE CASCADE,
 event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_calendar_event_links_event ON calendar_event_links(event_id);
