CREATE TABLE calendar_rolling_series (
 series_id TEXT PRIMARY KEY REFERENCES calendar_series(id) ON DELETE CASCADE,
 template_json TEXT NOT NULL,
 next_start TEXT NOT NULL,
 next_sequence INTEGER NOT NULL CHECK(next_sequence >= 2),
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','stopped','conflict'))
);
