CREATE TABLE players (
  fid TEXT PRIMARY KEY,
  nickname TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE player_nicknames (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE CASCADE,
  nickname TEXT NOT NULL,
  valid_from TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  valid_to TEXT
);

CREATE TABLE player_memberships (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE CASCADE,
  joined_on TEXT NOT NULL,
  left_on TEXT,
  CHECK(left_on IS NULL OR left_on >= joined_on)
);

CREATE TABLE events (
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  occurred_on TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'published')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE event_participants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  presence_status TEXT NOT NULL CHECK(
    presence_status IN ('confirmed_present', 'confirmed_absent', 'excused', 'unknown')
  ),
  roster_role TEXT CHECK(roster_role IN ('main', 'substitute', 'unregistered')),
  raw_points INTEGER CHECK(raw_points IS NULL OR raw_points >= 0),
  source_complete INTEGER NOT NULL DEFAULT 0 CHECK(source_complete IN (0, 1)),
  UNIQUE(event_id, player_fid)
);

CREATE TABLE admin_sessions (
  token_hash TEXT PRIMARY KEY,
  csrf_token TEXT NOT NULL,
  is_authenticated INTEGER NOT NULL DEFAULT 0 CHECK(is_authenticated IN (0, 1)),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL
);

CREATE TABLE login_attempts (
  client_key TEXT PRIMARY KEY,
  failure_count INTEGER NOT NULL,
  window_started_at INTEGER NOT NULL,
  blocked_until INTEGER
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  actor TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_occurred_on ON events(occurred_on DESC);
CREATE INDEX idx_events_status ON events(status);
CREATE INDEX idx_audit_created_at ON audit_log(created_at DESC);
CREATE INDEX idx_sessions_expires_at ON admin_sessions(expires_at);
