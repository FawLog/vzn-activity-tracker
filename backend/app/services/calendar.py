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
from .calendar_catalog_ids import CATALOG_IDS
from calendar import monthrange


class CalendarInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str = Field(max_length=100)
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
        if self.event_type not in CATALOG_IDS and self.event_type not in {e.value for e in EventType}:
            raise ValueError("Unknown calendar event type")
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
    request_key: str | None = Field(default=None, min_length=16, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')
    interval_minutes: int | None = Field(default=None, ge=60, le=525600)
    occurrence_count: int = Field(default=1, ge=1, le=180)
    reject_existing: bool = False
    repeat_months: int | None = Field(default=None, ge=1, le=12)
    repeat_weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)

    @model_validator(mode="after")
    def validate_series(self):
        rules = sum(rule is not None for rule in (self.interval_minutes,self.repeat_months,self.repeat_weekdays))
        if rules != int(self.occurrence_count > 1):
            raise ValueError("Specify exactly one repeat rule for a series")
        if self.repeat_weekdays is not None:
            if len(set(self.repeat_weekdays)) != len(self.repeat_weekdays) or any(d not in range(7) for d in self.repeat_weekdays):
                raise ValueError("Choose distinct weekdays 0–6 (Monday–Sunday)")
            if parse(self.starts_at).weekday() not in self.repeat_weekdays:
                raise ValueError("Anchor must match a selected weekday")
        if self.repeat_months is not None or self.repeat_weekdays is not None:
            offsets = series_offsets(self)
            if offsets[-1] > 366*1440:
                raise ValueError("Maximum recurrence horizon is 366 days")
            if parse(self.ends_at or self.starts_at)+timedelta(minutes=offsets[-1]) >= datetime(2100,1,1,tzinfo=timezone.utc):
                raise ValueError("Date outside supported range")
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


def series_offsets(payload):
    anchor = parse(payload.starts_at)
    if payload.repeat_months is not None:
        offsets = []
        for i in range(payload.occurrence_count):
            month_index = anchor.year*12+anchor.month-1+i*payload.repeat_months
            year, month = divmod(month_index,12)
            target = anchor.replace(year=year,month=month+1,day=min(anchor.day,monthrange(year,month+1)[1]))
            offset = int((target-anchor).total_seconds()//60)
            if offset > 366*1440:
                raise ValueError("Maximum recurrence horizon is 366 days")
            offsets.append(offset)
        return offsets
    if payload.repeat_weekdays is not None:
        offsets = [0]
        for day in range(1,367):
            if (anchor.weekday()+day)%7 in payload.repeat_weekdays:
                offsets.append(day*1440)
                if len(offsets)==payload.occurrence_count:
                    return offsets
        raise ValueError("Maximum recurrence horizon is 366 days")
    return [i*(payload.interval_minutes or 0) for i in range(payload.occurrence_count)]


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
    # Preserve the v1 request hash when the new opt-in field is false.
    excluded = {"request_key"} if payload.reject_existing else {"request_key", "reject_existing"}
    excluded.update(k for k in ("repeat_months","repeat_weekdays") if getattr(payload,k) is None)
    offsets = series_offsets(payload)
    fingerprint = hashlib.sha256(json.dumps(payload.model_dump(mode="json", exclude=excluded), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with transaction(path) as db:
        require_group(db, group_id, True)
        if payload.request_key:
            previous = db.execute("SELECT payload_hash, occurrence_ids FROM calendar_create_requests WHERE group_id=? AND request_key=?", (group_id, payload.request_key)).fetchone()
            if previous:
                if previous["payload_hash"] != fingerprint:
                    raise ValueError("Request key already used for a different schedule")
                return {"items": [dict(db.execute("SELECT * FROM calendar_occurrences WHERE group_id=? AND id=?", (group_id, oid)).fetchone()) for oid in json.loads(previous["occurrence_ids"])]}
        validate_scope(db, group_id, payload)
        if payload.reject_existing:
            # Date-only entries are ambiguous with any timed entry on the same UTC day.
            # Include cancelled entries so a new forecast cannot silently resurrect them.
            existing = db.execute("""SELECT starts_at,precision FROM calendar_occurrences
                WHERE group_id=? AND event_type=? AND scope=? AND alliance_id IS ? AND state_id=? AND phase=?
                AND starts_at>=? AND starts_at<?""",
                (group_id,payload.event_type,payload.scope,payload.alliance_id,payload.state_id,payload.phase,
                 payload.starts_at[:10],(parse(shift(payload.starts_at,offsets[-1])).date()+timedelta(days=1)).isoformat())).fetchall()
            for offset in offsets:
                start = shift(payload.starts_at, offset)
                if any(row["starts_at"]==start or
                       (row["starts_at"][:10]==start[:10] and (row["precision"]=="date" or payload.precision=="date"))
                       for row in existing):
                    raise ValueError("A matching scheduled or cancelled occurrence already exists; review the calendar")
        series_id = uuid.uuid4().hex if payload.occurrence_count > 1 else None
        if series_id:
            db.execute("INSERT INTO calendar_series(id,group_id,interval_minutes,occurrence_count,anchor) VALUES (?,?,?,?,?)",
                       (series_id,group_id,payload.interval_minutes or offsets[1],payload.occurrence_count,payload.starts_at))
            if payload.repeat_months is not None or payload.repeat_weekdays is not None:
                db.execute("INSERT INTO calendar_series_rules(series_id,rule_json) VALUES (?,?)",(series_id,json.dumps({"repeat_months":payload.repeat_months,"repeat_weekdays":payload.repeat_weekdays})))
        items=[]
        for sequence,offset in enumerate(offsets):
            occurrence_id=uuid.uuid4().hex
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
        if row["cycle_id"]:
            if any(row[k]!=getattr(payload,k) for k in ("event_type","scope","alliance_id","state_id","phase")):
                raise ValueError("Cycle phase identity and owner cannot be changed")
            siblings=db.execute("SELECT * FROM calendar_occurrences WHERE group_id=? AND cycle_id=? AND id!=? ORDER BY starts_at",(group_id,row["cycle_id"],occurrence_id)).fetchall()
            for sibling in siblings:
                if parse(sibling["starts_at"])<parse(row["starts_at"]):
                    if parse(payload.starts_at)<=parse(sibling["starts_at"]) or (sibling["ends_at"] and parse(payload.starts_at)<parse(sibling["ends_at"])):
                        raise ValueError("Phase would cross an earlier cycle phase")
                elif parse(payload.starts_at)>=parse(sibling["starts_at"]) or (payload.ends_at and parse(payload.ends_at)>parse(sibling["starts_at"])):
                    raise ValueError("Phase would cross a later cycle phase")
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

class CalendarCycleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["canyon", "svs"]
    request_key: str = Field(min_length=16,max_length=128,pattern=r"^[A-Za-z0-9_-]+$")
    phases: list[CalendarInput] = Field(min_length=2,max_length=4)

    @model_validator(mode="after")
    def validate_phases(self):
        expected = {"canyon":[("canyon","Voting"),("canyon","Registration"),("canyon","Matchmaking"),("canyon","Battle")],
                    "svs":[("svs_preparation","Preparation"),("svs_battle","Battle")]}[self.kind]
        if [(p.event_type,p.phase) for p in self.phases] != expected:
            raise ValueError("Invalid cycle phases or order")
        first = self.phases[0]
        if self.kind=="svs" and first.scope!="state":
            raise ValueError("SvS cycle requires state scope")
        if self.kind=="canyon" and first.scope!="alliance":
            raise ValueError("Canyon cycle requires alliance scope")
        for i,p in enumerate(self.phases):
            if (p.scope,p.alliance_id,p.state_id)!=(first.scope,first.alliance_id,first.state_id):
                raise ValueError("All phases must have the same owner")
            if i and parse(p.starts_at)<=parse(self.phases[i-1].starts_at):
                raise ValueError("Phases must be chronological")
            if i and self.phases[i-1].ends_at and parse(p.starts_at)<parse(self.phases[i-1].ends_at):
                raise ValueError("Cycle phases must not overlap")
            if parse(p.ends_at or p.starts_at)-parse(first.starts_at)>timedelta(days=31):
                raise ValueError("Maximum cycle duration is 31 days")
        return self


def create_cycle(path,group_id,payload:CalendarCycleCreate):
    fingerprint=hashlib.sha256(json.dumps({"cycle":payload.model_dump(mode="json",exclude={"request_key"})},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    with transaction(path) as db:
        require_group(db,group_id,True)
        previous=db.execute("SELECT payload_hash,occurrence_ids FROM calendar_create_requests WHERE group_id=? AND request_key=?",(group_id,payload.request_key)).fetchone()
        if previous:
            if previous["payload_hash"]!=fingerprint:
                raise ValueError("Request key already used for a different schedule")
            return {"items":[dict(db.execute("SELECT * FROM calendar_occurrences WHERE group_id=? AND id=?",(group_id,oid)).fetchone()) for oid in json.loads(previous["occurrence_ids"])]}
        for p in payload.phases:
            validate_scope(db,group_id,p)
            # Blank legacy phase may represent the same event. Never silently duplicate it.
            existing=db.execute("""SELECT starts_at,precision FROM calendar_occurrences
                WHERE group_id=? AND event_type=? AND scope=? AND alliance_id IS ? AND state_id=?
                AND (phase=? OR phase='') AND starts_at>=? AND starts_at<?""",
                (group_id,p.event_type,p.scope,p.alliance_id,p.state_id,p.phase,p.starts_at[:10],
                 (parse(p.starts_at).date()+timedelta(days=1)).isoformat())).fetchall()
            if any(r["starts_at"]==p.starts_at or r["precision"]=="date" or p.precision=="date" for r in existing):
                raise ValueError("A matching scheduled or cancelled phase already exists; review the calendar")
        cycle_id=uuid.uuid4().hex
        db.execute("INSERT INTO calendar_cycles(id,group_id,kind) VALUES (?,?,?)",(cycle_id,group_id,payload.kind))
        items=[]
        for p in payload.phases:
            oid=uuid.uuid4().hex
            db.execute("""INSERT INTO calendar_occurrences(id,group_id,cycle_id,event_type,scope,alliance_id,state_id,starts_at,ends_at,precision,phase,confidence,source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'manual')""",
                (oid,group_id,cycle_id,p.event_type,p.scope,p.alliance_id,p.state_id,p.starts_at,p.ends_at,p.precision,p.phase,p.confidence))
            audit(db,"created",oid)
            items.append(dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?",(oid,)).fetchone()))
        db.execute("INSERT INTO calendar_create_requests(group_id,request_key,payload_hash,occurrence_ids) VALUES (?,?,?,?)",(group_id,payload.request_key,fingerprint,json.dumps([r["id"] for r in items])))
        return {"items":items}


def get_cycle(path,group_id,cycle_id):
    with connection(path) as db:
        require_group(db,group_id)
        cycle=db.execute("SELECT * FROM calendar_cycles WHERE id=? AND group_id=?",(cycle_id,group_id)).fetchone()
        if cycle is None:
            raise LookupError("Calendar cycle not found")
        rows=db.execute("SELECT * FROM calendar_occurrences WHERE group_id=? AND cycle_id=? ORDER BY starts_at,id",(group_id,cycle_id)).fetchall()
        return {"kind":cycle["kind"],"items":[dict(r) for r in rows]}
