CREATE TABLE alliance_groups (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  discord_server_id TEXT,
  combined_statistics INTEGER NOT NULL DEFAULT 0 CHECK(combined_statistics IN (0, 1)),
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'archived')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE alliances (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  tag TEXT NOT NULL,
  state_id TEXT NOT NULL,
  alliance_type TEXT NOT NULL CHECK(alliance_type IN ('primary', 'additional')),
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'archived')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_alliances_one_primary_per_group
  ON alliances(group_id) WHERE alliance_type = 'primary';
CREATE INDEX idx_alliances_group_status ON alliances(group_id, status, name COLLATE NOCASE);

CREATE TABLE alliance_sync_settings (
  alliance_id TEXT PRIMARY KEY REFERENCES alliances(id) ON DELETE CASCADE,
  whiteoutstats_alliance_id TEXT,
  sync_enabled INTEGER NOT NULL DEFAULT 0 CHECK(sync_enabled IN (0, 1)),
  sync_interval_minutes INTEGER CHECK(sync_interval_minutes IS NULL OR sync_interval_minutes >= 15),
  last_sync_at TEXT,
  last_sync_status TEXT CHECK(last_sync_status IN ('success', 'failed', 'partial')),
  last_sync_error TEXT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE player_group_profiles (
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
  primary_alliance_id TEXT REFERENCES alliances(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'unconfirmed' CHECK(status IN ('unconfirmed', 'active', 'archived')),
  source_type TEXT NOT NULL CHECK(source_type IN ('legacy_unconfirmed', 'manual', 'whiteoutstats', 'transition_rule')),
  source_note TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(player_fid, group_id)
);

CREATE INDEX idx_player_group_profiles_group_alliance
  ON player_group_profiles(group_id, primary_alliance_id, status);

CREATE TABLE player_nickname_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE CASCADE,
  group_id TEXT REFERENCES alliance_groups(id) ON DELETE RESTRICT,
  alliance_id TEXT REFERENCES alliances(id) ON DELETE RESTRICT,
  nickname TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK(source_type IN ('legacy', 'manual', 'whiteoutstats', 'ocr')),
  source_reference TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_nickname_observations_player_time
  ON player_nickname_observations(player_fid, observed_at DESC);

CREATE TABLE player_membership_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
  alliance_id TEXT NOT NULL REFERENCES alliances(id) ON DELETE RESTRICT,
  observed_at TEXT NOT NULL,
  source_type TEXT NOT NULL CHECK(source_type IN ('manual', 'whiteoutstats', 'ocr')),
  source_reference TEXT,
  confidence TEXT NOT NULL DEFAULT 'confirmed' CHECK(confidence IN ('confirmed', 'needs_review')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_membership_observations_player_group_time
  ON player_membership_observations(player_fid, group_id, observed_at DESC);

CREATE TABLE player_alliance_transitions (
  id TEXT PRIMARY KEY,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
  from_alliance_id TEXT REFERENCES alliances(id) ON DELETE RESTRICT,
  to_alliance_id TEXT REFERENCES alliances(id) ON DELETE RESTRICT,
  first_observed_at TEXT NOT NULL,
  classification TEXT NOT NULL CHECK(classification IN ('temporary_pending', 'permanent', 'manual_corrected', 'disputed')),
  classified_at TEXT,
  source_observation_id INTEGER REFERENCES player_membership_observations(id) ON DELETE RESTRICT,
  manual_note TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_player_transitions_group_player
  ON player_alliance_transitions(group_id, player_fid, first_observed_at DESC);

CREATE TABLE player_primary_alliance_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
  alliance_id TEXT REFERENCES alliances(id) ON DELETE RESTRICT,
  effective_observed_at TEXT NOT NULL,
  ended_observed_at TEXT,
  source_type TEXT NOT NULL CHECK(source_type IN ('legacy_unconfirmed', 'manual', 'transition_rule')),
  source_transition_id TEXT REFERENCES player_alliance_transitions(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK(ended_observed_at IS NULL OR ended_observed_at >= effective_observed_at)
);

CREATE INDEX idx_primary_alliance_history_player_group_time
  ON player_primary_alliance_history(player_fid, group_id, effective_observed_at DESC);

ALTER TABLE events ADD COLUMN alliance_id TEXT REFERENCES alliances(id) ON DELETE RESTRICT;
CREATE INDEX idx_events_alliance_occurred_on ON events(alliance_id, occurred_on DESC);

CREATE TABLE event_registrations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  registration_status TEXT NOT NULL CHECK(registration_status IN ('registered_main', 'registered_substitute', 'not_registered', 'no_duty', 'unknown')),
  source_type TEXT NOT NULL CHECK(source_type IN ('manual', 'ocr', 'legacy')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(event_id, player_fid)
);

CREATE TABLE event_attendance_assessments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  attendance_status TEXT NOT NULL CHECK(attendance_status IN ('confirmed_present', 'confirmed_absent', 'excused', 'no_duty', 'unknown')),
  source_complete INTEGER NOT NULL DEFAULT 0 CHECK(source_complete IN (0, 1)),
  source_type TEXT NOT NULL CHECK(source_type IN ('manual', 'ocr', 'legacy')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(event_id, player_fid)
);

CREATE TABLE event_result_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  metric_key TEXT NOT NULL,
  raw_value INTEGER CHECK(raw_value IS NULL OR raw_value >= 0),
  source_complete INTEGER NOT NULL DEFAULT 0 CHECK(source_complete IN (0, 1)),
  source_type TEXT NOT NULL CHECK(source_type IN ('manual', 'ocr', 'legacy')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(event_id, player_fid, metric_key)
);

CREATE INDEX idx_event_registrations_event ON event_registrations(event_id);
CREATE INDEX idx_event_attendance_event ON event_attendance_assessments(event_id);
CREATE INDEX idx_event_results_event_metric ON event_result_entries(event_id, metric_key);
