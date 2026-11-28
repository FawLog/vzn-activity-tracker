CREATE TABLE calendar_follow_rules (
 id TEXT PRIMARY KEY,
 group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
 state_id TEXT NOT NULL,
 event_type TEXT NOT NULL CHECK(event_type IN ('game:flame-and-fang','game:crystal-reactivation-2')),
 starts_on TEXT NOT NULL,
 stopped_on TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK(stopped_on IS NULL OR stopped_on>=starts_on)
);
CREATE UNIQUE INDEX idx_active_calendar_follow ON calendar_follow_rules(group_id,state_id,event_type) WHERE stopped_on IS NULL;
