CREATE TABLE calendar_cycles (
 id TEXT PRIMARY KEY,
 group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
 kind TEXT NOT NULL CHECK(kind IN ('canyon','svs')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(id,group_id)
);
ALTER TABLE calendar_occurrences ADD COLUMN cycle_id TEXT REFERENCES calendar_cycles(id) ON DELETE RESTRICT;
CREATE INDEX idx_calendar_cycle ON calendar_occurrences(group_id,cycle_id);
