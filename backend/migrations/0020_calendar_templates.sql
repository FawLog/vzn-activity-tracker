CREATE TABLE calendar_templates (
 id TEXT PRIMARY KEY,
 group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
 alliance_id TEXT NOT NULL,
 name TEXT NOT NULL,
 schedule_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(alliance_id,group_id) REFERENCES alliances(id,group_id) ON DELETE RESTRICT
);
CREATE INDEX idx_calendar_templates_group_alliance ON calendar_templates(group_id,alliance_id);
