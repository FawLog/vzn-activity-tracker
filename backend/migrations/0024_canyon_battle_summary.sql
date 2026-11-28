-- Preserve all three Canyon team results and the reviewed report statistics.
ALTER TABLE foundry_session_details ADD COLUMN canyon_summary_json TEXT;
