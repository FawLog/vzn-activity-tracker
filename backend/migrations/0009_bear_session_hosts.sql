ALTER TABLE event_sessions ADD COLUMN host_alliance_id TEXT REFERENCES alliances(id) ON DELETE RESTRICT;
UPDATE event_sessions SET host_alliance_id=(SELECT alliance_id FROM events WHERE events.id=event_sessions.event_id);
CREATE INDEX idx_event_session_hosts ON event_sessions(host_alliance_id);

ALTER TABLE events ADD COLUMN bear_cycle_complete INTEGER NOT NULL DEFAULT 0 CHECK(bear_cycle_complete IN (0,1));
