"""Group-scoped planning and explicit draft links; never writes attendance records."""
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
        progress=review_status(db,group_id,[row["id"] for row in rows])
        return {"items":[{**dict(row),**({"review":progress[row["id"]]} if row["id"] in progress else {})} for row in rows]}


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
        if db.execute("SELECT 1 FROM calendar_event_links WHERE occurrence_id=?",(occurrence_id,)).fetchone():
            if any(row[k]!=getattr(payload,k) for k in ("event_type","scope","alliance_id","state_id","phase","starts_at","ends_at","precision","schedule_status")):
                raise ValueError("Unlink the actual event before changing its schedule or cancelling it")
        if row["entry_cycle_date"] and any(row[k]!=getattr(payload,k) for k in ("event_type","scope","alliance_id","state_id","phase","starts_at","ends_at","precision","schedule_status")):
            raise ValueError("Clear the session grouping before changing this schedule")
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
        if any(db.execute("SELECT 1 FROM calendar_event_links WHERE occurrence_id=?",(row["id"],)).fetchone() for row in rows):
            raise ValueError("Unlink actual events before changing this series")
        if any(row["entry_cycle_date"] for row in rows):
            raise ValueError("Clear session grouping before changing this series")
        moving_ids = {row["id"] for row in rows}
        proposed = []
        for row in rows:
            if payload.action == "shift":
                if row["precision"] == "date" and payload.shift_minutes % 1440:
                    raise ValueError("Date-only entries require whole-day shifts")
                start = shift(row["starts_at"], payload.shift_minutes)
                end = shift(row["ends_at"], payload.shift_minutes)
                if parse(start) < future_threshold(row["precision"], now) or not 2000 <= parse(start).year <= 2099 or (end and not 2000 <= parse(end).year <= 2099):
                    raise ValueError("Shift would move an occurrence outside future supported dates")
                validate_scope(db, group_id, CalendarInput(**{k: row[k] for k in CalendarInput.model_fields}))
                matches = db.execute("""SELECT id,starts_at,precision FROM calendar_occurrences
                    WHERE group_id=? AND event_type=? AND scope=? AND alliance_id IS ? AND state_id=? AND phase=?
                    AND starts_at>=? AND starts_at<?""",
                    (group_id,row["event_type"],row["scope"],row["alliance_id"],row["state_id"],row["phase"],
                     start[:10],(parse(start).date()+timedelta(days=1)).isoformat())).fetchall()
                def conflicts(other):
                    return other["starts_at"]==start or (other["starts_at"][:10]==start[:10] and
                        (other["precision"]=="date" or row["precision"]=="date"))
                if any(m["id"] not in moving_ids and conflicts(m) for m in matches) or any(
                    all(m[k]==row[k] for k in ("event_type","scope","alliance_id","state_id","phase")) and conflicts(m)
                    for m in proposed):
                    raise ValueError("Shift would duplicate an existing scheduled or cancelled occurrence")
                proposed.append({**row,"starts_at":start})
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

# Only types with established alliance-owned result workflows. Bear has a group
# cycle and host-specific sessions; it needs a separate mapping.
LINKABLE_TYPES = {"foundry","canyon","alliance_mobilization","alliance_championship","bear_trap"}


class CalendarEventLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str | None = Field(max_length=64)
    session_id: str | None = Field(default=None,min_length=1,max_length=64)
    revision: int = Field(ge=1)


def link_occurrence(db,group_id,occurrence_id):
    require_group(db,group_id)
    row=db.execute("SELECT * FROM calendar_occurrences WHERE group_id=? AND id=?",(group_id,occurrence_id)).fetchone()
    if row is None:
        raise LookupError("Calendar occurrence not found")
    return row


def link_eligible(row):
    return (row["scope"]=="alliance" and row["event_type"] in LINKABLE_TYPES
            and row["schedule_status"]=="scheduled"
            and not (row["event_type"]=="canyon" and row["cycle_id"] and row["phase"]!="Battle"))


def session_candidates(db,row,event_id=None):
    if not link_eligible(row) or row["event_type"] not in {"bear_trap","foundry","canyon"}:
        return []
    # Bear cycle date belongs to the group record; the actual trap date and host
    # are taken from the session, including academy traps on another UTC day.
    day=row["starts_at"][:10]
    sessions=db.execute("""SELECT s.id,s.event_id,s.session_key,s.started_at,s.host_alliance_id,e.status,e.occurred_on
        FROM event_sessions s JOIN events e ON e.id=s.event_id
        JOIN alliances a ON a.id=e.alliance_id JOIN alliances h ON h.id=s.host_alliance_id
        WHERE a.group_id=? AND h.group_id=? AND h.state_id=? AND h.id=? AND e.event_type=?
        AND substr(s.started_at,1,10)=? AND (? IS NULL OR e.id=?)
        AND (e.event_type='bear_trap' OR e.alliance_id=h.id)
        AND NOT EXISTS (SELECT 1 FROM calendar_event_links l WHERE l.session_id=s.id AND l.occurrence_id<>?)
        ORDER BY s.started_at,s.id LIMIT 101""",
        (row["group_id"],row["group_id"],row["state_id"],row["alliance_id"],row["event_type"],day,event_id,event_id,row["id"])).fetchall()
    # Do not infer identity from display labels. Explicit UTC minute, if supplied,
    # must match the recorded session; date-only entries can be reviewed manually.
    return [dict(s) for s in sessions if row["precision"]=="date" or
            parse(s["started_at"][:16]+"Z")==parse(row["starts_at"])]


def link_candidates(db,row):
    if not link_eligible(row) or row["event_type"]=="bear_trap":
        return []
    return [dict(r) for r in db.execute("""SELECT e.id,e.event_type,e.occurred_on,e.status,e.alliance_id
        FROM events e JOIN alliances a ON a.id=e.alliance_id
        WHERE a.group_id=? AND a.state_id=? AND e.alliance_id=? AND e.event_type=? AND e.occurred_on=?
        ORDER BY e.created_at,e.id LIMIT 101""",(row["group_id"],row["state_id"],row["alliance_id"],row["event_type"],row["starts_at"][:10])).fetchall()]


def event_link(path,group_id,occurrence_id):
    with connection(path) as db:
        row=link_occurrence(db,group_id,occurrence_id)
        linked=db.execute("""SELECT e.id,e.event_type,e.occurred_on,e.status,e.alliance_id,l.session_id,s.session_key,s.started_at
            FROM calendar_event_links l JOIN events e ON e.id=l.event_id JOIN alliances a ON a.id=e.alliance_id LEFT JOIN event_sessions s ON s.id=l.session_id
            WHERE l.occurrence_id=? AND a.group_id=?""",(occurrence_id,group_id)).fetchone()
        candidates=link_candidates(db,row)
        sessions=session_candidates(db,row,linked["id"] if linked else None)
        return {"linked":dict(linked) if linked else None,"items":candidates[:100],"sessions":sessions[:100],"truncated":len(candidates)>100 or len(sessions)>100,
                "eligible":link_eligible(row),"revision":row["revision"],"review":review_status(db,group_id,[occurrence_id]).get(occurrence_id),
                "entry_cycle_date":row["entry_cycle_date"],"entry_session_key":row["entry_session_key"],"group_members":entry_group_members(db,row)}


def set_event_link(path,group_id,occurrence_id,payload):
    with transaction(path) as db:
        require_group(db,group_id,True)
        row=link_occurrence(db,group_id,occurrence_id)
        if row["revision"]!=payload.revision:
            raise ValueError("Calendar entry changed; reload before linking")
        if payload.event_id is None and payload.session_id is not None:
            raise ValueError("Session requires an event")
        if payload.event_id is not None:
            if row["entry_cycle_date"]:
                raise ValueError("Use Enter event data for a grouped schedule")
            validate_scope(db,group_id,CalendarInput(**{k:row[k] for k in CalendarInput.model_fields}))
            if not link_eligible(row):
                raise ValueError("This occurrence cannot be linked to an alliance result")
            if payload.session_id:
                session=next((s for s in session_candidates(db,row,payload.event_id) if s["id"]==payload.session_id),None)
                if session is None:
                    raise ValueError("Session must match the schedule host, state, type and UTC date/time and be unlinked elsewhere")
            elif row["event_type"]=="bear_trap":
                raise ValueError("Bear schedules require an explicit trap session")
            else:
                event=db.execute("""SELECT e.id FROM events e JOIN alliances a ON a.id=e.alliance_id
                    WHERE e.id=? AND a.group_id=? AND a.state_id=? AND e.alliance_id=? AND e.event_type=? AND e.occurred_on=?""",
                    (payload.event_id,group_id,row["state_id"],row["alliance_id"],row["event_type"],row["starts_at"][:10])).fetchone()
                if event is None:
                    raise ValueError("Event must match alliance, state, type and UTC start date")
            old=db.execute("SELECT event_id,session_id FROM calendar_event_links WHERE occurrence_id=?",(occurrence_id,)).fetchone()
            if old and (old["event_id"]!=payload.event_id or (old["session_id"] and old["session_id"]!=payload.session_id)):
                raise ValueError("Unlink the existing event or session first")
            db.execute("INSERT INTO calendar_event_links(occurrence_id,event_id,session_id) VALUES (?,?,?) ON CONFLICT(occurrence_id) DO UPDATE SET session_id=excluded.session_id",
                       (occurrence_id,payload.event_id,payload.session_id))
        else:
            if row["entry_cycle_date"]:
                require_open_cycle_for_grouping(db,group_id,row["event_type"],row["entry_cycle_date"],row["alliance_id"])
            db.execute("DELETE FROM calendar_event_links WHERE occurrence_id=?",(occurrence_id,))
        db.execute("UPDATE calendar_occurrences SET revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",(occurrence_id,))
        audit(db,"event_linked" if payload.event_id else "event_unlinked",occurrence_id)
    return event_link(path,group_id,occurrence_id)


def event_schedules(path,group_id,event_id):
    with connection(path) as db:
        require_group(db,group_id)
        if not db.execute("SELECT 1 FROM events e JOIN alliances a ON a.id=e.alliance_id WHERE e.id=? AND a.group_id=?",(event_id,group_id)).fetchone():
            raise LookupError("Event not found in selected group")
        return {"items":[dict(r) for r in db.execute("""SELECT c.*,l.session_id AS linked_session_id FROM calendar_occurrences c JOIN calendar_event_links l ON l.occurrence_id=c.id
            WHERE c.group_id=? AND l.event_id=? ORDER BY c.starts_at,c.id""",(group_id,event_id)).fetchall()]}

class CalendarDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    confirmed: Literal[True]
    event_id: str | None = Field(default=None,max_length=64)
    cycle_date: date | None = None
    session_key: str | None = Field(default=None,max_length=32)


def create_linked_draft(path,group_id,occurrence_id,payload):
    """Create only explicitly reviewed draft records, atomically with their link."""
    with transaction(path) as db:
        require_group(db,group_id,True)
        row=link_occurrence(db,group_id,occurrence_id)
        if row["revision"]!=payload.revision:
            raise ValueError("Calendar entry changed; reload before creating a draft")
        validate_scope(db,group_id,CalendarInput(**{k:row[k] for k in CalendarInput.model_fields}))
        if not link_eligible(row) or row["confidence"]!="confirmed":
            raise ValueError("Confirm a supported alliance schedule before creating a draft")
        old=db.execute("SELECT event_id,session_id FROM calendar_event_links WHERE occurrence_id=?",(occurrence_id,)).fetchone()
        if old and (old["session_id"] or old["event_id"]!=payload.event_id):
            raise ValueError("Schedule already linked; open the existing record")
        if row["entry_cycle_date"]:
            raise ValueError("Use Enter event data for a grouped schedule")
        kind=row["event_type"]
        day=row["starts_at"][:10]
        is_session=kind in {"bear_trap","foundry","canyon"}
        if is_session:
            if row["precision"]!="minute":
                raise ValueError("Set the actual session time explicitly before creating a draft session")
            if not payload.session_key or not re.fullmatch(r"trap_(?:[1-9]|[12][0-9]|30)" if kind=="bear_trap" else r"legion_[12]",payload.session_key):
                raise ValueError("Choose a valid trap or legion identifier")
        elif payload.session_key is not None or payload.event_id is not None:
            raise ValueError("Use the existing event link for this event type")
        if kind=="bear_trap":
            if payload.cycle_date is None or not 2000<=payload.cycle_date.year<=2099:
                raise ValueError("Choose the group Bear cycle date explicitly")
            cycle=payload.cycle_date.isoformat()
            if abs((parse(day)-parse(cycle)).days)>7:
                raise ValueError("Bear cycle date must be within seven days of the trap")
            primary=db.execute("SELECT id FROM alliances WHERE group_id=? AND alliance_type='primary' AND status='active'",(group_id,)).fetchone()
            if primary is None:
                raise ValueError("An active primary alliance is required")
            owner=primary["id"]
            candidates=db.execute("""SELECT e.id,e.status FROM events e JOIN alliances a ON a.id=e.alliance_id
                WHERE a.group_id=? AND e.event_type=? AND e.occurred_on=?""",(group_id,kind,cycle)).fetchall()
        else:
            if payload.cycle_date is not None:
                raise ValueError("Cycle date applies only to Bear")
            cycle=day
            owner=row["alliance_id"]
            candidates=db.execute("SELECT id,status FROM events WHERE alliance_id=? AND event_type=? AND occurred_on=?",(owner,kind,cycle)).fetchall()
        if payload.event_id:
            chosen=next((x for x in candidates if x["id"]==payload.event_id),None)
            if chosen is None or chosen["status"]!="draft":
                raise ValueError("Select an existing compatible draft event")
            eid=chosen["id"]
        else:
            if candidates:
                raise ValueError("An event already exists on this date; select or link it instead")
            eid=uuid.uuid4().hex
            db.execute("INSERT INTO events(id,alliance_id,event_type,occurred_on,status) VALUES (?,?,?,?,'draft')",(eid,owner,kind,cycle))
            db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES ('created','event',?,'admin')",(eid,))
        sid=None
        if is_session:
            if db.execute("SELECT 1 FROM event_sessions WHERE event_id=? AND session_key=?",(eid,payload.session_key)).fetchone():
                raise ValueError("Session identifier already exists; choose or link the existing session")
            if db.execute("""SELECT 1 FROM event_sessions s JOIN events e ON e.id=s.event_id
                WHERE e.event_type=? AND s.host_alliance_id=? AND substr(s.started_at,1,16)=?""",
                (kind,row["alliance_id"],row["starts_at"][:16])).fetchone():
                raise ValueError("A session already exists at this host and time; link it instead")
            sid=uuid.uuid4().hex
            db.execute("INSERT INTO event_sessions(id,event_id,session_key,started_at,host_alliance_id) VALUES (?,?,?,?,?)",
                (sid,eid,payload.session_key,parse(row["starts_at"]).isoformat(),row["alliance_id"]))
            if kind=="bear_trap":
                db.execute("UPDATE events SET bear_cycle_complete=0 WHERE id=?",(eid,))
            db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES ('session_created','event',?,'admin')",(eid,))
        else:
            # Existing event editor convention for non-battle main sections:
            # the date anchor is not a claimed game start time.
            db.execute("INSERT INTO event_sessions(id,event_id,session_key,started_at,host_alliance_id) VALUES (?,?,?,?,?)",
                (uuid.uuid4().hex,eid,"main",cycle+"T00:00:00+00:00",owner))
        db.execute("""INSERT INTO calendar_event_links(occurrence_id,event_id,session_id) VALUES (?,?,?)
            ON CONFLICT(occurrence_id) DO UPDATE SET session_id=excluded.session_id""",(occurrence_id,eid,sid))
        db.execute("UPDATE calendar_occurrences SET revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",(occurrence_id,))
        audit(db,"draft_created_and_linked",occurrence_id)
    return event_link(path,group_id,occurrence_id)


def draft_bear_cycles(path,group_id,occurrence_id,cycle_date):
    with connection(path) as db:
        row=link_occurrence(db,group_id,occurrence_id)
        if not link_eligible(row) or row["event_type"]!="bear_trap":
            raise ValueError("Choose a Bear schedule")
        if abs((parse(row["starts_at"][:10])-parse(cycle_date.isoformat())).days)>7:
            raise ValueError("Bear cycle date must be within seven days of the trap")
        return {"items":[dict(r) for r in db.execute("""SELECT e.id,e.status,e.occurred_on FROM events e
            JOIN alliances a ON a.id=e.alliance_id WHERE a.group_id=? AND e.event_type='bear_trap' AND e.occurred_on=?
            ORDER BY e.id""",(group_id,cycle_date.isoformat())).fetchall()]}

def review_status(db,group_id,occurrence_ids):
    """Read-only evidence flags, scoped to linked records. No absence inference."""
    if not occurrence_ids:
        return {}
    output={}
    # Chunk to remain within SQLite variable limits on older installations.
    for offset in range(0,len(occurrence_ids),400):
        ids=occurrence_ids[offset:offset+400]
        marks=",".join("?" for _ in ids)
        links=db.execute(f"""SELECT l.occurrence_id,l.event_id,l.session_id,e.event_type,e.status,
            EXISTS(SELECT 1 FROM event_completion_reviews r WHERE r.event_id=e.id) AS final_review
            FROM calendar_event_links l JOIN calendar_occurrences c ON c.id=l.occurrence_id
            JOIN events e ON e.id=l.event_id JOIN alliances a ON a.id=e.alliance_id
            WHERE c.group_id=? AND a.group_id=? AND l.occurrence_id IN ({marks})""",
            (group_id,group_id,*ids)).fetchall()
        event_ids=list({l["event_id"] for l in links})
        if not event_ids:
            continue
        emarks=",".join("?" for _ in event_ids)
        sessions={}
        for s in db.execute(f"""SELECT s.id,s.event_id,s.session_key,s.roster_complete,s.registration_complete,
            s.attendance_complete,s.results_complete,
            EXISTS(SELECT 1 FROM event_session_roster r WHERE r.session_id=s.id) AS has_rows
            FROM event_sessions s WHERE s.event_id IN ({emarks})""",event_ids):
            sessions.setdefault(s["event_id"],[]).append(s)
        for link in links:
            kind=link["event_type"]
            all_sessions=sessions.get(link["event_id"],[])
            relevant=[s for s in all_sessions if not link["session_id"] or s["id"]==link["session_id"]]
            legion=kind in {"foundry","canyon"}
            expected=(1 if link["session_id"] or not legion else 2)
            coverage=len(relevant)>=expected and bool(relevant)
            if legion and not link["session_id"]:
                coverage={s["session_key"] for s in relevant}=={"legion_1","legion_2"}
            def flag(key,applicable=True):
                if not applicable:
                    return "not_applicable"
                if not relevant:
                    return "not_recorded"
                if coverage and all(s["has_rows"] and s[key] for s in relevant):
                    return "reviewed"
                if any(s["has_rows"] or s[key] for s in relevant):
                    return "partial"
                return "not_recorded"
            output[link["occurrence_id"]]={
                "publication":link["status"],
                "scope":"session" if link["session_id"] else "event",
                "session_count":len(relevant),
                "roster":flag("roster_complete"),
                "registration":flag("registration_complete",legion or kind=="alliance_championship"),
                "attendance":flag("attendance_complete",legion or kind=="bear_trap"),
                "results":flag("results_complete",kind!="alliance_championship"),
                "final_attendance_review":bool(link["final_review"] and link["status"]=="published") if legion or kind=="bear_trap" else None,
            }
    return output

class CalendarEntryStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    confirmed: Literal[True]


def start_entry(path,group_id,occurrence_id,payload):
    """Resolve unambiguous records only after an explicit data-entry action."""
    with transaction(path) as db:
        require_group(db,group_id,True)
        row=link_occurrence(db,group_id,occurrence_id)
        validate_scope(db,group_id,CalendarInput(**{k:row[k] for k in CalendarInput.model_fields}))
        if not link_eligible(row):
            raise ValueError("This schedule does not support data entry")
        kind=row["event_type"]
        session_kind=kind in {"bear_trap","foundry","canyon"}
        old=db.execute("SELECT event_id,session_id FROM calendar_event_links WHERE occurrence_id=?",(occurrence_id,)).fetchone()
        if old and (not session_kind or old["session_id"]):
            # A completed link is safe to reopen, including after a lost response.
            pass
        else:
            if row["revision"]!=payload.revision:
                raise ValueError("Calendar entry changed; reload before entering data")
            if row["confidence"]!="confirmed":
                raise ValueError("Confirm the schedule before entering data")
            if kind=="bear_trap" and not row["entry_cycle_date"]:
                raise ValueError("Review the group Bear cycle and trap identity first")
            if session_kind and row["precision"]!="minute":
                raise ValueError("Set the actual session time before entering data")
            if kind=="canyon" and row["phase"].strip().lower() not in {"battle","legion 1","legion 2","legion_1","legion_2"}:
                raise ValueError("Select an explicit Canyon battle schedule")
            day=row["entry_cycle_date"] or row["starts_at"][:10]
            owner=row["alliance_id"]
            event_owner=owner
            if kind=="bear_trap":
                primary=db.execute("SELECT id FROM alliances WHERE group_id=? AND alliance_type='primary' AND status='active'",(group_id,)).fetchone()
                if primary is None:
                    raise ValueError("An active primary alliance is required")
                event_owner=primary["id"]
                events=db.execute("""SELECT e.id,e.status,e.alliance_id FROM events e JOIN alliances a ON a.id=e.alliance_id
                    WHERE a.group_id=? AND e.event_type=? AND e.occurred_on=? ORDER BY e.id""",(group_id,kind,day)).fetchall()
                if any(e["alliance_id"]!=event_owner for e in events):
                    raise ValueError("Existing Bear cycle owner requires review")
            else:
                events=db.execute("SELECT id,status FROM events WHERE alliance_id=? AND event_type=? AND occurred_on=? ORDER BY id",(owner,kind,day)).fetchall()
            if old:
                events=[e for e in events if e["id"]==old["event_id"]]
                if not events:
                    raise ValueError("Existing event link requires review")
            if len(events)>1:
                raise ValueError("Multiple matching events; choose the correct record explicitly")
            eid=events[0]["id"] if events else None
            sid=None
            if session_kind:
                # A legion is not inferred from arbitrary labels or its start time.
                match=re.fullmatch(r"legion[ _]([12])",row["phase"].strip().lower())
                key=row["entry_session_key"] or ("legion_"+match[1] if match else None)
                if eid:
                    sessions=db.execute("SELECT id,session_key,started_at,host_alliance_id FROM event_sessions WHERE event_id=?",(eid,)).fetchall()
                    matches=[s for s in sessions if s["host_alliance_id"]==owner and s["started_at"][:16]==row["starts_at"][:16]]
                    if len(matches)>1:
                        raise ValueError("Multiple matching sessions; choose explicitly")
                    if matches:
                        if key and matches[0]["session_key"]!=key:
                            raise ValueError("Schedule legion and existing session disagree")
                        sid=matches[0]["id"]
                        if db.execute("SELECT 1 FROM calendar_event_links WHERE session_id=? AND occurrence_id<>?",(sid,occurrence_id)).fetchone():
                            raise ValueError("This session is already linked to another schedule")
                    elif not key or any(s["session_key"]==key for s in sessions):
                        raise ValueError("Review the legion identity and existing sessions first")
                if not sid and not key:
                    raise ValueError("Choose the legion explicitly before entering data")
                if not sid and db.execute("""SELECT 1 FROM event_sessions s JOIN events e ON e.id=s.event_id
                    WHERE e.event_type=? AND s.host_alliance_id=? AND substr(s.started_at,1,16)=?""",(kind,owner,row["starts_at"][:16])).fetchone():
                    raise ValueError("A session already exists at this host and time; review it first")
            if eid and not session_kind and db.execute("SELECT 1 FROM calendar_event_links WHERE event_id=? AND occurrence_id<>?",(eid,occurrence_id)).fetchone():
                raise ValueError("Event already linked to another schedule; review existing links")
            if eid and session_kind and not sid and events[0]["status"]!="draft":
                raise ValueError("Reopen the existing published event before adding a session")
            if not eid:
                eid=uuid.uuid4().hex
                db.execute("INSERT INTO events(id,alliance_id,event_type,occurred_on,status) VALUES (?,?,?,?,'draft')",(eid,event_owner,kind,day))
                db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES ('created','event',?,'admin')",(eid,))
                if not session_kind:
                    db.execute("INSERT INTO event_sessions(id,event_id,session_key,started_at,host_alliance_id) VALUES (?,?,?,?,?)",
                        (uuid.uuid4().hex,eid,"main",day+"T00:00:00+00:00",owner))
            if session_kind and not sid:
                sid=uuid.uuid4().hex
                db.execute("INSERT INTO event_sessions(id,event_id,session_key,started_at,host_alliance_id) VALUES (?,?,?,?,?)",
                    (sid,eid,key,parse(row["starts_at"]).isoformat(),owner))
                if kind=="bear_trap":
                    db.execute("UPDATE events SET bear_cycle_complete=0 WHERE id=?",(eid,))
                db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES ('session_created','event',?,'admin')",(eid,))
            db.execute("""INSERT INTO calendar_event_links(occurrence_id,event_id,session_id) VALUES (?,?,?)
                ON CONFLICT(occurrence_id) DO UPDATE SET session_id=excluded.session_id""",(occurrence_id,eid,sid))
            db.execute("UPDATE calendar_occurrences SET revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",(occurrence_id,))
            audit(db,"data_entry_started",occurrence_id)
    return event_link(path,group_id,occurrence_id)

class EntryGrouping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    cycle_date: date | None = None
    session_key: str | None = Field(default=None,max_length=32)

    @model_validator(mode="after")
    def paired(self):
        if (self.cycle_date is None)!=(self.session_key is None):
            raise ValueError("Provide both cycle date and session identity, or clear both")
        return self


def require_open_cycle_for_grouping(db, group_id, kind, day, owner):
    if day is None:
        return
    if db.execute("""SELECT 1 FROM events e JOIN alliances a ON a.id=e.alliance_id
        WHERE a.group_id=? AND e.event_type=? AND e.occurred_on=? AND e.status='published'
        AND (?='bear_trap' OR e.alliance_id=?) AND
        (e.bear_cycle_complete=1 OR EXISTS(SELECT 1 FROM event_completion_reviews r WHERE r.event_id=e.id))""",
        (group_id,kind,day,kind,owner)).fetchone():
        raise ValueError("Reopen the finalized event before changing its planned cycle")


def set_entry_grouping(path,group_id,occurrence_id,payload):
    with transaction(path) as db:
        require_group(db,group_id,True)
        row=link_occurrence(db,group_id,occurrence_id)
        if row["revision"]!=payload.revision:
            raise ValueError("Calendar entry changed; reload before grouping")
        if db.execute("SELECT 1 FROM calendar_event_links WHERE occurrence_id=?",(occurrence_id,)).fetchone():
            raise ValueError("Unlink the actual record before changing session grouping")
        kind=row["event_type"]
        require_open_cycle_for_grouping(db,group_id,kind,row["entry_cycle_date"],row["alliance_id"])
        if payload.cycle_date is not None:
            validate_scope(db,group_id,CalendarInput(**{k:row[k] for k in CalendarInput.model_fields}))
            if not link_eligible(row) or kind not in {"bear_trap","foundry","canyon"}:
                raise ValueError("Choose a supported alliance battle or trap schedule")
            if kind=="canyon" and row["phase"].strip().lower() not in {"battle","legion 1","legion 2","legion_1","legion_2"}:
                raise ValueError("Choose an explicit Canyon battle phase")
            if not 2000<=payload.cycle_date.year<=2099 or abs((parse(row["starts_at"][:10]).date()-payload.cycle_date).days)>7:
                raise ValueError("Cycle date must be within seven days of this schedule")
            pattern=r"trap_(?:[1-9]|[12][0-9]|30)" if kind=="bear_trap" else r"legion_[12]"
            if not re.fullmatch(pattern,payload.session_key or ""):
                raise ValueError("Invalid group session identity")
            label=re.fullmatch(r"legion[ _]([12])",row["phase"].strip().lower())
            if kind!="bear_trap" and label and payload.session_key!="legion_"+label[1]:
                raise ValueError("Session identity disagrees with the scheduled legion")
            require_open_cycle_for_grouping(db,group_id,kind,payload.cycle_date.isoformat(),row["alliance_id"])
            duplicate=db.execute("""SELECT 1 FROM calendar_occurrences WHERE group_id=? AND event_type=?
                AND entry_cycle_date=? AND entry_session_key=? AND id<>?
                AND (?='bear_trap' OR alliance_id=?)""",(group_id,kind,payload.cycle_date.isoformat(),payload.session_key,occurrence_id,kind,row["alliance_id"])).fetchone()
            if duplicate:
                raise ValueError("Session identity already assigned in this cycle")
        db.execute("UPDATE calendar_occurrences SET entry_cycle_date=?,entry_session_key=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (payload.cycle_date.isoformat() if payload.cycle_date else None,payload.session_key,occurrence_id))
        audit(db,"session_grouping_changed",occurrence_id)
    return event_link(path,group_id,occurrence_id)


def entry_group_members(db,row):
    if not row["entry_cycle_date"]:
        return []
    return [dict(r) for r in db.execute("""SELECT c.id,c.alliance_id,c.starts_at,c.precision,c.entry_session_key,c.confidence,c.schedule_status,a.tag,
        EXISTS(SELECT 1 FROM calendar_event_links l WHERE l.occurrence_id=c.id) AS linked
        FROM calendar_occurrences c JOIN alliances a ON a.id=c.alliance_id
        WHERE c.group_id=? AND c.event_type=? AND c.entry_cycle_date=?
        AND (?='bear_trap' OR c.alliance_id=?) ORDER BY c.starts_at,c.id""",
        (row["group_id"],row["event_type"],row["entry_cycle_date"],row["event_type"],row["alliance_id"]))]
