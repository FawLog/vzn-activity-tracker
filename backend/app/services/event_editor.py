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


class SessionSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    roster_complete: bool = False
    registration_complete: bool = False
    attendance_complete: bool = False
    results_complete: bool = False
    rows: list[PlayerRow] = Field(max_length=500)


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
            sessions.append(item)
        return {"event_id": event_id, "event_type": event["event_type"], "status": event["status"], "bear_cycle_complete": bool(event["bear_cycle_complete"]), "sessions": sessions}


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
        db.execute("""UPDATE event_sessions SET revision=revision+1,roster_complete=?,registration_complete=?,attendance_complete=?,results_complete=? WHERE id=?""", (payload.roster_complete,payload.registration_complete,payload.attendance_complete,payload.results_complete,session_id))
        _audit(db, event_id, "session_saved")
    return read(path, group_id, event_id)


def publish(path, group_id, event_id, bear_cycle_complete=False):
    with transaction(path) as db:
        event = _event(db, group_id, event_id, editable=True)
        sessions = db.execute("SELECT id FROM event_sessions WHERE event_id=?", (event_id,)).fetchall()
        if not sessions or any(not db.execute("SELECT 1 FROM event_session_roster WHERE session_id=?", (s["id"],)).fetchone() for s in sessions):
            raise ValueError("Every session needs reviewed player records before publication")
        db.execute("UPDATE events SET status='published',updated_at=CURRENT_TIMESTAMP WHERE id=?", (event_id,))
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
