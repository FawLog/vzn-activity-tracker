"""State opening dates: independent from roster observations and event results."""
from datetime import date, datetime, UTC, timedelta
from pydantic import BaseModel, ConfigDict, Field
from ..database import connection, transaction


class StateDateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    opened_on: date | None
    revision: int = Field(ge=0)


def valid_date(value, today):
    if not isinstance(value, str):
        raise ValueError("Missing state opening date")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value or not date(2000,1,1) <= parsed <= today:
        raise ValueError("Invalid state opening date")
    return value


def state_dates(path, group_id):
    today = datetime.now(UTC).date()
    with connection(path) as db:
        if not db.execute("SELECT 1 FROM alliance_groups WHERE id=?", (group_id,)).fetchone():
            raise LookupError("Group not found")
        rows = db.execute("""SELECT DISTINCT a.state_id,p.provider_opened_on,p.manual_opened_on,p.last_success_at,p.last_status,p.revision
            FROM alliances a LEFT JOIN state_calendar_profiles p ON a.state_id=p.state_id
            WHERE a.group_id=? AND a.status='active' ORDER BY a.state_id""",(group_id,)).fetchall()
    items=[]
    for row in rows:
        item=dict(row)
        opened=item["manual_opened_on"] or item["provider_opened_on"]
        item.update(opened_on=opened,source="manual" if item["manual_opened_on"] else "whiteoutstats" if opened else None,
                    age_days=(today-date.fromisoformat(opened)).days if opened else None,revision=item["revision"] or 0)
        items.append(item)
    return {"items":items}


def update_date(path,group_id,state_id,payload):
    opened=valid_date(payload.opened_on.isoformat(),datetime.now(UTC).date()) if payload.opened_on else None
    with transaction(path) as db:
        if not db.execute("""SELECT 1 FROM alliances a JOIN alliance_groups g ON g.id=a.group_id
            WHERE a.group_id=? AND a.state_id=? AND a.status='active' AND g.status='active'""",(group_id,state_id)).fetchone():
            raise LookupError("Active state not found in selected group")
        old=db.execute("SELECT revision FROM state_calendar_profiles WHERE state_id=?",(state_id,)).fetchone()
        if (old["revision"] if old else 0)!=payload.revision:
            raise ValueError("State date changed; reload before saving")
        db.execute("""INSERT INTO state_calendar_profiles(state_id,manual_opened_on) VALUES (?,?)
            ON CONFLICT(state_id) DO UPDATE SET manual_opened_on=excluded.manual_opened_on,revision=revision+1""",(state_id,opened))
        db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES ('updated','state_calendar_profile',?,'admin')",(state_id,))
    return next(i for i in state_dates(path,group_id)["items"] if i["state_id"]==state_id)


def due_states(path):
    cutoff=(datetime.now(UTC)-timedelta(days=1)).isoformat(timespec="seconds")
    with connection(path) as db:
        return [r[0] for r in db.execute("""SELECT DISTINCT a.state_id FROM alliances a
            JOIN alliance_groups g ON g.id=a.group_id
            LEFT JOIN state_calendar_profiles p ON p.state_id=a.state_id
            WHERE a.status='active' AND g.status='active'
            AND (p.last_attempt_at IS NULL OR p.last_attempt_at<=?) ORDER BY a.state_id""",(cutoff,))]


def sync_state(path,provider,state_id):
    now=datetime.now(UTC)
    stamp=now.isoformat(timespec="seconds")
    cutoff=(now-timedelta(days=1)).isoformat(timespec="seconds")
    with transaction(path) as db:
        old=db.execute("SELECT last_attempt_at FROM state_calendar_profiles WHERE state_id=?",(state_id,)).fetchone()
        if old and old[0] and old[0]>cutoff:
            return False
        db.execute("""INSERT INTO state_calendar_profiles(state_id,last_attempt_at,last_status) VALUES (?,?,'pending')
            ON CONFLICT(state_id) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,last_status='pending'""",(state_id,stamp))
    opened=None
    try:
        response=provider.fetch_state(state_id)
        if response.status_code==200 and isinstance(response.body,dict):
            body=response.body.get("state",response.body)
            if isinstance(body,dict) and str(body.get("kid"))==state_id:
                opened=valid_date(body.get("opened_on"),now.date())
    except (RuntimeError,ValueError,TypeError):
        pass
    with transaction(path) as db:
        if opened:
            db.execute("""UPDATE state_calendar_profiles SET provider_opened_on=?,last_success_at=?,last_status='success',
                revision=revision+CASE WHEN provider_opened_on IS NOT ? THEN 1 ELSE 0 END WHERE state_id=? AND last_attempt_at=?""",(opened,stamp,opened,state_id,stamp))
        else:
            db.execute("UPDATE state_calendar_profiles SET last_status='failed' WHERE state_id=? AND last_attempt_at=?",(state_id,stamp))
    return opened is not None
