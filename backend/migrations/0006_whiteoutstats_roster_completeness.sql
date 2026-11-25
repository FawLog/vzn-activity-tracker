-- A roster whose count does not agree with alliance info is useful evidence
-- for listed players, but cannot be used to infer that anyone is absent.
ALTER TABLE alliance_stat_snapshots
  ADD COLUMN roster_complete INTEGER NOT NULL DEFAULT 0 CHECK(roster_complete IN (0, 1));
