CREATE TABLE calendar_cycle_series (
 id TEXT PRIMARY KEY,
 group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
 kind TEXT NOT NULL CHECK(kind IN ('canyon','foundry','svs')),
 owner_key TEXT NOT NULL,
 interval_days INTEGER NOT NULL CHECK(interval_days BETWEEN 1 AND 366),
 template_json TEXT NOT NULL,
 next_sequence INTEGER NOT NULL CHECK(next_sequence >= 2),
 status TEXT NOT NULL CHECK(status IN ('active','finite','stopped','conflict')),
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1)
);
CREATE UNIQUE INDEX idx_active_cycle_series_owner ON calendar_cycle_series(group_id,kind,owner_key) WHERE status IN ('active','conflict');
CREATE TABLE calendar_cycle_series_members (
 cycle_id TEXT PRIMARY KEY REFERENCES calendar_cycles(id) ON DELETE RESTRICT,
 series_id TEXT NOT NULL REFERENCES calendar_cycle_series(id) ON DELETE RESTRICT,
 sequence INTEGER NOT NULL CHECK(sequence>=0),
 UNIQUE(series_id,sequence)
);
