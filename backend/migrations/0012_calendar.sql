CREATE TABLE calendar_series (
 id TEXT PRIMARY KEY,
 group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
 interval_minutes INTEGER NOT NULL CHECK(interval_minutes BETWEEN 60 AND 525600),
 occurrence_count INTEGER NOT NULL CHECK(occurrence_count BETWEEN 2 AND 180),
 anchor TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(id, group_id)
);
CREATE UNIQUE INDEX idx_calendar_alliance_group ON alliances(id, group_id);
CREATE TABLE calendar_occurrences (
 id TEXT PRIMARY KEY,
 group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
 series_id TEXT,
 sequence INTEGER NOT NULL DEFAULT 0 CHECK(sequence >= 0),
 event_type TEXT NOT NULL,
 scope TEXT NOT NULL CHECK(scope IN ('alliance','state')),
 alliance_id TEXT,
 state_id TEXT NOT NULL,
 starts_at TEXT NOT NULL,
 ends_at TEXT,
 precision TEXT NOT NULL CHECK(precision IN ('date','minute')),
 phase TEXT NOT NULL DEFAULT '',
 confidence TEXT NOT NULL CHECK(confidence IN ('confirmed','estimated')),
 schedule_status TEXT NOT NULL DEFAULT 'scheduled' CHECK(schedule_status IN ('scheduled','cancelled')),
 source TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual','recurrence')),
 revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(series_id,group_id) REFERENCES calendar_series(id,group_id) ON DELETE RESTRICT,
 FOREIGN KEY(alliance_id,group_id) REFERENCES alliances(id,group_id) ON DELETE RESTRICT,
 CHECK((scope='alliance' AND alliance_id IS NOT NULL) OR (scope='state' AND alliance_id IS NULL)),
 CHECK(ends_at IS NULL OR ends_at > starts_at),
 UNIQUE(series_id,sequence)
);
CREATE INDEX idx_calendar_group_start ON calendar_occurrences(group_id,starts_at);

CREATE TABLE calendar_create_requests (
 group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
 request_key TEXT NOT NULL,
 payload_hash TEXT NOT NULL,
 occurrence_ids TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(group_id,request_key)
);
