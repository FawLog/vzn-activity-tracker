CREATE TABLE state_calendar_profiles (
 state_id TEXT PRIMARY KEY,
 provider_opened_on TEXT,
 manual_opened_on TEXT,
 last_attempt_at TEXT,
 last_success_at TEXT,
 last_status TEXT CHECK(last_status IN ('success','failed','pending')),
 revision INTEGER NOT NULL DEFAULT 1
);
