"""Manual session editor. Explicit evidence, stable identity and atomic writes."""
from datetime import datetime, timezone
from typing import Literal
import uuid

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
            item = dict(session)
            rows = []
            for row in db.execute("SELECT * FROM event_session_roster WHERE session_id=? ORDER BY nickname COLLATE NOCASE, player_fid", (session["id"],)):
                entry = dict(row)
                entry["fid"] = entry.pop("player_fid")
                entry["metrics"] = {m["metric_key"]: m["raw_value"] for m in db.execute("SELECT metric_key, raw_value FROM event_session_metrics WHERE session_id=? AND player_fid=?", (session["id"], entry["fid"]))}
                rows.append(entry)
            item["rows"] = rows
            sessions.append(item)
        return {"event_id": event_id, "event_type": event["event_type"], "status": event["status"], "sessions": sessions}


def create_session(path, group_id, event_id, payload):
    with transaction(path) as db:
        event = _event(db, group_id, event_id, editable=True)
        if payload.session_key not in SESSION_KEYS[event["event_type"]]:
            raise ValueError("Invalid session for event type")
        if db.execute("SELECT 1 FROM event_sessions WHERE event_id=? AND session_key=?", (event_id, payload.session_key)).fetchone():
            raise ValueError("Session already exists")
        db.execute("INSERT INTO event_sessions(id,event_id,session_key,started_at) VALUES (?,?,?,?)", (uuid.uuid4().hex, event_id, payload.session_key, payload.started_at.isoformat()))
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
            if row.role and (event["event_type"] not in {"foundry", "canyon"} or row.registration != "registered"):
                raise ValueError("Role requires battle registration")
            if row.attendance == "confirmed_absent" and (row.eligibility != "confirmed" or not payload.attendance_complete):
                raise ValueError("Absence requires confirmed eligibility and complete attendance evidence")
            if row.registration == "not_registered" and (row.eligibility != "confirmed" or not payload.registration_complete):
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


def publish(path, group_id, event_id):
    with transaction(path) as db:
        _event(db, group_id, event_id, editable=True)
        sessions = db.execute("SELECT id FROM event_sessions WHERE event_id=?", (event_id,)).fetchall()
        if not sessions or any(not db.execute("SELECT 1 FROM event_session_roster WHERE session_id=?", (s["id"],)).fetchone() for s in sessions):
            raise ValueError("Every session needs reviewed player records before publication")
        db.execute("UPDATE events SET status='published',updated_at=CURRENT_TIMESTAMP WHERE id=?", (event_id,))
        _audit(db, event_id, "published")
    return read(path, group_id, event_id)
