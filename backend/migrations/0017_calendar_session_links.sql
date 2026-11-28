ALTER TABLE calendar_event_links ADD COLUMN session_id TEXT REFERENCES event_sessions(id) ON DELETE CASCADE;
CREATE UNIQUE INDEX idx_calendar_link_session ON calendar_event_links(session_id) WHERE session_id IS NOT NULL;
