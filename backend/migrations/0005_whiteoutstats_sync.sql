-- WhiteoutStats integration state.  External observations are deliberately
-- scoped to a VZN group/alliance and do not change historical event ownership.
ALTER TABLE alliance_sync_settings ADD COLUMN last_attempt_at TEXT;
ALTER TABLE alliance_sync_settings ADD COLUMN last_manual_sync_at TEXT;
ALTER TABLE alliance_sync_settings ADD COLUMN sync_in_progress_at TEXT;
ALTER TABLE alliance_sync_settings ADD COLUMN next_retry_at TEXT;
ALTER TABLE alliance_sync_settings ADD COLUMN last_found_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE alliance_sync_settings ADD COLUMN last_added_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE alliance_sync_settings ADD COLUMN last_updated_count INTEGER NOT NULL DEFAULT 0;

CREATE TABLE player_whiteoutstats_profiles (
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
  uid TEXT,
  power INTEGER CHECK(power IS NULL OR power >= 0),
  kills INTEGER CHECK(kills IS NULL OR kills >= 0),
  furnace_level INTEGER CHECK(furnace_level IS NULL OR furnace_level >= 0),
  alliance_rank TEXT,
  state_id TEXT,
  avatar_url TEXT,
  observed_at TEXT NOT NULL,
  received_at TEXT NOT NULL,
  source_alliance_id TEXT REFERENCES alliances(id) ON DELETE RESTRICT,
  PRIMARY KEY (player_fid, group_id)
);

CREATE TABLE player_game_stat_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
  alliance_id TEXT NOT NULL REFERENCES alliances(id) ON DELETE RESTRICT,
  uid TEXT,
  power INTEGER CHECK(power IS NULL OR power >= 0),
  kills INTEGER CHECK(kills IS NULL OR kills >= 0),
  furnace_level INTEGER CHECK(furnace_level IS NULL OR furnace_level >= 0),
  alliance_rank TEXT,
  state_id TEXT,
  source_observed_at TEXT NOT NULL,
  received_at TEXT NOT NULL,
  UNIQUE(alliance_id, player_fid, source_observed_at)
);
CREATE INDEX idx_player_game_stat_history ON player_game_stat_snapshots(group_id, player_fid, source_observed_at DESC);

CREATE TABLE alliance_stat_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alliance_id TEXT NOT NULL REFERENCES alliances(id) ON DELETE RESTRICT,
  group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
  external_aid TEXT,
  external_name TEXT,
  external_tag TEXT,
  state_id TEXT,
  power INTEGER CHECK(power IS NULL OR power >= 0),
  member_count INTEGER CHECK(member_count IS NULL OR member_count >= 0),
  power_rank INTEGER CHECK(power_rank IS NULL OR power_rank >= 0),
  leader_name TEXT,
  leader_fid TEXT,
  flag_url TEXT,
  source_observed_at TEXT NOT NULL,
  received_at TEXT NOT NULL,
  UNIQUE(alliance_id, source_observed_at)
);
CREATE INDEX idx_alliance_stat_history ON alliance_stat_snapshots(alliance_id, source_observed_at DESC);

CREATE TABLE alliance_roster_snapshot_members (
  alliance_snapshot_id INTEGER NOT NULL REFERENCES alliance_stat_snapshots(id) ON DELETE CASCADE,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  PRIMARY KEY(alliance_snapshot_id, player_fid)
);

CREATE TABLE player_roster_absence_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
  group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
  alliance_id TEXT NOT NULL REFERENCES alliances(id) ON DELETE RESTRICT,
  alliance_snapshot_id INTEGER NOT NULL REFERENCES alliance_stat_snapshots(id) ON DELETE CASCADE,
  observed_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(player_fid, alliance_snapshot_id)
);
CREATE INDEX idx_roster_absence_player ON player_roster_absence_observations(group_id, player_fid, observed_at DESC);

CREATE TABLE alliance_sync_runs (
  id TEXT PRIMARY KEY,
  alliance_id TEXT NOT NULL REFERENCES alliances(id) ON DELETE CASCADE,
  requested_at TEXT NOT NULL,
  completed_at TEXT,
  trigger_type TEXT NOT NULL CHECK(trigger_type IN ('initial', 'manual', 'scheduled')),
  status TEXT NOT NULL CHECK(status IN ('running', 'success', 'partial', 'failed', 'rate_limited')),
  found_count INTEGER NOT NULL DEFAULT 0,
  added_count INTEGER NOT NULL DEFAULT 0,
  updated_count INTEGER NOT NULL DEFAULT 0,
  message TEXT
);
CREATE INDEX idx_alliance_sync_runs_recent ON alliance_sync_runs(alliance_id, requested_at DESC);
