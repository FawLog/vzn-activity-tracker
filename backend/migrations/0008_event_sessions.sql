-- Session-level manual records; legacy event records remain untouched.
CREATE TABLE event_sessions (
  id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  session_key TEXT NOT NULL,
  started_at TEXT NOT NULL,
  roster_complete INTEGER NOT NULL DEFAULT 0 CHECK(roster_complete IN (0,1)),
  registration_complete INTEGER NOT NULL DEFAULT 0 CHECK(registration_complete IN (0,1)),
  attendance_complete INTEGER NOT NULL DEFAULT 0 CHECK(attendance_complete IN (0,1)),
  results_complete INTEGER NOT NULL DEFAULT 0 CHECK(results_complete IN (0,1)),
  revision INTEGER NOT NULL DEFAULT 0,
  UNIQUE(event_id, session_key)
);
CREATE TABLE event_session_roster (
  session_id TEXT NOT NULL REFERENCES event_sessions(id) ON DELETE CASCADE,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  nickname TEXT NOT NULL,
  eligibility TEXT NOT NULL CHECK(eligibility IN ('confirmed','unknown','no_duty')),
  registration TEXT NOT NULL CHECK(registration IN ('registered','not_registered','excused','unknown')),
  role TEXT CHECK(role IN ('main','substitute')),
  registered_by TEXT CHECK(registered_by IN ('player','officer','unknown')),
  attendance TEXT NOT NULL CHECK(attendance IN ('confirmed_present','confirmed_absent','excused','no_duty','unknown')),
  PRIMARY KEY(session_id, player_fid)
);
CREATE TABLE event_session_metrics (
  session_id TEXT NOT NULL,
  player_fid TEXT NOT NULL,
  metric_key TEXT NOT NULL,
  raw_value INTEGER NOT NULL CHECK(raw_value >= 0),
  PRIMARY KEY(session_id, player_fid, metric_key),
  FOREIGN KEY(session_id, player_fid) REFERENCES event_session_roster(session_id, player_fid) ON DELETE CASCADE
);
