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
        if self.event_type not in CATALOG_IDS and self.event_type not in {"svs_matchmaking","svs_triage"} and self.event_type not in {e.value for e in EventType}:
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
        if self.event_type in {"svs_matchmaking","svs_triage"} and self.scope!="state":
            raise ValueError("SvS phases require state scope")
        if (self.scope == "alliance") != bool(self.alliance_id):
            raise ValueError("Alliance scope requires an alliance; state scope does not")
        return self


class CalendarCreate(CalendarInput):
    request_key: str | None = Field(default=None, min_length=16, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')
    interval_minutes: int | None = Field(default=None, ge=60, le=525600)
    occurrence_count: int = Field(default=1, ge=1, le=180)
    reject_existing: bool = False
    rolling: bool = False
    bear_cycle_anchor: str | None = None
    bear_session_key: str | None = Field(default=None,max_length=32)
    repeat_months: int | None = Field(default=None, ge=1, le=12)
    repeat_weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)

    @model_validator(mode="after")
    def validate_series(self):
        if (self.bear_cycle_anchor is None)!=(self.bear_session_key is None):
            raise ValueError("Provide both shared Bear cycle anchor and trap identity")
        if self.bear_cycle_anchor is not None:
            if self.event_type!="bear_trap" or self.scope!="alliance" or self.precision!="minute" or not self.reject_existing or self.occurrence_count<2 or self.interval_minutes is None or not 1440<=self.interval_minutes<=10080:
                raise ValueError("Bear grouping requires a timed alliance series with a fixed 1–7 day interval and duplicate protection")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z",self.bear_cycle_anchor) or not re.fullmatch(r"trap_(?:[1-9]|[12][0-9]|30)",self.bear_session_key or ""):
                raise ValueError("Choose a UTC cycle anchor and unique trap identity")
            anchor=parse(self.bear_cycle_anchor)
            if not 2000<=anchor.year<=2099 or not timedelta(0)<=parse(self.starts_at)-anchor<timedelta(minutes=self.interval_minutes):
                raise ValueError("First trap must fall within the first shared Bear cycle")
        if self.rolling and (not self.reject_existing or self.interval_minutes is None or self.interval_minutes < 1440 or not 2 <= self.occurrence_count <= 60):
            raise ValueError("Automatic renewal requires a fixed interval of at least one day and 2–60 initial occurrences with duplicate protection")
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


# These two source relationships have an unambiguous date offset and duration.
# Other conditional rotations require locally reviewed dates and are not fabricated.
FOLLOW_RULES={
    "game:flame-and-fang":("svs_preparation",None,3,"SvS preparation"),
    "game:crystal-reactivation-2":("castle_battle",4,2,"Sunfire Castle battle week"),
}


class FollowSchedule(BaseModel):
    model_config=ConfigDict(extra="forbid")
    event_type: Literal["game:flame-and-fang","game:crystal-reactivation-2"]
    state_id: str=Field(min_length=1,max_length=32)
    starts_on: date


def validate_follow(db,group_id,payload,writing=False):
    require_group(db,group_id,writing)
    if not 2000<=payload.starts_on.year<=2099:
        raise ValueError("Date outside supported range")
    if not db.execute("SELECT 1 FROM alliances WHERE group_id=? AND state_id=? AND status='active'",(group_id,payload.state_id)).fetchone():
        raise ValueError("State must belong to an active alliance in this group")


def project_follow(db,rule,start,end):
    parent_type,weekday,length,label=FOLLOW_RULES[rule["event_type"]]
    parents=db.execute("""SELECT * FROM calendar_occurrences
        WHERE group_id=? AND state_id=? AND scope='state' AND event_type=? AND starts_at>=? AND starts_at<?
        ORDER BY starts_at,id""",(rule["group_id"],rule["state_id"],parent_type,
        (start-timedelta(days=7)).isoformat(),(end+timedelta(days=7)).isoformat())).fetchall()
    # Existing manual entries, including cancellations, take precedence over a projection.
    manual=db.execute("""SELECT starts_at,ends_at,precision FROM calendar_occurrences
        WHERE group_id=? AND state_id=? AND event_type=? AND starts_at<? AND
        (starts_at>=? OR ends_at>?)""",(rule["group_id"],rule["state_id"],rule["event_type"],end.isoformat(),
        (start-timedelta(days=7)).isoformat(),(start-timedelta(days=7)).isoformat())).fetchall()
    by_day={}
    for parent in parents:
        day=parse(parent["starts_at"]).date()
        if weekday is not None:
            day+=timedelta(days=weekday-day.weekday())
        finish=day+timedelta(days=length)
        if day.year<2000 or finish.year>2099 or day.isoformat()<rule["starts_on"] or rule["stopped_on"] and day.isoformat()>=rule["stopped_on"]:
            continue
        if not (day<end and finish>start):
            continue
        lo=datetime.combine(day,datetime.min.time(),timezone.utc)
        hi=datetime.combine(finish,datetime.min.time(),timezone.utc)
        if any(cycle_span([r])[0]<hi and cycle_span([r])[1]>lo for r in manual):
            continue
        existing=by_day.get(day)
        if existing and (existing["schedule_status"]=="scheduled" or parent["schedule_status"]!="scheduled"):
            continue
        by_day[day]={"id":"follow:"+rule["id"]+":"+parent["id"],"group_id":rule["group_id"],
            "series_id":None,"cycle_id":None,"sequence":0,"event_type":rule["event_type"],"scope":"state",
            "alliance_id":None,"state_id":rule["state_id"],"starts_at":day.isoformat(),"ends_at":finish.isoformat(),
            "precision":"date","phase":"","confidence":"estimated","schedule_status":parent["schedule_status"],
            "source":"recurrence","revision":parent["revision"],"follow_rule_id":rule["id"],
            "follow_parent_id":parent["id"],"follow_parent_label":label,"follow_active":rule["stopped_on"] is None}
    return sorted(by_day.values(),key=lambda r:(r["starts_at"],r["id"]))


def follow_plan(db,group_id,payload):
    rule=db.execute("""SELECT * FROM calendar_follow_rules WHERE group_id=? AND state_id=? AND event_type=? AND stopped_on IS NULL""",
        (group_id,payload.state_id,payload.event_type)).fetchone()
    proposed=rule or {"id":"preview","group_id":group_id,"state_id":payload.state_id,"event_type":payload.event_type,
        "starts_on":payload.starts_on.isoformat(),"stopped_on":None}
    end=min(payload.starts_on+timedelta(days=61),date(2100,1,1))
    return {"active_rule_id":rule["id"] if rule else None,"active_from":rule["starts_on"] if rule else None,
        "items":project_follow(db,proposed,payload.starts_on,end)}


def preview_follow(path,group_id,payload):
    with connection(path) as db:
        validate_follow(db,group_id,payload)
        return follow_plan(db,group_id,payload)


def enable_follow(path,group_id,payload):
    with transaction(path) as db:
        validate_follow(db,group_id,payload,True)
        plan=follow_plan(db,group_id,payload)
        if plan["active_rule_id"]:
            if plan["active_from"]!=payload.starts_on.isoformat():
                raise ValueError("A follow rule is already active. Stop it before changing the start date.")
            return plan
        last=db.execute("""SELECT MAX(stopped_on) FROM calendar_follow_rules WHERE group_id=? AND state_id=? AND event_type=?""",
            (group_id,payload.state_id,payload.event_type)).fetchone()[0]
        if last and payload.starts_on.isoformat()<last:
            raise ValueError("Start after the previous follow period to preserve its history")
        if db.execute("""SELECT 1 FROM calendar_occurrences WHERE group_id=? AND state_id=? AND event_type=? AND
            schedule_status='scheduled' AND (starts_at>=? OR ends_at>?)""",
            (group_id,payload.state_id,payload.event_type,payload.starts_on.isoformat(),payload.starts_on.isoformat())).fetchone():
            raise ValueError("Independent schedules already exist. Review or cancel them before following the parent event.")
        for series in db.execute("""SELECT r.template_json FROM calendar_rolling_series r JOIN calendar_series s ON s.id=r.series_id
            WHERE s.group_id=? AND r.status IN ('active','conflict')""",(group_id,)):
            template=json.loads(series["template_json"])
            if template.get("state_id")==payload.state_id and template.get("event_type")==payload.event_type:
                raise ValueError("Stop the independent rolling schedule before following the parent event.")
        oid=uuid.uuid4().hex
        db.execute("""INSERT INTO calendar_follow_rules(id,group_id,state_id,event_type,starts_on) VALUES (?,?,?,?,?)""",
            (oid,group_id,payload.state_id,payload.event_type,payload.starts_on.isoformat()))
        audit(db,"follow_enabled",oid)
        return follow_plan(db,group_id,payload)


def stop_follow(path,group_id,rule_id):
    with transaction(path) as db:
        require_group(db,group_id,True)
        row=db.execute("SELECT * FROM calendar_follow_rules WHERE group_id=? AND id=?",(group_id,rule_id)).fetchone()
        if not row:
            raise LookupError("Follow rule not found")
        if not row["stopped_on"]:
            # Retain today's already-started event and earlier projections.
            stop=max(row["starts_on"],(datetime.now(timezone.utc).date()+timedelta(days=1)).isoformat())
            db.execute("UPDATE calendar_follow_rules SET stopped_on=? WHERE id=?",(stop,rule_id))
            audit(db,"follow_stopped",rule_id)
        return {"stopped":True}


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
        rolling = {r["series_id"]:r["status"] for r in db.execute(
            "SELECT r.series_id,r.status FROM calendar_rolling_series r JOIN calendar_series s ON s.id=r.series_id WHERE s.group_id=?",(group_id,))}
        items=[{**dict(row),**({"review":progress[row["id"]]} if row["id"] in progress else {}),
                         **({"rolling_status":rolling[row["series_id"]]} if row["series_id"] in rolling else {})} for row in rows]
        for rule in db.execute("""SELECT * FROM calendar_follow_rules WHERE group_id=? AND starts_on<?
            AND (stopped_on IS NULL OR stopped_on>?)""",(group_id,end.isoformat(),(start-timedelta(days=3)).isoformat())):
            items.extend(project_follow(db,rule,start,end))
        if len(items)>2000:
            raise ValueError("Too many calendar entries; select a shorter range")
        return {"items":sorted(items,key=lambda r:(r["starts_at"],r["id"]))}


def create(path, group_id, payload: CalendarCreate):
    with transaction(path) as db:
        return create_in_transaction(db,group_id,payload)


def create_in_transaction(db, group_id, payload: CalendarCreate):
    # Preserve the v1 request hash when the new opt-in field is false.
    excluded = {"request_key"} if payload.reject_existing else {"request_key", "reject_existing"}
    excluded.update(k for k in ("repeat_months","repeat_weekdays") if getattr(payload,k) is None)
    if not payload.rolling:
        excluded.add("rolling")
    if payload.bear_cycle_anchor is None:
        excluded.update(("bear_cycle_anchor","bear_session_key"))
    offsets = series_offsets(payload)
    fingerprint = hashlib.sha256(json.dumps(payload.model_dump(mode="json", exclude=excluded), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require_group(db, group_id, True)
    if payload.request_key:
        previous = db.execute("SELECT payload_hash, occurrence_ids FROM calendar_create_requests WHERE group_id=? AND request_key=?", (group_id, payload.request_key)).fetchone()
        if previous:
            if previous["payload_hash"] != fingerprint:
                raise ValueError("Request key already used for a different schedule")
            return {"items": [dict(db.execute("SELECT * FROM calendar_occurrences WHERE group_id=? AND id=?", (group_id, oid)).fetchone()) for oid in json.loads(previous["occurrence_ids"])]}
    validate_scope(db, group_id, payload)
    if payload.event_type in FOLLOW_RULES and db.execute("""SELECT 1 FROM calendar_follow_rules
        WHERE group_id=? AND state_id=? AND event_type=? AND stopped_on IS NULL""",
        (group_id,payload.state_id,payload.event_type)).fetchone():
        raise ValueError("This event follows its parent schedule. Stop the follow rule before creating independent dates.")
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
        elif payload.bear_cycle_anchor is not None:
            db.execute("INSERT INTO calendar_series_rules(series_id,rule_json) VALUES (?,?)",(series_id,json.dumps({"bear_cycle_anchor":payload.bear_cycle_anchor,"bear_session_key":payload.bear_session_key})))
    if payload.rolling:
        template = CalendarInput(**{k:getattr(payload,k) for k in CalendarInput.model_fields})
        db.execute("INSERT INTO calendar_rolling_series(series_id,template_json,next_start,next_sequence) VALUES (?,?,?,?)",
                   (series_id,template.model_dump_json(),shift(payload.starts_at,payload.interval_minutes*payload.occurrence_count),payload.occurrence_count))
    items=[]
    for sequence,offset in enumerate(offsets):
        occurrence_id=uuid.uuid4().hex
        db.execute("""INSERT INTO calendar_occurrences(id,group_id,series_id,sequence,event_type,scope,alliance_id,state_id,starts_at,ends_at,precision,phase,confidence,source)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (occurrence_id,group_id,series_id,sequence,payload.event_type,payload.scope,payload.alliance_id,payload.state_id,shift(payload.starts_at,offset),shift(payload.ends_at,offset),payload.precision,payload.phase,payload.confidence if sequence==0 else "estimated","manual" if sequence==0 else "recurrence"))
        if payload.bear_cycle_anchor is not None:
            cycle_day,key=bear_assignment(db,group_id,payload.alliance_id,shift(payload.starts_at,offset),payload.bear_cycle_anchor,payload.bear_session_key,payload.interval_minutes,sequence,occurrence_id)
            db.execute("UPDATE calendar_occurrences SET entry_cycle_date=?,entry_session_key=? WHERE id=?",(cycle_day,key,occurrence_id))
        audit(db,"created",occurrence_id)
        items.append(dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (occurrence_id,)).fetchone()))
    if payload.request_key:
        db.execute("INSERT INTO calendar_create_requests(group_id,request_key,payload_hash,occurrence_ids) VALUES (?,?,?,?)", (group_id,payload.request_key,fingerprint,json.dumps([item["id"] for item in items])))
    return {"items":items}


class BearTrapSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alliance_id: str = Field(min_length=1,max_length=64)
    starts_at: str


class BearScheduleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cycle_date: date
    interval_minutes: int = Field(default=2880,ge=2850,le=10080)
    traps: list[BearTrapSlot] = Field(min_length=1,max_length=30)
    rolling: bool = True
    confirmed: Literal[True]
    request_key: str = Field(min_length=16,max_length=128,pattern=r"^[A-Za-z0-9_-]+$")

    @model_validator(mode="after")
    def validate_traps(self):
        if not 2000<=self.cycle_date.year<=2099:
            raise ValueError("Date outside supported range")
        starts=[]
        for slot in self.traps:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z",slot.starts_at):
                raise ValueError("Enter each trap's UTC date and minute")
            starts.append(parse(slot.starts_at))
        anchor=min(starts)
        if anchor.date()!=self.cycle_date:
            raise ValueError("The first trap must start on the selected first cycle date")
        if any(start-anchor>=timedelta(minutes=self.interval_minutes) for start in starts):
            raise ValueError("Every trap must start within the first shared cycle")
        if len({(slot.alliance_id,slot.starts_at) for slot in self.traps})!=len(self.traps):
            raise ValueError("Duplicate trap time for the same alliance")
        return self


def create_bear_schedule(path,group_id,payload: BearScheduleCreate):
    """Create all trap series or none, using the existing recurrence/grouping checks."""
    fingerprint=hashlib.sha256(("bear-batch:"+payload.model_dump_json(exclude={"request_key"})).encode()).hexdigest()
    with transaction(path) as db:
        require_group(db,group_id,True)
        previous=db.execute("SELECT payload_hash,occurrence_ids FROM calendar_create_requests WHERE group_id=? AND request_key=?",(group_id,payload.request_key)).fetchone()
        if previous:
            if previous["payload_hash"]!=fingerprint:
                raise ValueError("Request key already used for a different schedule")
            return {"items":[dict(db.execute("SELECT * FROM calendar_occurrences WHERE group_id=? AND id=?",(group_id,oid)).fetchone()) for oid in json.loads(previous["occurrence_ids"])]}
        anchor=min(slot.starts_at for slot in payload.traps)
        if parse(anchor).date()<datetime.now(timezone.utc).date():
            raise ValueError("Choose today or a future first cycle")
        # A full 60-day window is ready immediately. Renewal extends the cursor
        # on its normal hourly schedule; finite mode creates just four cycles.
        count=min(60,1+60*1440//payload.interval_minutes) if payload.rolling else 4
        items=[]
        for i,slot in enumerate(payload.traps,1):
            owner=db.execute("SELECT state_id FROM alliances WHERE id=? AND group_id=? AND status='active'",(slot.alliance_id,group_id)).fetchone()
            if owner is None:
                raise LookupError("Active alliance not found in selected group")
            series=CalendarCreate(event_type="bear_trap",scope="alliance",alliance_id=slot.alliance_id,state_id=owner["state_id"],
                starts_at=slot.starts_at,ends_at=shift(slot.starts_at,30),precision="minute",phase=f"Trap {i}",
                confidence="confirmed",interval_minutes=payload.interval_minutes,occurrence_count=count,
                reject_existing=True,rolling=payload.rolling,bear_cycle_anchor=anchor,bear_session_key=f"trap_{i}")
            items.extend(create_in_transaction(db,group_id,series)["items"])
        db.execute("INSERT INTO calendar_create_requests(group_id,request_key,payload_hash,occurrence_ids) VALUES (?,?,?,?)",
                   (group_id,payload.request_key,fingerprint,json.dumps([item["id"] for item in items])))
        return {"items":items}


def update(path, group_id, occurrence_id, payload: CalendarUpdate):
    with transaction(path) as db:
        return update_locked(db,group_id,occurrence_id,payload)


def update_locked(db,group_id,occurrence_id,payload):
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
    linked_legion=bool(row["cycle_id"] and row["event_type"] in {"foundry","canyon"} and row["phase"] in {"Legion 1","Legion 2"})
    if linked_legion and row["entry_cycle_date"]:
        require_open_cycle_for_grouping(db,group_id,row["event_type"],row["entry_cycle_date"],row["alliance_id"])
        if payload.starts_at[:10]!=row["entry_cycle_date"]:
            raise ValueError("Legion must stay on the shared battle date")
    if not linked_legion and row["entry_cycle_date"] and any(row[k]!=getattr(payload,k) for k in ("event_type","scope","alliance_id","state_id","phase","starts_at","ends_at","precision","schedule_status")):
        grouping=bear_series_rule(db,row["series_id"])
        if not grouping or any(row[k]!=getattr(payload,k) for k in ("event_type","scope","alliance_id","state_id","phase","precision")):
            raise ValueError("Clear the session grouping before changing its identity")
        require_open_cycle_for_grouping(db,group_id,row["event_type"],row["entry_cycle_date"],row["alliance_id"])
        if parse(row["starts_at"])<future_threshold(row["precision"],datetime.now(timezone.utc)) or parse(payload.starts_at)<future_threshold(row["precision"],datetime.now(timezone.utc)):
            raise ValueError("Choose a future Bear occurrence")
        series,_=series_metadata(db,row["series_id"])
        cycle_day,key=bear_assignment(db,group_id,row["alliance_id"],payload.starts_at,grouping["bear_cycle_anchor"],grouping["bear_session_key"],series["interval_minutes"],row["sequence"],row["id"],allow_before=True)
        if (cycle_day,key)!=(row["entry_cycle_date"],row["entry_session_key"]):
            raise ValueError("This trap has a manually changed cycle identity; review its grouping first")
    if row["cycle_id"]:
        if any(row[k]!=getattr(payload,k) for k in ("event_type","scope","alliance_id","state_id","phase")):
            raise ValueError("Cycle phase identity and owner cannot be changed")
        siblings=db.execute("SELECT * FROM calendar_occurrences WHERE group_id=? AND cycle_id=? AND id!=? ORDER BY starts_at",(group_id,row["cycle_id"],occurrence_id)).fetchall()
        for sibling in siblings:
            if linked_legion and sibling["phase"] in {"Legion 1","Legion 2"}:
                if payload.precision==sibling["precision"]=="minute" and payload.starts_at==sibling["starts_at"]:
                    raise ValueError("Choose distinct legion start times")
                continue
            if parse(sibling["starts_at"])<parse(row["starts_at"]):
                if parse(payload.starts_at)<=parse(sibling["starts_at"]) or (sibling["ends_at"] and parse(payload.starts_at)<parse(sibling["ends_at"])):
                    raise ValueError("Phase would cross an earlier cycle phase")
            elif parse(payload.starts_at)>=parse(sibling["starts_at"]) or (payload.ends_at and parse(payload.ends_at)>parse(sibling["starts_at"])):
                raise ValueError("Phase would cross a later cycle phase")
        if any(row[k]!=getattr(payload,k) for k in ("starts_at","ends_at","precision")):
            proposed=[{**dict(row),**payload.model_dump()}]+[dict(s) for s in siblings]
            validate_cycle_overlap(db,group_id,proposed,{r["id"] for r in proposed})
    db.execute("""UPDATE calendar_occurrences SET event_type=?,scope=?,alliance_id=?,state_id=?,starts_at=?,ends_at=?,precision=?,phase=?,confidence=?,schedule_status=?,source='manual',revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND group_id=?""",
      (payload.event_type,payload.scope,payload.alliance_id,payload.state_id,payload.starts_at,payload.ends_at,payload.precision,payload.phase,payload.confidence,payload.schedule_status,occurrence_id,group_id))
    audit(db,"cancelled" if payload.schedule_status=="cancelled" else "updated",occurrence_id)
    return dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (occurrence_id,)).fetchone())


class CalendarFutureChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["shift", "cancel", "edit"]
    schedule: CalendarUpdate | None = None
    interval_minutes: int | None = Field(default=None,ge=60,le=525600)
    shift_minutes: int = Field(default=0, ge=-527040, le=527040)
    revisions: dict[str, int] = Field(min_length=1, max_length=180)

    @model_validator(mode="after")
    def validate_action(self):
        if (self.action == "shift") != (self.shift_minutes != 0):
            raise ValueError("Only a shift requires a nonzero offset")
        if (self.action == "edit") != (self.schedule is not None) or (self.action!="edit" and self.interval_minutes is not None):
            raise ValueError("Series edit requires a schedule; interval is only valid for an edit")
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
        rows=future_rows(db,group_id,occurrence_id)
        series,rule=series_metadata(db,rows[0]["series_id"])
        return {"items":rows,"interval_minutes":None if rule.get("repeat_months") or rule.get("repeat_weekdays") else series["interval_minutes"]}


def edit_future_series(db,group_id,rows,payload,now):
    """Edit a reviewed suffix in one transaction, without touching history or actual records."""
    selected=rows[0]
    schedule=payload.schedule
    identity=("event_type","scope","alliance_id","state_id","phase","precision")
    if schedule.revision!=selected["revision"] or schedule.schedule_status!="scheduled":
        raise ValueError("Reload the selected scheduled occurrence")
    if any(any(row[k]!=getattr(schedule,k) for k in identity) for row in rows):
        raise ValueError("Series edits must preserve event type, owner, phase and precision")
    validate_scope(db,group_id,schedule)
    sid=selected["series_id"]
    series,rule=series_metadata(db,sid)
    grouping=rule if rule.get("bear_cycle_anchor") else None
    fixed=not (rule.get("repeat_months") or rule.get("repeat_weekdays"))
    if not fixed and payload.interval_minutes is not None:
        raise ValueError("Calendar-month and weekday series retain their repeat rules")
    interval=payload.interval_minutes or series["interval_minutes"]
    changing=fixed and interval!=series["interval_minutes"]
    if schedule.precision=="date" and fixed and interval%1440:
        raise ValueError("Date-only recurrence requires whole days")
    if grouping and not 1440<=interval<=10080:
        raise ValueError("Bear cycle interval must be 1–7 days")
    moving={r["id"] for r in rows}
    cut=selected["sequence"]
    rolling=db.execute("SELECT * FROM calendar_rolling_series WHERE series_id=?",(sid,)).fetchone()
    if rolling and interval<1440:
        raise ValueError("Automatic renewal requires an interval of at least one day")
    new_sid=sid
    anchor=grouping["bear_cycle_anchor"] if grouping else None
    if changing:
        tail=db.execute("SELECT id,sequence FROM calendar_occurrences WHERE series_id=? AND sequence>=? ORDER BY sequence",(sid,cut)).fetchall()
        if len(rows)<2 or {r["id"] for r in tail}!=moving or [r["sequence"] for r in tail]!=list(range(cut,cut+len(rows))):
            raise ValueError("Changing cadence requires at least two consecutive future occurrences without cancelled, elapsed or manual exceptions")
        if not grouping and any(r["entry_cycle_date"] for r in rows):
            raise ValueError("Review manually grouped sessions before changing cadence")
        if grouping:
            canonical=parse(anchor)+timedelta(minutes=series["interval_minutes"]*cut)
            # Other active Bear series must not silently diverge. Time-only edits remain independent.
            peers=db.execute("""SELECT 1 FROM calendar_occurrences WHERE group_id=? AND event_type='bear_trap'
                AND series_id IS NOT ? AND entry_cycle_date>=? AND schedule_status='scheduled' LIMIT 1""",
                (group_id,sid,canonical.date().isoformat())).fetchone()
            active_peers=db.execute("""SELECT r.rule_json FROM calendar_series_rules r JOIN calendar_series s ON s.id=r.series_id
                JOIN calendar_rolling_series n ON n.series_id=s.id WHERE s.group_id=? AND s.id<>? AND n.status IN ('active','conflict')""",(group_id,sid)).fetchall()
            if peers or any(json.loads(p["rule_json"]).get("bear_cycle_anchor") for p in active_peers):
                raise ValueError("Other Bear traps share the group schedule. Changing cadence requires a coordinated cycle change; time-only edits are independent")
            if any(not r["entry_cycle_date"] or r["entry_session_key"]!=grouping["bear_session_key"] for r in rows):
                raise ValueError("Review manually changed Bear grouping before changing cadence")
            anchor=canonical.strftime("%Y-%m-%dT%H:%MZ")
        new_sid=uuid.uuid4().hex
    start0=parse(schedule.starts_at)
    duration=parse(schedule.ends_at)-start0 if schedule.ends_at else None
    fmt="%Y-%m-%d" if schedule.precision=="date" else "%Y-%m-%dT%H:%MZ"
    offset=start0-parse(selected["starts_at"])
    proposed=[]
    for row in rows:
        index=row["sequence"]-cut
        seq=index if changing else row["sequence"]
        start=start0+timedelta(minutes=interval*index) if fixed else parse(row["starts_at"])+offset
        end=start+duration if duration is not None else None
        if start<future_threshold(schedule.precision,now) or not 2000<=start.year<=2099 or (end and not 2000<=end.year<=2099):
            raise ValueError("Series edit would move an occurrence outside future supported dates")
        value=start.strftime(fmt)
        finish=end.strftime(fmt) if end else None
        matches=db.execute("""SELECT id,starts_at,precision,phase FROM calendar_occurrences
            WHERE group_id=? AND event_type=? AND scope=? AND alliance_id IS ? AND state_id=?
            AND (phase=? OR event_type='bear_trap') AND starts_at>=? AND starts_at<?""",
            (group_id,schedule.event_type,schedule.scope,schedule.alliance_id,schedule.state_id,schedule.phase,
             value[:10],(start.date()+timedelta(days=1)).isoformat())).fetchall()
        def conflict(m):
            return m["starts_at"]==value or (m["starts_at"][:10]==value[:10] and (m["precision"]=="date" or schedule.precision=="date"))
        if any(m["id"] not in moving and conflict(m) for m in matches) or any(conflict(m) for m in proposed):
            raise ValueError("Series edit would duplicate an existing scheduled or cancelled occurrence")
        cycle_day,key=row["entry_cycle_date"],row["entry_session_key"]
        if cycle_day:
            require_open_cycle_for_grouping(db,group_id,row["event_type"],cycle_day,row["alliance_id"])
            if not grouping:
                if (value,finish)!=(row["starts_at"],row["ends_at"]):
                    raise ValueError("Review manually grouped sessions before editing their series")
            else:
                expected_old=(parse(grouping["bear_cycle_anchor"])+timedelta(minutes=series["interval_minutes"]*row["sequence"])).date().isoformat()
                if (cycle_day,key)!=(expected_old,grouping["bear_session_key"]):
                    raise ValueError("Review manually changed Bear grouping before editing the series")
                cycle_day,key=bear_assignment(db,group_id,row["alliance_id"],value,anchor,grouping["bear_session_key"],interval,seq,
                                              row["id"],allow_before=True,ignore_ids=moving)
        if cycle_day and any((m["entry_cycle_date"],m["entry_session_key"])==(cycle_day,key) for m in proposed):
            raise ValueError("Series edit would duplicate a Bear cycle identity")
        proposed.append({**row,"starts_at":value,"ends_at":finish,"entry_cycle_date":cycle_day,"entry_session_key":key,"sequence":seq})
    next_start=None
    next_sequence=None
    if rolling:
        next_sequence=rolling["next_sequence"]-cut if changing else rolling["next_sequence"]
        next_date=start0+timedelta(minutes=interval*(rolling["next_sequence"]-cut))
        if next_sequence<2 or next_date<future_threshold(schedule.precision,now) or next_date.year>2099:
            raise ValueError("Next automatic occurrence would fall outside future supported dates")
        if grouping:
            canonical=parse(anchor)+timedelta(minutes=interval*next_sequence)
            if not -timedelta(minutes=interval)<next_date-canonical<timedelta(minutes=interval):
                raise ValueError("Next automatic Bear trap would leave its shared cycle")
        next_start=next_date.strftime(fmt)
    if changing:
        db.execute("INSERT INTO calendar_series(id,group_id,interval_minutes,occurrence_count,anchor) VALUES (?,?,?,?,?)",
                   (new_sid,group_id,interval,len(rows),schedule.starts_at))
        if grouping:
            db.execute("UPDATE calendar_series_rules SET rule_json=? WHERE series_id=?",(json.dumps({**rule,"end_sequence":cut}),sid))
            db.execute("INSERT INTO calendar_series_rules(series_id,rule_json) VALUES (?,?)",
                       (new_sid,json.dumps({"bear_cycle_anchor":anchor,"bear_session_key":grouping["bear_session_key"]})))
        if rolling:
            db.execute("UPDATE calendar_rolling_series SET status='stopped' WHERE series_id=?",(sid,))
        # Avoid transient uniqueness conflicts when cycle dates move during a cadence change.
        for r in rows:
            db.execute("UPDATE calendar_occurrences SET entry_cycle_date=NULL,entry_session_key=NULL WHERE id=?",(r["id"],))
    for r in proposed:
        db.execute("""UPDATE calendar_occurrences SET series_id=?,sequence=?,starts_at=?,ends_at=?,entry_cycle_date=?,entry_session_key=?,
                    confidence=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                   (new_sid,r["sequence"],r["starts_at"],r["ends_at"],r["entry_cycle_date"],r["entry_session_key"],
                    schedule.confidence if r["id"]==selected["id"] else "estimated",r["id"]))
        audit(db,"rescheduled",r["id"])
    if rolling:
        template=CalendarInput(**{k:getattr(schedule,k) for k in CalendarInput.model_fields}).model_dump_json()
        if changing:
            db.execute("INSERT INTO calendar_rolling_series(series_id,template_json,next_start,next_sequence,status) VALUES (?,?,?,?,?)",
                       (new_sid,template,next_start,next_sequence,rolling["status"]))
        else:
            db.execute("UPDATE calendar_rolling_series SET template_json=?,next_start=? WHERE series_id=?",(template,next_start,sid))
    return {"items":[dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?",(r["id"],)).fetchone()) for r in proposed]}


def change_future(path, group_id, occurrence_id, payload: CalendarFutureChange):
    with transaction(path) as db:
        require_group(db, group_id, True)
        rows = future_rows(db, group_id, occurrence_id)
        if not rows or {row["id"]: row["revision"] for row in rows} != payload.revisions:
            raise ValueError("Series changed; review affected occurrences again")
        now = datetime.now(timezone.utc)
        if any(db.execute("SELECT 1 FROM calendar_event_links WHERE occurrence_id=?",(row["id"],)).fetchone() for row in rows):
            raise ValueError("Unlink actual events before changing this series")
        if payload.action=="edit":
            return edit_future_series(db,group_id,rows,payload,now)
        auto_bear=bear_series_rule(db,rows[0]["series_id"])
        if auto_bear and payload.action=="shift":
            raise ValueError("Cancel and replace an automatically grouped Bear series to change its cycle anchor or cadence")
        if any(row["entry_cycle_date"] for row in rows):
            if not auto_bear or payload.action!="cancel":
                raise ValueError("Clear session grouping before changing this series")
            for row in rows:
                require_open_cycle_for_grouping(db,group_id,row["event_type"],row["entry_cycle_date"],row["alliance_id"])
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
        rolling = db.execute("SELECT * FROM calendar_rolling_series WHERE series_id=?",(rows[0]["series_id"],)).fetchone()
        if rolling:
            if payload.action == "cancel":
                db.execute("UPDATE calendar_rolling_series SET status='stopped' WHERE series_id=?",(rolling["series_id"],))
            elif rolling["status"] == "active":
                next_start = shift(rolling["next_start"],payload.shift_minutes)
                if parse(next_start) < now or not 2000 <= parse(next_start).year <= 2099:
                    raise ValueError("Shift would move the next renewal outside future supported dates")
                db.execute("UPDATE calendar_rolling_series SET next_start=? WHERE series_id=?",(next_start,rolling["series_id"]))
        return {"items": [dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (row["id"],)).fetchone()) for row in rows]}

class CalendarCycleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["canyon", "foundry", "svs"]
    request_key: str = Field(min_length=16,max_length=128,pattern=r"^[A-Za-z0-9_-]+$")
    phases: list[CalendarInput] = Field(min_length=2,max_length=5)
    occurrence_count: int = Field(default=1,ge=1,le=14)
    interval_days: int | None = Field(default=None,ge=1,le=366)
    rolling: bool = False

    @model_validator(mode="after")
    def validate_phases(self):
        actual=[(p.event_type,p.phase) for p in self.phases]
        if self.kind=="svs":
            # Preserve the shape of already persisted two-phase renewal templates.
            valid=[[("svs_matchmaking","Matchmaking"),("svs_preparation","Preparation"),("svs_battle","Battle"),("svs_triage","Field Triage")],
                   [("svs_preparation","Preparation"),("svs_battle","Battle")]]
        else:
            prep=[(self.kind,p) for p in ("Voting","Registration","Matchmaking")]
            valid=[prep+[(self.kind,"Battle")],prep+[(self.kind,"Legion 1")],prep+[(self.kind,"Legion 1"),(self.kind,"Legion 2")]]
        if actual not in valid:
            raise ValueError("Invalid cycle phases or order")
        first = self.phases[0]
        if self.kind=="svs" and first.scope!="state":
            raise ValueError("SvS cycle requires state scope")
        if self.kind!="svs" and first.scope!="alliance":
            raise ValueError("Battle cycle requires alliance scope")
        for i,p in enumerate(self.phases):
            if (p.scope,p.alliance_id,p.state_id)!=(first.scope,first.alliance_id,first.state_id):
                raise ValueError("All phases must have the same owner")
            parallel=i>0 and p.phase=="Legion 2" and self.phases[i-1].phase=="Legion 1"
            if parallel:
                prior=self.phases[i-1]
                if p.starts_at[:10]!=prior.starts_at[:10] or (p.precision==prior.precision=="minute" and p.starts_at==prior.starts_at):
                    raise ValueError("Legions require a shared battle date and distinct known times")
                if self.phases[2].ends_at and parse(p.starts_at)<parse(self.phases[2].ends_at):
                    raise ValueError("Battle must follow matchmaking")
            if i and not parallel and parse(p.starts_at)<=parse(self.phases[i-1].starts_at):
                raise ValueError("Phases must be chronological")
            if i and not parallel and self.phases[i-1].ends_at and parse(p.starts_at)<parse(self.phases[i-1].ends_at):
                raise ValueError("Cycle phases must not overlap")
            if parse(p.ends_at or p.starts_at)-parse(first.starts_at)>timedelta(days=31):
                raise ValueError("Maximum cycle duration is 31 days")
        if self.rolling and (self.interval_days is None or self.interval_days<7 or self.interval_days>60 or self.occurrence_count!=1+60//self.interval_days):
            raise ValueError("Automatic renewal requires a 7–60 day cadence and the initial 60-day preview")
        if (self.occurrence_count>1)!=(self.interval_days is not None):
            raise ValueError("Provide a repeat interval for multiple cycles")
        if self.interval_days is not None:
            if (self.occurrence_count-1)*self.interval_days>366:
                raise ValueError("Maximum recurrence horizon is 366 days")
            if max(parse(p.ends_at or p.starts_at) for p in self.phases)>=parse(first.starts_at)+timedelta(days=self.interval_days):
                raise ValueError("Repeat interval must exceed the cycle duration")
            if max(parse(p.ends_at or p.starts_at) for p in self.phases)+timedelta(days=(self.occurrence_count-1)*self.interval_days)>=datetime(2100,1,1,tzinfo=timezone.utc):
                raise ValueError("Date outside supported range")
        return self


def project_cycle(kind, phases, days):
    result=[]
    for p in phases:
        values=p.model_dump()
        values.update(starts_at=shift(p.starts_at,days*1440),ends_at=shift(p.ends_at,days*1440),confidence="estimated")
        if kind!="svs" and p.phase in {"Battle","Legion 1","Legion 2"}:
            values.update(starts_at=values["starts_at"][:10],ends_at=None,precision="date")
        result.append(CalendarInput.model_validate(values))
    CalendarCycleCreate(kind=kind,request_key="projected-cycle-template",phases=result)
    return result


def cycle_occurrences(payload:CalendarCycleCreate):
    return [payload.phases]+[project_cycle(payload.kind,payload.phases,i*(payload.interval_days or 0)) for i in range(1,payload.occurrence_count)]


def cycle_owner(phase):
    return "a:"+phase.alliance_id if phase.scope=="alliance" else "s:"+phase.state_id


def cycle_span(rows):
    def end(r):
        start=parse(r["starts_at"])
        return parse(r["ends_at"]) if r["ends_at"] else start+timedelta(days=1 if r["precision"]=="date" else 0,minutes=0 if r["precision"]=="date" else 1)
    return min(parse(r["starts_at"]) for r in rows),max(end(r) for r in rows)


def validate_cycle_overlap(db,group_id,rows,ignore_ids=()):
    first,last=cycle_span(rows)
    p=rows[0]
    types=tuple(sorted({r["event_type"] for r in rows}))
    marks=",".join("?" for _ in types)
    candidates=db.execute(f"""SELECT * FROM calendar_occurrences
        WHERE group_id=? AND event_type IN ({marks}) AND scope=? AND alliance_id IS ? AND state_id=?
        AND starts_at<? AND (starts_at>=? OR ends_at>?)""",
        (group_id,*types,p["scope"],p["alliance_id"],p["state_id"],(last.date()+timedelta(days=1)).isoformat(),first.date().isoformat(),first.date().isoformat())).fetchall()
    for other in candidates:
        if other["id"] in ignore_ids:
            continue
        lo,hi=cycle_span([other])
        if lo<last and hi>first:
            raise ValueError("Cycle overlaps an existing schedule; review the calendar")


def validate_cycle_insert(db,group_id,phases):
    validate_cycle_overlap(db,group_id,[p.model_dump() for p in phases])
    for p in phases:
        validate_scope(db,group_id,p)
        if p.phase in {"Legion 1","Legion 2"}:
            if db.execute("""SELECT 1 FROM calendar_occurrences WHERE group_id=? AND alliance_id=? AND event_type=?
                AND substr(starts_at,1,10)=? AND (lower(phase) IN ('battle','') OR replace(lower(phase),'_',' ')=?)""",
                (group_id,p.alliance_id,p.event_type,p.starts_at[:10],p.phase.lower())).fetchone():
                raise ValueError("A matching battle or legion schedule already exists; review the calendar")
            require_open_cycle_for_grouping(db,group_id,p.event_type,p.starts_at[:10],p.alliance_id)
            if db.execute("""SELECT 1 FROM calendar_occurrences WHERE group_id=? AND alliance_id=? AND event_type=? AND entry_cycle_date=? AND entry_session_key=?""",(group_id,p.alliance_id,p.event_type,p.starts_at[:10],"legion_"+p.phase[-1])).fetchone():
                raise ValueError("Legion already assigned in this cycle")
        # Blank legacy phase may represent the same event. Never silently duplicate it.
        existing=db.execute("""SELECT starts_at,precision FROM calendar_occurrences
            WHERE group_id=? AND event_type=? AND scope=? AND alliance_id IS ? AND state_id=?
            AND (phase=? OR phase='') AND starts_at>=? AND starts_at<?""",
            (group_id,p.event_type,p.scope,p.alliance_id,p.state_id,p.phase,p.starts_at[:10],
             (parse(p.starts_at).date()+timedelta(days=1)).isoformat())).fetchall()
        if any(r["starts_at"]==p.starts_at or r["precision"]=="date" or p.precision=="date" for r in existing):
            raise ValueError("A matching scheduled or cancelled phase already exists; review the calendar")

def insert_cycle(db,group_id,kind,phases,series_id=None,sequence=0,forecast=False,system=False):
    cycle_id=uuid.uuid4().hex
    db.execute("INSERT INTO calendar_cycles(id,group_id,kind) VALUES (?,?,?)",(cycle_id,group_id,kind))
    if series_id:
        db.execute("INSERT INTO calendar_cycle_series_members(cycle_id,series_id,sequence) VALUES (?,?,?)",(cycle_id,series_id,sequence))
    items=[]
    for p in phases:
        oid=uuid.uuid4().hex
        db.execute("""INSERT INTO calendar_occurrences(id,group_id,cycle_id,event_type,scope,alliance_id,state_id,starts_at,ends_at,precision,phase,confidence,source)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (oid,group_id,cycle_id,p.event_type,p.scope,p.alliance_id,p.state_id,p.starts_at,p.ends_at,p.precision,p.phase,p.confidence,"recurrence" if forecast else "manual"))
        if p.phase in {"Legion 1","Legion 2"}:
            db.execute("UPDATE calendar_occurrences SET entry_cycle_date=?,entry_session_key=? WHERE id=?",(p.starts_at[:10],"legion_"+p.phase[-1],oid))
        if system:
            db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES ('created','calendar_occurrence',?,'system')",(oid,))
        else:
            audit(db,"created",oid)
        items.append(dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?",(oid,)).fetchone()))
    return items


def create_cycle(path,group_id,payload:CalendarCycleCreate):
    excluded={"request_key"}
    if not payload.rolling:
        excluded.add("rolling")
    if payload.occurrence_count==1:
        excluded.update(("occurrence_count","interval_days"))
    fingerprint=hashlib.sha256(json.dumps({"cycle":payload.model_dump(mode="json",exclude=excluded)},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    cycles=cycle_occurrences(payload)
    with transaction(path) as db:
        require_group(db,group_id,True)
        previous=db.execute("SELECT payload_hash,occurrence_ids FROM calendar_create_requests WHERE group_id=? AND request_key=?",(group_id,payload.request_key)).fetchone()
        if previous:
            if previous["payload_hash"]!=fingerprint:
                raise ValueError("Request key already used for a different schedule")
            return {"items":[dict(db.execute("SELECT * FROM calendar_occurrences WHERE group_id=? AND id=?",(group_id,oid)).fetchone()) for oid in json.loads(previous["occurrence_ids"])]}
        for phases in cycles:
            validate_cycle_insert(db,group_id,phases)
        series_id=None
        if payload.occurrence_count>1:
            owner=cycle_owner(payload.phases[0])
            if payload.rolling and db.execute("SELECT 1 FROM calendar_cycle_series WHERE group_id=? AND kind=? AND owner_key=? AND status IN ('active','conflict')",(group_id,payload.kind,owner)).fetchone():
                raise ValueError("An automatic cycle schedule already exists for this owner; review or stop it first")
            series_id=uuid.uuid4().hex
            db.execute("""INSERT INTO calendar_cycle_series(id,group_id,kind,owner_key,interval_days,template_json,next_sequence,status)
                VALUES (?,?,?,?,?,?,?,?)""",(series_id,group_id,payload.kind,owner,payload.interval_days,
                json.dumps([p.model_dump(mode="json") for p in payload.phases]),len(cycles),"active" if payload.rolling else "finite"))
        items=[]
        for i,phases in enumerate(cycles):
            items.extend(insert_cycle(db,group_id,payload.kind,phases,series_id,i,forecast=i>0))
        db.execute("INSERT INTO calendar_create_requests(group_id,request_key,payload_hash,occurrence_ids) VALUES (?,?,?,?)",(group_id,payload.request_key,fingerprint,json.dumps([r["id"] for r in items])))
        return {"items":items}


def cycle_series(db,group_id,cycle_id):
    return db.execute("""SELECT s.*,m.sequence FROM calendar_cycle_series s JOIN calendar_cycle_series_members m ON m.series_id=s.id
        WHERE s.group_id=? AND m.cycle_id=?""",(group_id,cycle_id)).fetchone()


def cycle_rows(db,group_id,cycle_id):
    if not db.execute("SELECT 1 FROM calendar_cycles WHERE id=? AND group_id=?",(cycle_id,group_id)).fetchone():
        raise LookupError("Calendar cycle not found")
    return [dict(r) for r in db.execute("SELECT * FROM calendar_occurrences WHERE group_id=? AND cycle_id=? ORDER BY starts_at,id",(group_id,cycle_id))]


def get_cycle(path,group_id,cycle_id):
    with connection(path) as db:
        require_group(db,group_id)
        rows=cycle_rows(db,group_id,cycle_id)
        kind=db.execute("SELECT kind FROM calendar_cycles WHERE id=?",(cycle_id,)).fetchone()[0]
        series=cycle_series(db,group_id,cycle_id)
        return {"kind":kind,"items":rows,"series":{k:series[k] for k in ("id","interval_days","status","revision","sequence")} if series else None}


class CycleReconcile(BaseModel):
    model_config=ConfigDict(extra="forbid")
    action: Literal["confirm","shift","stop","cadence"]
    following: bool=False
    shift_days: int=Field(default=0,ge=-366,le=366)
    interval_days: int|None=Field(default=None,ge=7,le=60)
    revisions: dict[str,int]=Field(default_factory=dict,max_length=500)
    series_revision: int|None=Field(default=None,ge=1)

    @model_validator(mode="after")
    def valid_action(self):
        if (self.action=="shift")!=bool(self.shift_days):
            raise ValueError("Only a shift requires a nonzero number of days")
        if (self.action=="cadence")!=(self.interval_days is not None):
            raise ValueError("Only cadence changes require a repeat interval")
        if self.action=="cadence" and not self.following:
            raise ValueError("Cadence changes affect following cycles")
        if self.following and self.action not in {"shift","cadence"}:
            raise ValueError("Only shifts and cadence changes may affect following cycles")
        return self


def cycle_has_results(db,rows):
    for row in rows:
        if db.execute("SELECT 1 FROM calendar_event_links WHERE occurrence_id=?",(row["id"],)).fetchone():
            return True
        if row["event_type"] in {"foundry","canyon"} and row["phase"] in {"Battle","Legion 1","Legion 2"}:
            if db.execute("SELECT 1 FROM events WHERE alliance_id=? AND event_type=? AND occurred_on=?",
                (row["alliance_id"],row["event_type"],row["entry_cycle_date"] or row["starts_at"][:10])).fetchone():
                return True
    return False


def cycle_has_external_grouping(db,rows):
    for r in rows:
        if r["entry_cycle_date"] and db.execute("""SELECT 1 FROM calendar_occurrences
            WHERE group_id=? AND event_type=? AND alliance_id=? AND entry_cycle_date=? AND cycle_id IS NOT ?""",
            (r["group_id"],r["event_type"],r["alliance_id"],r["entry_cycle_date"],r["cycle_id"])).fetchone():
            return True
    return False


def movable_cycle(db,rows,now):
    return bool(rows and all(r["confidence"]=="estimated" and (r["revision"]==1 or r["source"]=="recurrence")
        and r["schedule_status"]=="scheduled" and parse(r["starts_at"])>now for r in rows)
        and not cycle_has_results(db,rows) and not cycle_has_external_grouping(db,rows))


def cycle_reconcile_plan(db,group_id,cycle_id,following,now):
    require_group(db,group_id)
    rows=cycle_rows(db,group_id,cycle_id)
    series=cycle_series(db,group_id,cycle_id)
    if following and not series:
        raise ValueError("This legacy cycle has no recurring series")
    eligible=[]
    protected=0
    if movable_cycle(db,rows,now):
        eligible.append(rows)
        if following:
            members=db.execute("""SELECT m.cycle_id FROM calendar_cycle_series_members m
                WHERE m.series_id=? AND m.sequence>? ORDER BY m.sequence LIMIT 101""",(series["id"],series["sequence"])).fetchall()
            if len(members)>100:
                raise ValueError("Too many cycles for one review; choose a later forecast")
            for member in members:
                group=cycle_rows(db,group_id,member["cycle_id"])
                if movable_cycle(db,group,now):
                    eligible.append(group)
                else:
                    protected+=1
    else:
        protected=1
    can_confirm=bool(rows and all(r["schedule_status"]=="scheduled" for r in rows) and not cycle_has_results(db,rows)
        and cycle_span(rows)[1]>now and any(r["confidence"]=="estimated" for r in rows))
    return {"items":[r for group in eligible for r in group],
        "protected_cycles":protected,"can_confirm":can_confirm,"confirm_items":[r for r in rows if r["confidence"]=="estimated"],
        "series_revision":series["revision"] if series else None,"series_status":series["status"] if series else None}


def preview_cycle_reconcile(path,group_id,cycle_id,following=False,interval_days=None):
    with connection(path) as db:
        now=datetime.now(timezone.utc)
        if interval_days is not None:
            return cadence_plan(db,group_id,cycle_id,interval_days,now)[0]
        return cycle_reconcile_plan(db,group_id,cycle_id,following,now)


def validate_shifted_cycles(db,group_id,proposed,ids,now):
    by_cycle={}
    for row in proposed:
        by_cycle.setdefault(row["cycle_id"],[]).append(row)
    ranges=[]
    for cid,rows in by_cycle.items():
        first,last=cycle_span(rows)
        if first<=now:
            raise ValueError("Cannot move a forecast into the past")
        for r in rows:
            CalendarInput.model_validate({k:r[k] for k in CalendarInput.model_fields})
            if r["phase"] in {"Battle","Legion 1","Legion 2"} and r["event_type"] in {"canyon","foundry"}:
                if db.execute("SELECT 1 FROM events WHERE alliance_id=? AND event_type=? AND occurred_on=?",
                    (r["alliance_id"],r["event_type"],r["entry_cycle_date"] or r["starts_at"][:10])).fetchone():
                    raise ValueError("A result record already exists on the target battle date")
            if r["entry_session_key"]:
                for existing in db.execute("""SELECT id FROM calendar_occurrences WHERE group_id=? AND alliance_id=? AND event_type=? AND entry_cycle_date=? AND entry_session_key=?""",
                    (group_id,r["alliance_id"],r["event_type"],r["entry_cycle_date"],r["entry_session_key"])):
                    if existing["id"] not in ids:
                        raise ValueError("Target date already has this legion identity")
        validate_cycle_overlap(db,group_id,rows,ids)
        if any(lo<last and hi>first for lo,hi in ranges):
            raise ValueError("Proposed cycles overlap")
        ranges.append((first,last))


def cadence_plan(db,group_id,cycle_id,interval_days,now):
    require_group(db,group_id)
    series=cycle_series(db,group_id,cycle_id)
    if not series or series["status"] not in {"active","finite","conflict"}:
        raise ValueError("Choose an existing active or finite cycle series")
    if not 7<=interval_days<=60 or interval_days==series["interval_days"]:
        raise ValueError("Choose a different repeat interval between 7 and 60 days")
    anchor_rows=cycle_rows(db,group_id,cycle_id)
    anchor,end=cycle_span(anchor_rows)
    if end<=now or any(r["schedule_status"]!="scheduled" for r in anchor_rows):
        raise ValueError("Choose a current or future scheduled cycle as the anchor")
    for r in anchor_rows:
        validate_scope(db,group_id,CalendarInput.model_validate({k:r[k] for k in CalendarInput.model_fields}))
    if end-anchor>timedelta(days=interval_days):
        raise ValueError("Repeat interval cannot be shorter than the selected cycle")
    template=[CalendarInput.model_validate(p) for p in json.loads(series["template_json"])]
    template_start=parse(template[0].starts_at)
    delta=anchor-template_start
    if delta.seconds or delta.microseconds:
        raise ValueError("The anchor start time differs from the series template; review its dates first")
    # Keep sequence IDs stable and align the new recurrence with the selected cycle.
    moved=project_cycle(series["kind"],template,delta.days-series["sequence"]*interval_days)
    projected_anchor=project_cycle(series["kind"],moved,series["sequence"]*interval_days)
    projected_span=cycle_span([p.model_dump() for p in projected_anchor])
    if projected_span[1]-projected_span[0]>timedelta(days=interval_days):
        raise ValueError("Repeat interval cannot be shorter than the template cycle")
    members=db.execute("""SELECT cycle_id,sequence FROM calendar_cycle_series_members
        WHERE series_id=? AND sequence>? ORDER BY sequence LIMIT 101""",(series["id"],series["sequence"])).fetchall()
    if len(members)>100:
        raise ValueError("Too many cycles for one review; choose a later forecast")
    rows=[]; proposed=[]; protected=0
    for member in members:
        group=cycle_rows(db,group_id,member["cycle_id"])
        if not movable_cycle(db,group,now):
            protected+=1
            continue
        target=anchor+timedelta(days=(member["sequence"]-series["sequence"])*interval_days)
        offset=target-cycle_span(group)[0]
        if offset.seconds or offset.microseconds:
            raise ValueError("A forecast start time differs from the series template")
        rows.extend(group)
        proposed.extend({**r,"starts_at":shift(r["starts_at"],offset.days*1440),"ends_at":shift(r["ends_at"],offset.days*1440),
            "entry_cycle_date":shift(r["entry_cycle_date"],offset.days*1440)} for r in group)
    if not rows and series["status"]=="finite":
        raise ValueError("No following forecasts to reschedule")
    validate_shifted_cycles(db,group_id,proposed,{r["id"] for r in rows},now)
    next_start=None
    if series["status"] in {"active","conflict"}:
        next_cycle=project_cycle(series["kind"],moved,series["next_sequence"]*interval_days)
        next_start=next_cycle[0].starts_at
        if parse(next_start)<=now:
            raise ValueError("New renewal anchor would be in the past")
        next_rows=[p.model_dump() for p in next_cycle]
        validate_cycle_overlap(db,group_id,next_rows,{r["id"] for r in rows})
        lo,hi=cycle_span(next_rows)
        by_cycle={}
        for r in proposed:
            by_cycle.setdefault(r["cycle_id"],[]).append(r)
        if any(a<hi and b>lo for a,b in (cycle_span(rr) for rr in by_cycle.values())):
            raise ValueError("Next automatic cycle overlaps a proposed forecast")
    return {"items":rows,"proposed":proposed,"anchor_items":anchor_rows,"protected_cycles":protected,
        "interval_days":interval_days,"series_revision":series["revision"],"next_start":next_start},moved


def write_cycle_moves(db,proposed,following):
    # Avoid transient legion uniqueness conflicts when several cycles exchange dates.
    for r in proposed:
        if r["entry_session_key"]:
            db.execute("UPDATE calendar_occurrences SET entry_cycle_date=NULL,entry_session_key=NULL WHERE id=?",(r["id"],))
    for r in proposed:
        db.execute("""UPDATE calendar_occurrences SET starts_at=?,ends_at=?,entry_cycle_date=?,entry_session_key=?,source=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (r["starts_at"],r["ends_at"],r["entry_cycle_date"],r["entry_session_key"],"recurrence" if following else "manual",r["id"]))
        audit(db,"rescheduled",r["id"])


def reconcile_cycle(path,group_id,cycle_id,payload):
    now=datetime.now(timezone.utc)
    with transaction(path) as db:
        require_group(db,group_id,True)
        if payload.action=="cadence":
            plan,moved=cadence_plan(db,group_id,cycle_id,payload.interval_days,now)
            rows=plan["anchor_items"]+plan["items"]
            if plan["series_revision"]!=payload.series_revision or {r["id"]:r["revision"] for r in rows}!=payload.revisions:
                raise ValueError("Cycle or series changed; refresh the interval preview")
            series=cycle_series(db,group_id,cycle_id)
            write_cycle_moves(db,plan["proposed"],True)
            db.execute("UPDATE calendar_cycle_series SET interval_days=?,template_json=?,revision=revision+1 WHERE id=?",
                (payload.interval_days,json.dumps([p.model_dump(mode="json") for p in moved]),series["id"]))
            for r in plan["anchor_items"]:
                audit(db,"cycle_cadence_changed",r["id"])
            return {"items":[dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?",(r["id"],)).fetchone()) for r in rows]}
        plan=cycle_reconcile_plan(db,group_id,cycle_id,payload.following,now)
        series=cycle_series(db,group_id,cycle_id)
        if plan["series_revision"]!=payload.series_revision:
            raise ValueError("Schedule series changed; refresh the preview")
        if payload.action=="stop":
            if not series or series["status"] not in {"active","conflict"}:
                raise ValueError("No automatic renewal to stop")
            db.execute("UPDATE calendar_cycle_series SET status='stopped',revision=revision+1 WHERE id=?",(series["id"],))
            for r in cycle_rows(db,group_id,cycle_id):
                audit(db,"cycle_renewal_stopped",r["id"])
            return {"items":cycle_rows(db,group_id,cycle_id)}
        rows=plan["confirm_items"] if payload.action=="confirm" and plan["can_confirm"] else plan["items"] if payload.action=="shift" else []
        if not rows or {r["id"]:r["revision"] for r in rows}!=payload.revisions:
            raise ValueError("Cycle is protected or changed; refresh the preview")
        if payload.action=="confirm":
            for r in rows:
                db.execute("UPDATE calendar_occurrences SET confidence='confirmed',source='manual',revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",(r["id"],))
                audit(db,"confirmed",r["id"])
        else:
            proposed=[{**r,"starts_at":shift(r["starts_at"],payload.shift_days*1440),"ends_at":shift(r["ends_at"],payload.shift_days*1440),
                "entry_cycle_date":shift(r["entry_cycle_date"],payload.shift_days*1440)} for r in rows]
            ids={r["id"] for r in rows}
            validate_shifted_cycles(db,group_id,proposed,ids,now)
            if payload.following and series and series["status"] in {"active","conflict"}:
                template=[CalendarInput.model_validate(p) for p in json.loads(series["template_json"])]
                moved=project_cycle(series["kind"],template,payload.shift_days)
                # Refuse a new renewal cursor that is outside supported dates or already past.
                next_cycle=project_cycle(series["kind"],moved,series["next_sequence"]*series["interval_days"])
                if parse(next_cycle[0].starts_at)<=now:
                    raise ValueError("New renewal anchor would be in the past")
                db.execute("UPDATE calendar_cycle_series SET template_json=?,revision=revision+1 WHERE id=?",(json.dumps([p.model_dump(mode="json") for p in moved]),series["id"]))
            write_cycle_moves(db,proposed,payload.following)
        return {"items":[dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?",(r["id"],)).fetchone()) for r in rows]}


def renew_cycle_series(path,series_id,now):
    with transaction(path) as db:
        series=db.execute("""SELECT s.* FROM calendar_cycle_series s JOIN alliance_groups g ON g.id=s.group_id
            WHERE s.id=? AND s.status='active' AND g.status='active'""",(series_id,)).fetchone()
        if not series:
            return 0
        template=[CalendarInput.model_validate(p) for p in json.loads(series["template_json"])]
        interval=series["interval_days"]
        anchor=parse(template[0].starts_at)
        threshold=future_threshold(template[0].precision,now)
        # Never backfill missed cycles after downtime.
        seq=max(series["next_sequence"],max(0,(threshold-anchor)//timedelta(days=interval)))
        if anchor+timedelta(days=seq*interval)<threshold:
            seq+=1
        horizon=now+timedelta(days=ROLLING_HORIZON_DAYS)
        count=0
        status="active"
        while anchor+timedelta(days=seq*interval)<=horizon:
            if (anchor+timedelta(days=seq*interval)).year>2099:
                status="stopped"
                break
            try:
                phases=project_cycle(series["kind"],template,seq*interval)
                validate_cycle_insert(db,series["group_id"],phases)
            except (ValueError,LookupError):
                status="conflict"
                break
            insert_cycle(db,series["group_id"],series["kind"],phases,series_id,seq,forecast=True,system=True)
            count+=len(phases)
            seq+=1
        if seq!=series["next_sequence"] or status!=series["status"]:
            db.execute("UPDATE calendar_cycle_series SET next_sequence=?,status=?,revision=revision+1 WHERE id=?",(seq,status,series_id))
        return count


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
            and not (row["event_type"] in {"canyon","foundry"} and row["cycle_id"] and row["phase"] not in {"Battle","Legion 1","Legion 2"}))


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
        start_entry_locked(db,group_id,occurrence_id,payload)
    return event_link(path,group_id,occurrence_id)


def start_entry_locked(db,group_id,occurrence_id,payload):
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


class OccurrenceWorkspaceStart(BaseModel):
    model_config=ConfigDict(extra="forbid")
    member_id: str
    revision: int=Field(ge=1)
    confirmed: Literal[True]


def occurrence_workspace_state(db,group_id,occurrence_id):
    row=link_occurrence(db,group_id,occurrence_id)
    kind=row["event_type"]
    if row["scope"]!="alliance" or kind not in {"bear_trap","alliance_mobilization","alliance_championship"}:
        raise ValueError("This schedule has no shared data workspace")
    if kind=="bear_trap":
        day=row["entry_cycle_date"]
        if not day:
            raise ValueError("This advanced single trap needs a reviewed cycle identity")
        primary=db.execute("SELECT id FROM alliances WHERE group_id=? AND alliance_type='primary' AND status='active'",(group_id,)).fetchone()
        if not primary:
            raise ValueError("An active primary alliance is required")
        owner=primary["id"]
        members=db.execute("""SELECT c.*,a.tag FROM calendar_occurrences c JOIN alliances a ON a.id=c.alliance_id
            WHERE c.group_id=? AND c.event_type='bear_trap' AND c.entry_cycle_date=? ORDER BY c.starts_at,c.id""",(group_id,day)).fetchall()
        candidates=db.execute("""SELECT e.id,e.status,e.alliance_id FROM events e JOIN alliances a ON a.id=e.alliance_id
            WHERE a.group_id=? AND e.event_type='bear_trap' AND e.occurred_on=?""",(group_id,day)).fetchall()
        if any(e["alliance_id"]!=owner for e in candidates):
            raise ValueError("Existing Bear cycle owner requires review")
    else:
        day=row["starts_at"][:10]
        owner=row["alliance_id"]
        members=[db.execute("SELECT c.*,a.tag FROM calendar_occurrences c JOIN alliances a ON a.id=c.alliance_id WHERE c.id=?",(occurrence_id,)).fetchone()]
        candidates=db.execute("SELECT id,status,alliance_id FROM events WHERE alliance_id=? AND event_type=? AND occurred_on=?",(owner,kind,day)).fetchall()
    if len(candidates)>1:
        raise ValueError("Multiple matching events; review Event History before entering data")
    event=candidates[0] if candidates else None
    sessions={}
    if event:
        sessions={s["session_key"]:s for s in db.execute("SELECT * FROM event_sessions WHERE event_id=?",(event["id"],))}
    slots=[]
    for member in members:
        key=member["entry_session_key"] if kind=="bear_trap" else "main"
        session=sessions.get(key)
        link=db.execute("SELECT event_id,session_id FROM calendar_event_links WHERE occurrence_id=?",(member["id"],)).fetchone()
        if link and (not event or link["event_id"]!=event["id"] or link["session_id"] and (not session or link["session_id"]!=session["id"])):
            raise ValueError("Existing calendar link requires review")
        if session and (session["host_alliance_id"]!=member["alliance_id"] or kind=="bear_trap" and session["started_at"][:16]!=member["starts_at"][:16]):
            raise ValueError("Existing session differs from the planned trap; review its time or host")
        slots.append({"key":key,"id":member["id"],"tag":member["tag"],"starts_at":member["starts_at"],
            "precision":member["precision"],"revision":member["revision"],"confidence":member["confidence"],
            "cancelled":member["schedule_status"]=="cancelled","linked":bool(link and (link["session_id"] or kind!="bear_trap" and session)),
            "session_id":session["id"] if session else None})
    return {"kind":kind,"cycle_date":day,"event_id":event["id"] if event and sessions else None,
        "event_status":event["status"] if event else None,"slots":slots}


def get_occurrence_workspace(path,group_id,occurrence_id):
    with connection(path) as db:
        return occurrence_workspace_state(db,group_id,occurrence_id)


def start_occurrence_workspace(path,group_id,occurrence_id,payload):
    with transaction(path) as db:
        require_group(db,group_id,True)
        state=occurrence_workspace_state(db,group_id,occurrence_id)
        slot=next((s for s in state["slots"] if s["id"]==payload.member_id),None)
        if not slot:
            raise ValueError("Choose a session from this event")
        if slot["linked"]:
            return state
        if slot["revision"]!=payload.revision:
            raise ValueError("Schedule changed; reopen the event card")
        if slot["cancelled"]:
            raise ValueError("This schedule is cancelled")
        row=link_occurrence(db,group_id,slot["id"])
        if state["kind"]=="bear_trap" and row["precision"]!="minute":
            raise ValueError("Set the actual trap time in schedule settings")
        if row["confidence"]!="confirmed":
            fields={k:row[k] for k in CalendarInput.model_fields}
            fields["confidence"]="confirmed"
            row=update_locked(db,group_id,row["id"],CalendarUpdate(**fields,revision=row["revision"],schedule_status="scheduled"))
        start_entry_locked(db,group_id,row["id"],CalendarEntryStart(revision=row["revision"],confirmed=True))
        if state["kind"]!="bear_trap":
            # A pre-existing empty draft (e.g. entered through Event History) still needs its main session.
            event=db.execute("""SELECT e.id,e.status FROM events e JOIN calendar_event_links l ON l.event_id=e.id
                WHERE l.occurrence_id=?""",(row["id"],)).fetchone()
            if event["status"]=="draft" and not db.execute("SELECT 1 FROM event_sessions WHERE event_id=?",(event["id"],)).fetchone():
                db.execute("INSERT INTO event_sessions(id,event_id,session_key,started_at,host_alliance_id) VALUES (?,?,?,?,?)",
                    (uuid.uuid4().hex,event["id"],"main",state["cycle_date"]+"T00:00:00+00:00",row["alliance_id"]))
                db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES ('session_created','event',?,'admin')",(event["id"],))
        return occurrence_workspace_state(db,group_id,occurrence_id)


class CycleWorkspaceStart(BaseModel):
    model_config=ConfigDict(extra="forbid")
    legion: Literal["legion_1","legion_2"]
    starts_at: str
    revisions: dict[str,int]=Field(min_length=1,max_length=5)


def cycle_workspace_state(db,group_id,cycle_id):
    require_group(db,group_id)
    rows=cycle_rows(db,group_id,cycle_id)
    kind=db.execute("SELECT kind FROM calendar_cycles WHERE id=? AND group_id=?",(cycle_id,group_id)).fetchone()[0]
    if kind not in {"foundry","canyon"}:
        raise ValueError("This cycle has no legion workspace")
    battles=[r for r in rows if r["phase"] in {"Legion 1","Legion 2"}]
    if not battles:
        raise ValueError("No legion is scheduled in this cycle")
    first=battles[0]
    day=first["entry_cycle_date"] or first["starts_at"][:10]
    owner=first["alliance_id"]
    if any((r["event_type"],r["alliance_id"],r["state_id"],r["scope"])!=(kind,owner,first["state_id"],"alliance") for r in rows) or any((r["entry_cycle_date"] or r["starts_at"][:10])!=day for r in battles):
        raise ValueError("Cycle has inconsistent owner or battle dates")
    events=db.execute("""SELECT e.id,e.status FROM events e JOIN alliances a ON a.id=e.alliance_id
        WHERE a.group_id=? AND e.alliance_id=? AND e.event_type=? AND e.occurred_on=?""",(group_id,owner,kind,day)).fetchall()
    if len(events)>1:
        raise ValueError("Multiple matching event records; review Event History before entering data")
    event=events[0] if events else None
    sessions={}
    if event:
        for s in db.execute("SELECT * FROM event_sessions WHERE event_id=?",(event["id"],)):
            if s["session_key"] not in {"legion_1","legion_2"} or s["host_alliance_id"]!=owner or s["started_at"][:10]!=day:
                raise ValueError("Existing session identity or date requires review")
            sessions[s["session_key"]]=dict(s)
    slots=[]
    for n in (1,2):
        key="legion_"+str(n)
        row=next((r for r in battles if r["phase"]=="Legion "+str(n)),None)
        session=sessions.get(key)
        link=db.execute("SELECT event_id,session_id FROM calendar_event_links WHERE occurrence_id=?",(row["id"],)).fetchone() if row else None
        if link and (not event or link["event_id"]!=event["id"] or link["session_id"] and (not session or session["id"]!=link["session_id"])):
            raise ValueError("Existing calendar link requires review")
        if session and db.execute("SELECT 1 FROM calendar_event_links WHERE session_id=? AND occurrence_id<>?",(session["id"],row["id"] if row else "")).fetchone():
            raise ValueError("Legion already linked to a different schedule")
        known=session["started_at"][:16]+"Z" if session else row["starts_at"] if row and row["precision"]=="minute" else None
        slots.append({"key":key,"occurrence_id":row["id"] if row else None,"starts_at":known,
            "linked":bool(link and link["session_id"]),"cancelled":bool(row and row["schedule_status"]=="cancelled"),
            "session_id":session["id"] if session else None})
    return {"kind":kind,"battle_date":day,"event_id":event["id"] if event and sessions else None,
        "event_status":event["status"] if event else None,"slots":slots,"revisions":{r["id"]:r["revision"] for r in rows}}


def get_cycle_workspace(path,group_id,cycle_id):
    with connection(path) as db:
        return cycle_workspace_state(db,group_id,cycle_id)


def start_cycle_workspace(path,group_id,cycle_id,payload):
    with transaction(path) as db:
        require_group(db,group_id,True)
        state=cycle_workspace_state(db,group_id,cycle_id)
        slot=next(s for s in state["slots"] if s["key"]==payload.legion)
        if slot["linked"] and slot["starts_at"]==payload.starts_at:
            return state
        if state["revisions"]!=payload.revisions:
            raise ValueError("Cycle changed; reopen the event card")
        if slot["cancelled"]:
            raise ValueError("This legion is cancelled in the schedule")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z",payload.starts_at) or payload.starts_at[:10]!=state["battle_date"]:
            raise ValueError("Enter the confirmed UTC time on the scheduled battle date")
        start=parse(payload.starts_at)
        if slot["session_id"] and slot["starts_at"]!=payload.starts_at:
            raise ValueError("Use the existing session time; review it in Event History if it is incorrect")
        rows=cycle_rows(db,group_id,cycle_id)
        phase="Legion "+payload.legion[-1]
        row=next((r for r in rows if r["id"]==slot["occurrence_id"]),None)
        base=row or next(r for r in rows if r["phase"] in {"Legion 1","Legion 2"})
        duration=timedelta(minutes=60)
        if row and row["precision"]=="minute" and row["ends_at"]:
            duration=parse(row["ends_at"])-parse(row["starts_at"])
        fields={k:base[k] for k in CalendarInput.model_fields}
        fields.update(phase=phase,precision="minute",starts_at=payload.starts_at,
            ends_at=(start+duration).strftime("%Y-%m-%dT%H:%MZ"),confidence="confirmed")
        entry=CalendarInput.model_validate(fields)
        validate_scope(db,group_id,entry)
        if row:
            if row["starts_at"]!=entry.starts_at or row["precision"]!="minute" or row["confidence"]!="confirmed":
                update_locked(db,group_id,row["id"],CalendarUpdate(**fields,revision=row["revision"],schedule_status="scheduled"))
            oid=row["id"]
        else:
            # Add the second legion to this occurrence only, not to the recurrence template.
            require_open_cycle_for_grouping(db,group_id,state["kind"],state["battle_date"],entry.alliance_id)
            prospective=[r for r in rows]+[fields]
            ordered=sorted(prospective,key=lambda r:{"Voting":0,"Registration":1,"Matchmaking":2,"Legion 1":3,"Legion 2":4}[r["phase"]])
            CalendarCycleCreate(kind=state["kind"],request_key="workspace-legion-setup",phases=[CalendarInput.model_validate({k:r[k] for k in CalendarInput.model_fields}) for r in ordered])
            validate_cycle_overlap(db,group_id,prospective,{r["id"] for r in rows})
            if db.execute("""SELECT 1 FROM calendar_occurrences WHERE group_id=? AND alliance_id=? AND event_type=? AND entry_cycle_date=? AND entry_session_key=?""",
                (group_id,entry.alliance_id,entry.event_type,state["battle_date"],payload.legion)).fetchone():
                raise ValueError("Legion already assigned to another schedule")
            oid=uuid.uuid4().hex
            db.execute("""INSERT INTO calendar_occurrences(id,group_id,cycle_id,event_type,scope,alliance_id,state_id,starts_at,ends_at,precision,phase,confidence,source,entry_cycle_date,entry_session_key)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'manual',?,?)""",
                (oid,group_id,cycle_id,entry.event_type,entry.scope,entry.alliance_id,entry.state_id,entry.starts_at,entry.ends_at,entry.precision,phase,entry.confidence,state["battle_date"],payload.legion))
            audit(db,"created",oid)
        revision=db.execute("SELECT revision FROM calendar_occurrences WHERE id=?",(oid,)).fetchone()[0]
        start_entry_locked(db,group_id,oid,CalendarEntryStart(revision=revision,confirmed=True))
        return cycle_workspace_state(db,group_id,cycle_id)


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
        if row["cycle_id"] and row["phase"] in {"Legion 1","Legion 2"}:
            raise ValueError("Legion grouping is assigned by the linked event cycle")
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


def series_metadata(db,series_id):
    series=db.execute("SELECT * FROM calendar_series WHERE id=?",(series_id,)).fetchone()
    row=db.execute("SELECT rule_json FROM calendar_series_rules WHERE series_id=?",(series_id,)).fetchone()
    return series,json.loads(row["rule_json"]) if row else {}


def bear_series_rule(db,series_id):
    _,rule=series_metadata(db,series_id)
    return rule if rule.get("bear_cycle_anchor") else None


def bear_assignment(db,group_id,owner,start,anchor,key,interval,sequence,ignore_id=None,*,allow_before=False,ignore_ids=()):
    canonical=parse(anchor)+timedelta(minutes=interval*sequence)
    cycle_day=canonical.date().isoformat()
    lower=-timedelta(minutes=interval) if allow_before else timedelta(0)
    if not 2000<=canonical.year<=2099 or not lower<=parse(start)-canonical<timedelta(minutes=interval) or (allow_before and parse(start)-canonical==lower):
        raise ValueError("Bear trap no longer belongs to its configured cycle")
    require_open_cycle_for_grouping(db,group_id,"bear_trap",cycle_day,owner)
    others=db.execute("""SELECT c.*,s.interval_minutes,r.rule_json FROM calendar_occurrences c
        LEFT JOIN calendar_series s ON s.id=c.series_id
        LEFT JOIN calendar_series_rules r ON r.series_id=c.series_id
        WHERE c.group_id=? AND c.event_type='bear_trap' AND c.id IS NOT ?
        AND (c.entry_cycle_date=? OR (c.alliance_id=? AND substr(c.starts_at,1,10)=?))""",
        (group_id,ignore_id,cycle_day,owner,start[:10])).fetchall()
    for other in others:
        if other["id"] in ignore_ids:
            continue
        if other["alliance_id"]==owner and (other["starts_at"]==start or (other["precision"]=="date" and other["starts_at"]==start[:10])):
            raise ValueError("Matching Bear trap schedule already exists")
        if other["entry_cycle_date"]!=cycle_day:
            continue
        if other["entry_session_key"]==key:
            raise ValueError("Trap identity already assigned in this Bear cycle")
        rule=json.loads(other["rule_json"]) if other["rule_json"] else {}
        if rule.get("bear_cycle_anchor"):
            other_cycle=parse(rule["bear_cycle_anchor"])+timedelta(minutes=other["interval_minutes"]*other["sequence"])
            if other["interval_minutes"]!=interval or other_cycle!=canonical:
                raise ValueError("Bear schedules disagree on the shared cycle anchor or cadence")
    return cycle_day,key


def missing_bear_forecasts(db,group_id,cycle_day):
    """Do not finalize a configured cycle if an expected forecast never materialized."""
    day=parse(cycle_day)
    rows=db.execute("""SELECT s.*,r.rule_json,n.status AS rolling_status
        FROM calendar_series s JOIN calendar_series_rules r ON r.series_id=s.id
        LEFT JOIN calendar_rolling_series n ON n.series_id=s.id WHERE s.group_id=?""",(group_id,)).fetchall()
    missing=[]
    for row in rows:
        rule=json.loads(row["rule_json"])
        if not rule.get("bear_cycle_anchor") or row["rolling_status"]=="stopped":
            continue
        anchor=parse(rule["bear_cycle_anchor"])
        step=timedelta(minutes=row["interval_minutes"])
        sequence=max(0,(day-anchor)//step)
        if anchor+sequence*step<day:
            sequence+=1
        if not day<=anchor+sequence*step<day+timedelta(days=1):
            continue
        if rule.get("end_sequence") is not None and sequence>=rule["end_sequence"]:
            continue
        if row["rolling_status"] is None and sequence>=row["occurrence_count"]:
            continue
        if not db.execute("SELECT 1 FROM calendar_occurrences WHERE series_id=? AND sequence=?",(row["id"],sequence)).fetchone():
            missing.append(rule["bear_session_key"])
    return sorted(set(missing))


# Persist only future occurrences. The independent cursor is never inferred from
# a manually edited or cancelled occurrence. The initial series count remains
# immutable, because calendar_series has a legacy 180-occurrence bound.
ROLLING_HORIZON_DAYS = 60


def renew_series(path, series_id, now):
    with transaction(path) as db:
        series = db.execute("""SELECT r.*,s.group_id,s.interval_minutes
            FROM calendar_rolling_series r JOIN calendar_series s ON s.id=r.series_id
            JOIN alliance_groups g ON g.id=s.group_id
            WHERE r.series_id=? AND r.status='active' AND g.status='active'""",(series_id,)).fetchone()
        if not series:
            return 0
        template = CalendarInput.model_validate_json(series["template_json"])
        try:
            validate_scope(db,series["group_id"],template)
        except (ValueError,LookupError):
            return 0
        start = parse(series["next_start"])
        interval = timedelta(minutes=series["interval_minutes"])
        duration = parse(template.ends_at)-parse(template.starts_at) if template.ends_at else None
        threshold = future_threshold(template.precision,now)
        horizon = now + timedelta(days=ROLLING_HORIZON_DAYS)
        sequence = series["next_sequence"]
        if start < threshold:
            missed = (threshold-start)//interval
            if start+missed*interval < threshold:
                missed += 1
            start += missed*interval
            sequence += missed
        fmt = "%Y-%m-%d" if template.precision=="date" else "%Y-%m-%dT%H:%MZ"
        count = 0
        status = "active"
        grouping=bear_series_rule(db,series_id)
        while start <= horizon:
            if start.year > 2099 or (duration and (start+duration).year>2099):
                status = "stopped"
                break
            value = start.strftime(fmt)
            end = (start+duration).strftime(fmt) if duration else None
            matches = db.execute("""SELECT starts_at,precision FROM calendar_occurrences
                WHERE group_id=? AND event_type=? AND scope=? AND alliance_id IS ? AND state_id=? AND phase=?
                AND starts_at>=? AND starts_at<?""",
                (series["group_id"],template.event_type,template.scope,template.alliance_id,template.state_id,template.phase,
                 value[:10],(start.date()+timedelta(days=1)).isoformat())).fetchall()
            if any(r["starts_at"]==value or (r["starts_at"][:10]==value[:10] and
                   (r["precision"]=="date" or template.precision=="date")) for r in matches):
                status = "conflict"
                break
            cycle_day=key=None
            if grouping:
                try:
                    cycle_day,key=bear_assignment(db,series["group_id"],template.alliance_id,value,grouping["bear_cycle_anchor"],grouping["bear_session_key"],series["interval_minutes"],sequence,allow_before=True)
                except ValueError:
                    status="conflict"
                    break
            oid = uuid.uuid4().hex
            db.execute("""INSERT INTO calendar_occurrences(id,group_id,series_id,sequence,event_type,scope,alliance_id,state_id,
                       starts_at,ends_at,precision,phase,confidence,source)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'estimated','recurrence')""",
                       (oid,series["group_id"],series_id,sequence,template.event_type,template.scope,template.alliance_id,
                        template.state_id,value,end,template.precision,template.phase))
            if grouping:
                db.execute("UPDATE calendar_occurrences SET entry_cycle_date=?,entry_session_key=? WHERE id=?",(cycle_day,key,oid))
            db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES ('created','calendar_occurrence',?,'system')",(oid,))
            count += 1
            sequence += 1
            start += interval
        if start.year>2099:
            status = "stopped"
        db.execute("UPDATE calendar_rolling_series SET next_start=?,next_sequence=?,status=? WHERE series_id=?",
                   (start.strftime(fmt),sequence,status,series_id))
        return count


def renew_schedules(path, now=None):
    now = now or datetime.now(timezone.utc)
    with connection(path) as db:
        ids = [r[0] for r in db.execute("SELECT series_id FROM calendar_rolling_series WHERE status='active'")]
    total = 0
    for series_id in ids:
        total += renew_series(path,series_id,now)
    with connection(path) as db:
        cycle_ids=[r[0] for r in db.execute("SELECT id FROM calendar_cycle_series WHERE status='active'")]
    for series_id in cycle_ids:
        total += renew_cycle_series(path,series_id,now)
    return total
