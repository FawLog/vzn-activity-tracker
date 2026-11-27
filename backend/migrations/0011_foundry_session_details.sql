-- Independent reviewed battle metadata; existing event records remain unchanged.
CREATE TABLE foundry_session_details (
  session_id TEXT PRIMARY KEY REFERENCES event_sessions(id) ON DELETE CASCADE,
  main_count INTEGER CHECK(main_count BETWEEN 0 AND 30),
  substitute_count INTEGER CHECK(substitute_count BETWEEN 0 AND 10),
  outcome TEXT CHECK(outcome IN ('victory','defeat')),
  own_score INTEGER CHECK(own_score >= 0),
  opponent_score INTEGER CHECK(opponent_score >= 0),
  opponent_tag TEXT,
  opponent_name TEXT,
  opponent_state TEXT
);
