"""Manual session editor. Explicit evidence, stable identity and atomic writes."""
from datetime import datetime, timezone
from typing import Literal
import uuid
import re

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from ..database import connection, transaction

SESSION_KEYS = {
    "alliance_mobilization": {"main"},
    "alliance_championship": {"main"},
    "foundry": {"legion_1", "legion_2"},
    "canyon": {"legion_1", "legion_2"},
    "bear_trap": {"trap_1", "trap_2"},
}
METRICS = {
    "alliance_mobilization": {"points", "rank", "missions_completed", "missions_accepted"},
    "alliance_championship": {"registration_value"},
    "foundry": {"personal_points", "rank"},
    "canyon": {"personal_points", "rank"},
    "bear_trap": {"damage", "rank"},
}


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_key: str
    started_at: datetime
    host_alliance_id: str | None = Field(default=None, max_length=64)

    @field_validator("started_at")
    @classmethod
    def utc_time(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        return value.astimezone(timezone.utc)


class PlayerRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fid: str = Field(min_length=1, max_length=32)
    nickname: str = Field(min_length=1, max_length=120)
    eligibility: Literal["confirmed", "unknown", "no_duty"] = "unknown"
    registration: Literal["registered", "not_registered", "excused", "unknown"] = "unknown"
    role: Literal["main", "substitute"] | None = None
    registered_by: Literal["player", "officer", "unknown"] | None = None
    attendance: Literal["confirmed_present", "confirmed_absent", "excused", "no_duty", "unknown"] = "unknown"
    metrics: dict[str, StrictInt] = Field(default_factory=dict, max_length=8)


class FoundryDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    main_count: StrictInt | None = Field(default=None, ge=0, le=30)
    substitute_count: StrictInt | None = Field(default=None, ge=0, le=10)
    outcome: Literal["victory", "defeat"] | None = None
    own_score: StrictInt | None = Field(default=None, ge=0, le=9007199254740991)
    opponent_score: StrictInt | None = Field(default=None, ge=0, le=9007199254740991)
    opponent_tag: str | None = Field(default=None, max_length=24)
    opponent_name: str | None = Field(default=None, max_length=120)
    opponent_state: str | None = Field(default=None, max_length=16, pattern=r"^\d+$")


FOUNDRY_FIELDS = ("main_count", "substitute_count", "outcome", "own_score", "opponent_score", "opponent_tag", "opponent_name", "opponent_state")


def foundry_details(db, session_id):
    row = db.execute("SELECT * FROM foundry_session_details WHERE session_id=?", (session_id,)).fetchone()
    return {k: row[k] for k in FOUNDRY_FIELDS} if row else {}


class SessionSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    roster_complete: bool = False
    registration_complete: bool = False
    attendance_complete: bool = False
    results_complete: bool = False
    rows: list[PlayerRow] = Field(max_length=500)
    foundry_details: FoundryDetails | None = None


def _event(db, group_id, event_id, *, editable=False):
    event = db.execute("""
        SELECT e.*, a.status AS alliance_status, g.status AS group_status
        FROM events e JOIN alliances a ON a.id=e.alliance_id
        JOIN alliance_groups g ON g.id=a.group_id
        WHERE e.id=? AND a.group_id=?
    """, (event_id, group_id)).fetchone()
    if event is None:
        raise LookupError("Event not found in selected group")
    if editable and (event["status"] != "draft" or event["alliance_status"] != "active" or event["group_status"] != "active"):
        raise ValueError("Only active draft events can be edited")
    if editable and event["event_type"] not in SESSION_KEYS:
        raise ValueError("Event type not supported by manual editor")
    return event


def _audit(db, event_id, action):
    db.execute("INSERT INTO audit_log(action, entity_type, entity_id, actor) VALUES (?, 'event', ?, 'admin')", (action, event_id))


def historical_homes(db, group_id, occurred_on):
    homes = {}
    for row in db.execute("""SELECT player_fid, alliance_id FROM player_primary_alliance_history
        WHERE group_id=? AND substr(effective_observed_at,1,10)<?
        AND (ended_observed_at IS NULL OR substr(ended_observed_at,1,10)>?)""",
        (group_id, occurred_on, occurred_on)):
        homes.setdefault(row["player_fid"], set()).add(row["alliance_id"])
    return {fid: next(iter(ids)) for fid, ids in homes.items() if len(ids) == 1}


def read(path, group_id, event_id):
    with connection(path) as db:
        event = _event(db, group_id, event_id)
        sessions = []
        for session in db.execute("SELECT * FROM event_sessions WHERE event_id=? ORDER BY session_key", (event_id,)):
            item = {key: session[key] for key in ('id', 'session_key', 'started_at', 'revision', 'host_alliance_id')}
            item.update({key: bool(session[key]) for key in ('roster_complete', 'registration_complete', 'attendance_complete', 'results_complete')})
            rows = []
            for row in db.execute("SELECT * FROM event_session_roster WHERE session_id=? ORDER BY nickname COLLATE NOCASE, player_fid", (session["id"],)):
                entry = dict(row)
                entry.pop("session_id")
                entry["fid"] = entry.pop("player_fid")
                entry["metrics"] = {m["metric_key"]: m["raw_value"] for m in db.execute("SELECT metric_key, raw_value FROM event_session_metrics WHERE session_id=? AND player_fid=?", (session["id"], entry["fid"]))}
                rows.append(entry)
            item["rows"] = rows
            if event["event_type"] == "foundry":
                item["foundry_details"] = foundry_details(db, session["id"])
            sessions.append(item)
        completion = [dict(r) for r in db.execute("SELECT player_fid AS fid,nickname,outcome,roster_member,home_alliance_id FROM event_completion_roster WHERE event_id=? ORDER BY nickname COLLATE NOCASE,player_fid",(event_id,))]
        return {"event_id": event_id, "event_type": event["event_type"], "status": event["status"], "bear_cycle_complete": bool(event["bear_cycle_complete"]), "sessions": sessions, "completion": completion, "historical_homes": historical_homes(db, group_id, event["occurred_on"]) if event["event_type"] in ("bear_trap", "foundry") else {}}


def create_session(path, group_id, event_id, payload):
    with transaction(path) as db:
        event = _event(db, group_id, event_id, editable=True)
        if not (re.fullmatch(r"trap_(?:[1-9]|[12][0-9]|30)", payload.session_key) if event["event_type"] == "bear_trap" else payload.session_key in SESSION_KEYS[event["event_type"]]):
            raise ValueError("Invalid session for event type")
        if db.execute("SELECT 1 FROM event_sessions WHERE event_id=? AND session_key=?", (event_id, payload.session_key)).fetchone():
            raise ValueError("Session already exists")
        host = payload.host_alliance_id or event["alliance_id"]
        if event["event_type"] != "bear_trap" and host != event["alliance_id"]:
            raise ValueError("Only Bear Hunt supports cross-alliance sessions")
        if not db.execute("SELECT 1 FROM alliances WHERE id=? AND group_id=? AND status='active'", (host,group_id)).fetchone():
            raise ValueError("Host alliance must be active in the selected group")
        db.execute("INSERT INTO event_sessions(id,event_id,session_key,started_at,host_alliance_id) VALUES (?,?,?,?,?)", (uuid.uuid4().hex, event_id, payload.session_key, payload.started_at.isoformat(),host))
        if event["event_type"] == "bear_trap":
            db.execute("UPDATE events SET bear_cycle_complete=0 WHERE id=?", (event_id,))
        _audit(db, event_id, "session_created")
    return read(path, group_id, event_id)


def save(path, group_id, event_id, session_id, payload):
    with transaction(path) as db:
        event = _event(db, group_id, event_id, editable=True)
        session = db.execute("SELECT * FROM event_sessions WHERE id=? AND event_id=?", (session_id, event_id)).fetchone()
        if session is None:
            raise LookupError("Session not found")
        if session["revision"] != payload.revision:
            raise ValueError("Session changed; reload before saving")
        if payload.foundry_details is not None and event["event_type"] != "foundry":
            raise ValueError("Battle metadata is only supported for Foundry")
        if event["event_type"] == "foundry":
            details = payload.foundry_details.model_dump() if payload.foundry_details is not None else foundry_details(db, session_id)
            own, opponent, outcome = details.get("own_score"), details.get("opponent_score"), details.get("outcome")
            if own is not None and opponent is not None and outcome and ((outcome == "victory" and own <= opponent) or (outcome == "defeat" and own >= opponent)):
                raise ValueError("Battle outcome conflicts with recorded team scores")
            if payload.registration_complete:
                selected = [r for r in payload.rows if r.registration == "registered"]
                if any(not r.role for r in selected) or details.get("main_count") != sum(r.role == "main" for r in selected) or details.get("substitute_count") != sum(r.role == "substitute" for r in selected):
                    raise ValueError("Reviewed registration counts must match the combatant and substitute mail")
        seen = set()
        for row in payload.rows:
            if row.fid in seen:
                raise ValueError("Duplicate player")
            seen.add(row.fid)
            if not db.execute("SELECT 1 FROM player_group_profiles WHERE player_fid=? AND group_id=?", (row.fid, group_id)).fetchone():
                raise ValueError("Player does not belong to selected group")
            if row.registered_by and row.registration != "registered":
                raise ValueError("Registration author requires registration")
            if row.role and (event["event_type"] not in {"foundry", "canyon"} or row.registration != "registered"):
                raise ValueError("Role requires battle registration")
            if row.attendance == "confirmed_absent" and (row.eligibility != "confirmed" or not payload.attendance_complete or not payload.roster_complete):
                raise ValueError("Absence requires confirmed eligibility and complete attendance evidence and roster")
            if row.registration == "not_registered" and (row.eligibility != "confirmed" or not payload.registration_complete or not payload.roster_complete):
                raise ValueError("Non-registration requires confirmed eligibility and complete registration evidence")
            if any(k not in METRICS[event["event_type"]] or v < 0 or v > 9007199254740991 or (k == "rank" and v == 0) for k,v in row.metrics.items()):
                raise ValueError("Invalid metric")
            if row.metrics.get("missions_completed", 0) > row.metrics.get("missions_accepted", 9007199254740991):
                raise ValueError("Completed missions exceed accepted missions")
            if event["event_type"] == "alliance_championship" and row.attendance != "unknown":
                raise ValueError("Championship records registration only")
            if row.attendance == "confirmed_absent" and any(row.metrics.get(k, 0) > 0 for k in ("damage", "personal_points")):
                raise ValueError("Positive battle result conflicts with absence")
        db.execute("DELETE FROM event_session_roster WHERE session_id=?", (session_id,))
        for row in payload.rows:
            db.execute("""INSERT INTO event_session_roster(session_id,player_fid,nickname,eligibility,registration,role,registered_by,attendance)
                VALUES (?,?,?,?,?,?,?,?)""", (session_id,row.fid,row.nickname,row.eligibility,row.registration,row.role,row.registered_by,row.attendance))
            db.executemany("INSERT INTO event_session_metrics(session_id,player_fid,metric_key,raw_value) VALUES (?,?,?,?)", [(session_id,row.fid,k,v) for k,v in row.metrics.items()])
        if event["event_type"] == "foundry" and payload.foundry_details is not None:
            db.execute("""INSERT INTO foundry_session_details(session_id,main_count,substitute_count,outcome,own_score,opponent_score,opponent_tag,opponent_name,opponent_state)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET
                main_count=excluded.main_count,substitute_count=excluded.substitute_count,outcome=excluded.outcome,
                own_score=excluded.own_score,opponent_score=excluded.opponent_score,opponent_tag=excluded.opponent_tag,
                opponent_name=excluded.opponent_name,opponent_state=excluded.opponent_state""",
                (session_id, *(details.get(k) for k in FOUNDRY_FIELDS)))
        db.execute("""UPDATE event_sessions SET revision=revision+1,roster_complete=?,registration_complete=?,attendance_complete=?,results_complete=? WHERE id=?""", (payload.roster_complete,payload.registration_complete,payload.attendance_complete,payload.results_complete,session_id))
        _audit(db, event_id, "session_saved")
    return read(path, group_id, event_id)


class CompletionReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revisions: dict[str, StrictInt] = Field(max_length=30)
    roster: list[str] = Field(min_length=1, max_length=500)
    home_alliances: dict[str, str] = Field(default_factory=dict, max_length=500)
    excused: list[str] = Field(default_factory=list, max_length=500)
    no_duty: list[str] = Field(default_factory=list, max_length=500)
    expected_sessions: int = Field(ge=1, le=30)


def finalize_attendance(db, event, group_id, review):
    kind = event["event_type"]
    if kind not in {"bear_trap", "foundry", "canyon"}:
        raise ValueError("Event does not support automatic attendance")
    eid = event["id"]
    sessions = db.execute("SELECT * FROM event_sessions WHERE event_id=?", (eid,)).fetchall()
    if len(sessions) != review.expected_sessions or (kind != "bear_trap" and {s["session_key"] for s in sessions} != {"legion_1","legion_2"}):
        raise ValueError("All expected traps or both legions must be recorded")
    if review.revisions != {s["id"]: s["revision"] for s in sessions}:
        raise ValueError("Sessions changed; reload final review")
    roster, excused, no_duty = set(review.roster), set(review.excused), set(review.no_duty)
    if len(roster)!=len(review.roster) or excused & no_duty or not (excused | no_duty) <= roster:
        raise ValueError("Invalid roster or exceptions")
    profiles = {r["player_fid"]: r for r in db.execute("""
        SELECT p.player_fid, (SELECT n.nickname FROM player_nickname_observations n
          WHERE n.player_fid=p.player_fid AND n.group_id=p.group_id
          ORDER BY n.observed_at DESC,n.id DESC LIMIT 1) AS nickname
        FROM player_group_profiles p WHERE p.group_id=?
    """, (group_id,))}
    if not roster <= profiles.keys():
        raise ValueError("Roster contains a player outside this group")
    if kind == "foundry" and any(not s["registration_complete"] or not s["results_complete"] for s in sessions):
        raise ValueError("Confirm complete registration and personal results for both legions")
    if kind == "foundry":
        for s in sessions:
            details = foundry_details(db, s["id"])
            selected = db.execute("SELECT role, COUNT(*) AS n FROM event_session_roster WHERE session_id=? AND registration='registered' GROUP BY role", (s["id"],)).fetchall()
            by_role = {r["role"]: r["n"] for r in selected}
            if None in by_role or details.get("main_count") != by_role.get("main", 0) or details.get("substitute_count") != by_role.get("substitute", 0):
                raise ValueError("Reconfirm registration mail counts before finalizing")
    present = set()
    for s in sessions:
        for r in db.execute("""SELECT r.*, EXISTS(SELECT 1 FROM event_session_metrics m
            WHERE m.session_id=r.session_id AND m.player_fid=r.player_fid
            AND m.metric_key IN ('damage','personal_points') AND m.raw_value>0) AS scored
            FROM event_session_roster r WHERE r.session_id=?""", (s["id"],)):
            if kind == "foundry":
                fid = r["player_fid"]
                score = db.execute("SELECT raw_value FROM event_session_metrics WHERE session_id=? AND player_fid=? AND metric_key='personal_points'", (s["id"], fid)).fetchone()
                if r["registration"] == "registered":
                    if not r["role"]:
                        raise ValueError("Review main/substitute role for all selected players")
                    if fid not in roster and not (score and score["raw_value"] > 0):
                        raise ValueError("Include selected players in the reviewed event roster or review their eligibility")
                    if score is None and fid not in excused | no_duty:
                        raise ValueError("A selected player has missing personal points; review results")
                elif score is not None:
                    raise ValueError("Reconcile personal results with the selected registration roster")
                if score is not None and score["raw_value"] > 0:
                    present.add(fid)
            elif r["attendance"] == "confirmed_present" or r["scored"]:
                present.add(r["player_fid"])
    if present & (excused | no_duty):
        raise ValueError("A participating player cannot be excused or ineligible")
    homes = {}
    if kind == "bear_trap":
        historical = historical_homes(db, group_id, event["occurred_on"])
        valid_homes = {r["id"] for r in db.execute("SELECT id FROM alliances WHERE group_id=?", (group_id,))}
        if not set(review.home_alliances) <= (roster | present) or not set(review.home_alliances.values()) <= valid_homes:
            raise ValueError("Invalid reviewed home alliance")
        for fid in roster | present:
            known = historical.get(fid)
            reviewed = review.home_alliances.get(fid)
            if known and reviewed and known != reviewed:
                raise ValueError("Reviewed home conflicts with historical membership")
            home = known or reviewed
            if fid in roster and not home:
                raise ValueError("Confirm home alliance for every eligible Bear player")
            homes[fid] = home
    db.execute("DELETE FROM event_completion_roster WHERE event_id=?", (eid,))
    for fid in sorted(roster | present):
        outcome = "positive" if fid in present else "no_duty" if fid in no_duty else "excused" if fid in excused else "negative"
        db.execute("INSERT INTO event_completion_roster(event_id,player_fid,nickname,outcome,home_alliance_id,roster_member) VALUES (?,?,?,?,?,?)",
                   (eid,fid,profiles[fid]["nickname"] or fid,outcome,homes.get(fid) if kind == "bear_trap" else event["alliance_id"] if fid in roster else None,int(fid in roster)))
    db.execute("INSERT INTO event_completion_reviews(event_id) VALUES (?) ON CONFLICT(event_id) DO UPDATE SET completed_at=CURRENT_TIMESTAMP", (eid,))
    _audit(db,eid,"attendance_finalized")


def publish(path, group_id, event_id, bear_cycle_complete=False, completion=None):
    with transaction(path) as db:
        event = _event(db, group_id, event_id, editable=True)
        sessions = db.execute("SELECT id FROM event_sessions WHERE event_id=?", (event_id,)).fetchall()
        if not sessions or any(not db.execute("SELECT 1 FROM event_session_roster WHERE session_id=?", (s["id"],)).fetchone() for s in sessions):
            raise ValueError("Every session needs reviewed player records before publication")
        if completion is not None:
            finalize_attendance(db,event,group_id,completion)
            bear_cycle_complete = True
        else:
            db.execute("DELETE FROM event_completion_roster WHERE event_id=?", (event_id,))
            db.execute("DELETE FROM event_completion_reviews WHERE event_id=?", (event_id,))
        db.execute("UPDATE events SET status='published',bear_cycle_complete=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(bear_cycle_complete and event["event_type"] == "bear_trap"), event_id))
        _audit(db, event_id, "published")
    return read(path, group_id, event_id)


def check_ocr_scope(path, group_id, event_id, session_id):
    with connection(path) as db:
        _event(db, group_id, event_id, editable=True)
        if not db.execute("SELECT 1 FROM event_sessions WHERE id=? AND event_id=?", (session_id, event_id)).fetchone():
            raise LookupError("Session not found")


def manage_event(path, group_id, event_id, action, confirmed, occurred_on=None, session_id=None):
    if not confirmed:
        raise ValueError("Explicit confirmation required")
    with transaction(path) as db:
        event = _event(db, group_id, event_id)
        if event["alliance_status"] != "active" or event["group_status"] != "active":
            raise ValueError("Only active groups and alliances can be edited")
        if action == "delete":
            _audit(db,event_id,"event_deleted")
            db.execute("DELETE FROM events WHERE id=?", (event_id,))
            return
        if action == "reopen":
            if event["status"] != "published":
                raise ValueError("Only published events can be reopened")
            db.execute("UPDATE events SET status='draft',bear_cycle_complete=0,updated_at=CURRENT_TIMESTAMP WHERE id=?", (event_id,))
            db.execute("UPDATE event_sessions SET revision=revision+1 WHERE event_id=?", (event_id,))
        elif action == "date":
            if event["status"] != "draft" or occurred_on is None:
                raise ValueError("Reopen the event before changing its date")
            if db.execute("SELECT 1 FROM event_session_roster r JOIN event_sessions s ON s.id=r.session_id WHERE s.event_id=?",(event_id,)).fetchone() or db.execute("SELECT 1 FROM event_participants WHERE event_id=?",(event_id,)).fetchone():
                raise ValueError("Cannot change date after recording results; create a corrected event")
            db.execute("UPDATE events SET occurred_on=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (occurred_on.isoformat(),event_id))
            db.execute("UPDATE event_sessions SET started_at=? || substr(started_at,11), revision=revision+1 WHERE event_id=?", (occurred_on.isoformat(),event_id))
        elif action == "delete_session":
            if event["status"] != "draft":
                raise ValueError("Reopen event before removing a session")
            if event["event_type"] in {"alliance_championship","alliance_mobilization"}:
                raise ValueError("Delete the event instead of its only results section")
            if not db.execute("DELETE FROM event_sessions WHERE id=? AND event_id=?", (session_id,event_id)).rowcount:
                raise LookupError("Session not found")
        else:
            raise ValueError("Unsupported action")
        _audit(db,event_id,"event_"+action)
