ALTER TABLE event_sessions ADD COLUMN host_alliance_id TEXT REFERENCES alliances(id) ON DELETE RESTRICT;
UPDATE event_sessions SET host_alliance_id=(SELECT alliance_id FROM events WHERE events.id=event_sessions.event_id);
CREATE INDEX idx_event_session_hosts ON event_sessions(host_alliance_id);
