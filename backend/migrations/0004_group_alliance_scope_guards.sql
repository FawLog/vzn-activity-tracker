-- 0003 predates composite foreign keys for group-scoped alliance references.
-- Existing nullable legacy data remains valid; these guards reject only new
-- cross-group references and prevent moving an alliance after it is referenced.

CREATE UNIQUE INDEX idx_alliances_group_id_id ON alliances(group_id, id);

CREATE TRIGGER trg_alliances_group_immutable
BEFORE UPDATE OF group_id ON alliances
FOR EACH ROW
WHEN NEW.group_id <> OLD.group_id
BEGIN
  SELECT RAISE(ABORT, 'alliance group cannot be changed');
END;

CREATE TRIGGER trg_player_group_profiles_primary_scope_insert
BEFORE INSERT ON player_group_profiles
FOR EACH ROW
WHEN NEW.primary_alliance_id IS NOT NULL
 AND NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.primary_alliance_id AND group_id = NEW.group_id)
BEGIN
  SELECT RAISE(ABORT, 'primary alliance must belong to player group');
END;

CREATE TRIGGER trg_player_group_profiles_primary_scope_update
BEFORE UPDATE OF group_id, primary_alliance_id ON player_group_profiles
FOR EACH ROW
WHEN NEW.primary_alliance_id IS NOT NULL
 AND NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.primary_alliance_id AND group_id = NEW.group_id)
BEGIN
  SELECT RAISE(ABORT, 'primary alliance must belong to player group');
END;

CREATE TRIGGER trg_nickname_observations_alliance_scope_insert
BEFORE INSERT ON player_nickname_observations
FOR EACH ROW
WHEN NEW.alliance_id IS NOT NULL
 AND (NEW.group_id IS NULL OR NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.alliance_id AND group_id = NEW.group_id))
BEGIN
  SELECT RAISE(ABORT, 'nickname observation alliance must belong to group');
END;

CREATE TRIGGER trg_nickname_observations_alliance_scope_update
BEFORE UPDATE OF group_id, alliance_id ON player_nickname_observations
FOR EACH ROW
WHEN NEW.alliance_id IS NOT NULL
 AND (NEW.group_id IS NULL OR NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.alliance_id AND group_id = NEW.group_id))
BEGIN
  SELECT RAISE(ABORT, 'nickname observation alliance must belong to group');
END;

CREATE TRIGGER trg_membership_observations_alliance_scope_insert
BEFORE INSERT ON player_membership_observations
FOR EACH ROW
WHEN NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.alliance_id AND group_id = NEW.group_id)
BEGIN
  SELECT RAISE(ABORT, 'membership observation alliance must belong to group');
END;

CREATE TRIGGER trg_membership_observations_alliance_scope_update
BEFORE UPDATE OF group_id, alliance_id ON player_membership_observations
FOR EACH ROW
WHEN NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.alliance_id AND group_id = NEW.group_id)
BEGIN
  SELECT RAISE(ABORT, 'membership observation alliance must belong to group');
END;

CREATE TRIGGER trg_transitions_scope_insert
BEFORE INSERT ON player_alliance_transitions
FOR EACH ROW
WHEN (NEW.from_alliance_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.from_alliance_id AND group_id = NEW.group_id))
  OR (NEW.to_alliance_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.to_alliance_id AND group_id = NEW.group_id))
  OR (NEW.source_observation_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM player_membership_observations
    WHERE id = NEW.source_observation_id AND group_id = NEW.group_id AND player_fid = NEW.player_fid
  ))
BEGIN
  SELECT RAISE(ABORT, 'transition references must belong to player group');
END;

CREATE TRIGGER trg_transitions_scope_update
BEFORE UPDATE OF player_fid, group_id, from_alliance_id, to_alliance_id, source_observation_id ON player_alliance_transitions
FOR EACH ROW
WHEN (NEW.from_alliance_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.from_alliance_id AND group_id = NEW.group_id))
  OR (NEW.to_alliance_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.to_alliance_id AND group_id = NEW.group_id))
  OR (NEW.source_observation_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM player_membership_observations
    WHERE id = NEW.source_observation_id AND group_id = NEW.group_id AND player_fid = NEW.player_fid
  ))
BEGIN
  SELECT RAISE(ABORT, 'transition references must belong to player group');
END;

CREATE TRIGGER trg_primary_history_scope_insert
BEFORE INSERT ON player_primary_alliance_history
FOR EACH ROW
WHEN (NEW.alliance_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.alliance_id AND group_id = NEW.group_id))
  OR (NEW.source_transition_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM player_alliance_transitions
    WHERE id = NEW.source_transition_id AND group_id = NEW.group_id AND player_fid = NEW.player_fid
  ))
BEGIN
  SELECT RAISE(ABORT, 'primary alliance history references must belong to player group');
END;

CREATE TRIGGER trg_primary_history_scope_update
BEFORE UPDATE OF player_fid, group_id, alliance_id, source_transition_id ON player_primary_alliance_history
FOR EACH ROW
WHEN (NEW.alliance_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM alliances WHERE id = NEW.alliance_id AND group_id = NEW.group_id))
  OR (NEW.source_transition_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM player_alliance_transitions
    WHERE id = NEW.source_transition_id AND group_id = NEW.group_id AND player_fid = NEW.player_fid
  ))
BEGIN
  SELECT RAISE(ABORT, 'primary alliance history references must belong to player group');
END;
