ALTER TABLE calendar_occurrences ADD COLUMN entry_cycle_date TEXT;
ALTER TABLE calendar_occurrences ADD COLUMN entry_session_key TEXT;
CREATE UNIQUE INDEX idx_calendar_bear_group_session ON calendar_occurrences(group_id,entry_cycle_date,entry_session_key) WHERE event_type='bear_trap' AND entry_cycle_date IS NOT NULL;
CREATE UNIQUE INDEX idx_calendar_legion_group_session ON calendar_occurrences(group_id,alliance_id,event_type,entry_cycle_date,entry_session_key) WHERE event_type IN ('foundry','canyon') AND entry_cycle_date IS NOT NULL;
