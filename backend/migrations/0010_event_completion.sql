CREATE TABLE event_completion_roster (
 event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
 player_fid TEXT NOT NULL REFERENCES players(fid) ON DELETE RESTRICT,
 nickname TEXT NOT NULL,
 home_alliance_id TEXT REFERENCES alliances(id) ON DELETE RESTRICT,
 roster_member INTEGER NOT NULL CHECK(roster_member IN (0,1)),
 outcome TEXT NOT NULL CHECK(outcome IN ('positive','negative','excused','no_duty')),
 PRIMARY KEY(event_id,player_fid)
);
CREATE TABLE event_completion_reviews (
 event_id TEXT PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
 completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
