-- Rebuild the parent with an expanded CHECK while preserving all child links.
CREATE TEMP TABLE saved_cycle_links AS SELECT id,cycle_id FROM calendar_occurrences WHERE cycle_id IS NOT NULL;
UPDATE calendar_occurrences SET cycle_id=NULL WHERE cycle_id IS NOT NULL;
CREATE TABLE calendar_cycles_new (
 id TEXT PRIMARY KEY,
 group_id TEXT NOT NULL REFERENCES alliance_groups(id) ON DELETE RESTRICT,
 kind TEXT NOT NULL CHECK(kind IN ('canyon','svs','foundry')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(id,group_id)
);
INSERT INTO calendar_cycles_new SELECT id,group_id,kind,created_at FROM calendar_cycles;
DROP TABLE calendar_cycles;
ALTER TABLE calendar_cycles_new RENAME TO calendar_cycles;
UPDATE calendar_occurrences SET cycle_id=(SELECT cycle_id FROM saved_cycle_links WHERE saved_cycle_links.id=calendar_occurrences.id)
 WHERE id IN (SELECT id FROM saved_cycle_links);
DROP TABLE saved_cycle_links;
