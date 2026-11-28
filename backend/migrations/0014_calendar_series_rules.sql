CREATE TABLE calendar_series_rules (series_id TEXT PRIMARY KEY REFERENCES calendar_series(id) ON DELETE CASCADE, rule_json TEXT NOT NULL);
