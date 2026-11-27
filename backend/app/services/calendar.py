"""Group-scoped planning only. Never writes actual event or attendance records."""
from datetime import date, datetime, timedelta, timezone
from typing import Literal
import re
import uuid
import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..database import connection, transaction
from ..schemas import EventType


class CalendarInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: EventType
    scope: Literal["alliance", "state"]
    alliance_id: str | None = Field(default=None, max_length=64)
    state_id: str = Field(min_length=1, max_length=32)
    starts_at: str
    ends_at: str | None = None
    precision: Literal["date", "minute"]
    phase: str = Field(default="", max_length=80)
    confidence: Literal["confirmed", "estimated"] = "confirmed"

    @model_validator(mode="after")
    def validate_times(self):
        pattern = r"\d{4}-\d{2}-\d{2}" if self.precision == "date" else r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z"
        for value in (self.starts_at, self.ends_at):
            if value is not None:
                if not re.fullmatch(pattern, value):
                    raise ValueError("Use date-only or UTC minute precision consistently")
                parsed = parse(value)
                if not 2000 <= parsed.year <= 2099:
                    raise ValueError("Date outside supported range")
        if self.ends_at is not None and not self.starts_at < self.ends_at:
            raise ValueError("End must follow start")
        if self.ends_at and parse(self.ends_at) - parse(self.starts_at) > timedelta(days=31):
            raise ValueError("Maximum event duration is 31 days")
        if (self.scope == "alliance") != bool(self.alliance_id):
            raise ValueError("Alliance scope requires an alliance; state scope does not")
        return self


class CalendarCreate(CalendarInput):
    request_key: str | None = Field(default=None, min_length=16, max_length=128, pattern=r'^[A-Za-z0-9_-]+
    interval_minutes: int | None = Field(default=None, ge=60, le=525600)
    occurrence_count: int = Field(default=1, ge=1, le=180)

    @model_validator(mode="after")
    def validate_series(self):
        if (self.occurrence_count > 1) != (self.interval_minutes is not None):
            raise ValueError("Specify interval and count together")
        if self.interval_minutes is not None:
            if self.precision == "date" and self.interval_minutes % 1440:
                raise ValueError("Date-only recurrence requires whole days")
            if self.interval_minutes * (self.occurrence_count - 1) > 366 * 1440:
                raise ValueError("Maximum recurrence horizon is 366 days")
            if parse(self.ends_at or self.starts_at) + timedelta(minutes=self.interval_minutes * (self.occurrence_count - 1)) >= datetime(2100,1,1,tzinfo=timezone.utc):
                raise ValueError("Date outside supported range")
        return self


class CalendarUpdate(CalendarInput):
    revision: int = Field(ge=1)
    schedule_status: Literal["scheduled", "cancelled"] = "scheduled"


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z")).replace(tzinfo=timezone.utc)


def shift(value: str | None, minutes: int) -> str | None:
    if value is None:
        return None
    result = parse(value) + timedelta(minutes=minutes)
    return result.strftime("%Y-%m-%dT%H:%MZ" if "T" in value else "%Y-%m-%d")


def require_group(db, group_id, writing=False):
    row = db.execute("SELECT status FROM alliance_groups WHERE id=?", (group_id,)).fetchone()
    if row is None:
        raise LookupError("Group not found")
    if writing and row["status"] != "active":
        raise ValueError("Archived group is read-only")


def validate_scope(db, group_id, payload):
    require_group(db, group_id, True)
    if payload.scope == "alliance":
        row = db.execute("SELECT state_id,status FROM alliances WHERE id=? AND group_id=?", (payload.alliance_id,group_id)).fetchone()
        if row is None:
            raise LookupError("Alliance not found in selected group")
        if row["status"] != "active" or row["state_id"] != payload.state_id:
            raise ValueError("Choose an active alliance in the specified state")
    elif not db.execute("SELECT 1 FROM alliances WHERE group_id=? AND state_id=? AND status='active'", (group_id,payload.state_id)).fetchone():
        raise ValueError("State must belong to an active alliance in this group")


def audit(db, action, occurrence_id):
    db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES (?,?,?,'admin')", (action,"calendar_occurrence",occurrence_id))


def list_occurrences(path, group_id, start: date, end: date):
    if not 2000 <= start.year <= 2099 or not 2000 <= end.year <= 2100 or not 1 <= (end-start).days <= 93:
        raise ValueError("Calendar range must be 1–93 days")
    with connection(path) as db:
        require_group(db, group_id)
        # Date-only starts and UTC minute starts compare consistently against day boundaries.
        rows = db.execute("""SELECT * FROM calendar_occurrences WHERE group_id=?
          AND starts_at < ? AND (starts_at >= ? OR
          (precision='date' AND ends_at > ?) OR
          (precision='minute' AND ends_at > ?))
          ORDER BY starts_at,id LIMIT 2001""",
          (group_id,end.isoformat(),start.isoformat(),start.isoformat(),start.isoformat()+"T00:00Z")).fetchall()
        if len(rows)>2000:
            raise ValueError("Too many calendar entries; select a shorter range")
        return {"items":[dict(row) for row in rows]}


def create(path, group_id, payload: CalendarCreate):
    fingerprint = hashlib.sha256(json.dumps(payload.model_dump(mode="json", exclude={"request_key"}), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with transaction(path) as db:
        require_group(db, group_id, True)
        if payload.request_key:
            previous = db.execute("SELECT payload_hash, occurrence_ids FROM calendar_create_requests WHERE group_id=? AND request_key=?", (group_id, payload.request_key)).fetchone()
            if previous:
                if previous["payload_hash"] != fingerprint:
                    raise ValueError("Request key already used for a different schedule")
                return {"items": [dict(db.execute("SELECT * FROM calendar_occurrences WHERE group_id=? AND id=?", (group_id, oid)).fetchone()) for oid in json.loads(previous["occurrence_ids"])]}
        validate_scope(db, group_id, payload)
        series_id = uuid.uuid4().hex if payload.interval_minutes is not None else None
        if series_id:
            db.execute("INSERT INTO calendar_series(id,group_id,interval_minutes,occurrence_count,anchor) VALUES (?,?,?,?,?)",
                       (series_id,group_id,payload.interval_minutes,payload.occurrence_count,payload.starts_at))
        items=[]
        for sequence in range(payload.occurrence_count):
            occurrence_id=uuid.uuid4().hex
            offset=sequence*(payload.interval_minutes or 0)
            db.execute("""INSERT INTO calendar_occurrences(id,group_id,series_id,sequence,event_type,scope,alliance_id,state_id,starts_at,ends_at,precision,phase,confidence,source)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (occurrence_id,group_id,series_id,sequence,payload.event_type,payload.scope,payload.alliance_id,payload.state_id,shift(payload.starts_at,offset),shift(payload.ends_at,offset),payload.precision,payload.phase,payload.confidence if sequence==0 else "estimated","manual" if sequence==0 else "recurrence"))
            audit(db,"created",occurrence_id)
            items.append(dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (occurrence_id,)).fetchone()))
        if payload.request_key:
            db.execute("INSERT INTO calendar_create_requests(group_id,request_key,payload_hash,occurrence_ids) VALUES (?,?,?,?)", (group_id,payload.request_key,fingerprint,json.dumps([item["id"] for item in items])))
        return {"items":items}


def update(path, group_id, occurrence_id, payload: CalendarUpdate):
    with transaction(path) as db:
        require_group(db,group_id,True)
        row=db.execute("SELECT * FROM calendar_occurrences WHERE id=? AND group_id=?", (occurrence_id,group_id)).fetchone()
        if row is None:
            raise LookupError("Calendar occurrence not found")
        if row["revision"]!=payload.revision:
            raise ValueError("Calendar entry changed; reload before saving")
        validate_scope(db,group_id,payload)
        db.execute("""UPDATE calendar_occurrences SET event_type=?,scope=?,alliance_id=?,state_id=?,starts_at=?,ends_at=?,precision=?,phase=?,confidence=?,schedule_status=?,source='manual',revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND group_id=?""",
          (payload.event_type,payload.scope,payload.alliance_id,payload.state_id,payload.starts_at,payload.ends_at,payload.precision,payload.phase,payload.confidence,payload.schedule_status,occurrence_id,group_id))
        audit(db,"cancelled" if payload.schedule_status=="cancelled" else "updated",occurrence_id)
        return dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (occurrence_id,)).fetchone())
)
    interval_minutes: int | None = Field(default=None, ge=60, le=525600)
    occurrence_count: int = Field(default=1, ge=1, le=180)

    @model_validator(mode="after")
    def validate_series(self):
        if (self.occurrence_count > 1) != (self.interval_minutes is not None):
            raise ValueError("Specify interval and count together")
        if self.interval_minutes is not None:
            if self.precision == "date" and self.interval_minutes % 1440:
                raise ValueError("Date-only recurrence requires whole days")
            if self.interval_minutes * (self.occurrence_count - 1) > 366 * 1440:
                raise ValueError("Maximum recurrence horizon is 366 days")
            if parse(self.ends_at or self.starts_at) + timedelta(minutes=self.interval_minutes * (self.occurrence_count - 1)) >= datetime(2100,1,1,tzinfo=timezone.utc):
                raise ValueError("Date outside supported range")
        return self


class CalendarUpdate(CalendarInput):
    revision: int = Field(ge=1)
    schedule_status: Literal["scheduled", "cancelled"] = "scheduled"


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z")).replace(tzinfo=timezone.utc)


def shift(value: str | None, minutes: int) -> str | None:
    if value is None:
        return None
    result = parse(value) + timedelta(minutes=minutes)
    return result.strftime("%Y-%m-%dT%H:%MZ" if "T" in value else "%Y-%m-%d")


def require_group(db, group_id, writing=False):
    row = db.execute("SELECT status FROM alliance_groups WHERE id=?", (group_id,)).fetchone()
    if row is None:
        raise LookupError("Group not found")
    if writing and row["status"] != "active":
        raise ValueError("Archived group is read-only")


def validate_scope(db, group_id, payload):
    require_group(db, group_id, True)
    if payload.scope == "alliance":
        row = db.execute("SELECT state_id,status FROM alliances WHERE id=? AND group_id=?", (payload.alliance_id,group_id)).fetchone()
        if row is None:
            raise LookupError("Alliance not found in selected group")
        if row["status"] != "active" or row["state_id"] != payload.state_id:
            raise ValueError("Choose an active alliance in the specified state")
    elif not db.execute("SELECT 1 FROM alliances WHERE group_id=? AND state_id=? AND status='active'", (group_id,payload.state_id)).fetchone():
        raise ValueError("State must belong to an active alliance in this group")


def audit(db, action, occurrence_id):
    db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES (?,?,?,'admin')", (action,"calendar_occurrence",occurrence_id))


def list_occurrences(path, group_id, start: date, end: date):
    if not 2000 <= start.year <= 2099 or not 2000 <= end.year <= 2100 or not 1 <= (end-start).days <= 93:
        raise ValueError("Calendar range must be 1–93 days")
    with connection(path) as db:
        require_group(db, group_id)
        # Date-only starts and UTC minute starts compare consistently against day boundaries.
        rows = db.execute("""SELECT * FROM calendar_occurrences WHERE group_id=?
          AND starts_at < ? AND (starts_at >= ? OR
          (precision='date' AND ends_at > ?) OR
          (precision='minute' AND ends_at > ?))
          ORDER BY starts_at,id LIMIT 2001""",
          (group_id,end.isoformat(),start.isoformat(),start.isoformat(),start.isoformat()+"T00:00Z")).fetchall()
        if len(rows)>2000:
            raise ValueError("Too many calendar entries; select a shorter range")
        return {"items":[dict(row) for row in rows]}


def create(path, group_id, payload: CalendarCreate):
    with transaction(path) as db:
        validate_scope(db,group_id,payload)
        series_id = uuid.uuid4().hex if payload.interval_minutes is not None else None
        if series_id:
            db.execute("INSERT INTO calendar_series(id,group_id,interval_minutes,occurrence_count,anchor) VALUES (?,?,?,?,?)",
                       (series_id,group_id,payload.interval_minutes,payload.occurrence_count,payload.starts_at))
        items=[]
        for sequence in range(payload.occurrence_count):
            occurrence_id=uuid.uuid4().hex
            offset=sequence*(payload.interval_minutes or 0)
            db.execute("""INSERT INTO calendar_occurrences(id,group_id,series_id,sequence,event_type,scope,alliance_id,state_id,starts_at,ends_at,precision,phase,confidence,source)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (occurrence_id,group_id,series_id,sequence,payload.event_type,payload.scope,payload.alliance_id,payload.state_id,shift(payload.starts_at,offset),shift(payload.ends_at,offset),payload.precision,payload.phase,payload.confidence if sequence==0 else "estimated","manual" if sequence==0 else "recurrence"))
            audit(db,"created",occurrence_id)
            items.append(dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (occurrence_id,)).fetchone()))
        return {"items":items}


def update(path, group_id, occurrence_id, payload: CalendarUpdate):
    with transaction(path) as db:
        require_group(db,group_id,True)
        row=db.execute("SELECT * FROM calendar_occurrences WHERE id=? AND group_id=?", (occurrence_id,group_id)).fetchone()
        if row is None:
            raise LookupError("Calendar occurrence not found")
        if row["revision"]!=payload.revision:
            raise ValueError("Calendar entry changed; reload before saving")
        validate_scope(db,group_id,payload)
        db.execute("""UPDATE calendar_occurrences SET event_type=?,scope=?,alliance_id=?,state_id=?,starts_at=?,ends_at=?,precision=?,phase=?,confidence=?,schedule_status=?,source='manual',revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND group_id=?""",
          (payload.event_type,payload.scope,payload.alliance_id,payload.state_id,payload.starts_at,payload.ends_at,payload.precision,payload.phase,payload.confidence,payload.schedule_status,occurrence_id,group_id))
        audit(db,"cancelled" if payload.schedule_status=="cancelled" else "updated",occurrence_id)
        return dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (occurrence_id,)).fetchone())


class CalendarFutureChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["shift", "cancel"]
    shift_minutes: int = Field(default=0, ge=-527040, le=527040)
    revisions: dict[str, int] = Field(min_length=1, max_length=180)

    @model_validator(mode="after")
    def validate_action(self):
        if (self.action == "shift") != (self.shift_minutes != 0):
            raise ValueError("Shift requires a nonzero offset; cancellation requires zero")
        return self


def future_threshold(precision, now):
    return now.replace(hour=0, minute=0, second=0, microsecond=0) if precision == "date" else now


def future_rows(db, group_id, occurrence_id):
    require_group(db, group_id)
    row = db.execute("SELECT * FROM calendar_occurrences WHERE id=? AND group_id=?", (occurrence_id, group_id)).fetchone()
    if row is None:
        raise LookupError("Calendar occurrence not found")
    if row["series_id"] is None or row["schedule_status"] != "scheduled":
        raise ValueError("Choose a scheduled occurrence in a recurring series")
    now = datetime.now(timezone.utc)
    if parse(row["starts_at"]) < future_threshold(row["precision"], now):
        raise ValueError("Choose a future occurrence")
    # Keep manual overrides and cancellations intact.
    rows = db.execute("""SELECT * FROM calendar_occurrences WHERE group_id=? AND series_id=?
        AND sequence>=? AND schedule_status='scheduled' AND (id=? OR source='recurrence')
        ORDER BY sequence""", (group_id, row["series_id"], row["sequence"], occurrence_id)).fetchall()
    return [dict(r) for r in rows if parse(r["starts_at"]) >= future_threshold(r["precision"], now)]


def preview_future(path, group_id, occurrence_id):
    with connection(path) as db:
        return {"items": future_rows(db, group_id, occurrence_id)}


def change_future(path, group_id, occurrence_id, payload: CalendarFutureChange):
    with transaction(path) as db:
        require_group(db, group_id, True)
        rows = future_rows(db, group_id, occurrence_id)
        if not rows or {row["id"]: row["revision"] for row in rows} != payload.revisions:
            raise ValueError("Series changed; review affected occurrences again")
        now = datetime.now(timezone.utc)
        for row in rows:
            if payload.action == "shift":
                if row["precision"] == "date" and payload.shift_minutes % 1440:
                    raise ValueError("Date-only entries require whole-day shifts")
                start = shift(row["starts_at"], payload.shift_minutes)
                end = shift(row["ends_at"], payload.shift_minutes)
                if parse(start) < future_threshold(row["precision"], now) or not 2000 <= parse(start).year <= 2099 or (end and not 2000 <= parse(end).year <= 2099):
                    raise ValueError("Shift would move an occurrence outside future supported dates")
                validate_scope(db, group_id, CalendarInput(**{k: row[k] for k in CalendarInput.model_fields}))
                db.execute("UPDATE calendar_occurrences SET starts_at=?,ends_at=?,confidence='estimated',revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (start,end,row["id"]))
            else:
                db.execute("UPDATE calendar_occurrences SET schedule_status='cancelled',source='manual',revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (row["id"],))
            audit(db, "cancelled" if payload.action == "cancel" else "rescheduled", row["id"])
        return {"items": [dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (row["id"],)).fetchone()) for row in rows]}
