"""Reusable alliance scheduling defaults, separate from calendar occurrences."""
import json
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..database import connection, transaction
from .calendar import CalendarCreate, require_group, validate_scope


class TemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1,max_length=80)
    schedule: CalendarCreate

    @model_validator(mode="after")
    def validate_template(self):
        self.name = self.name.strip()
        if not self.name or self.schedule.scope != "alliance" or self.schedule.request_key is not None:
            raise ValueError("Choose a name and an alliance schedule without a request key")
        return self


def serialize(row):
    return {"id":row["id"],"name":row["name"],"alliance_id":row["alliance_id"],"schedule":json.loads(row["schedule_json"])}


def list_templates(path,group_id):
    with connection(path) as db:
        require_group(db,group_id)
        rows = db.execute("""SELECT t.* FROM calendar_templates t JOIN alliances a ON a.id=t.alliance_id
            AND a.group_id=t.group_id WHERE t.group_id=? AND a.status='active'
            ORDER BY t.name COLLATE NOCASE,t.id""",(group_id,)).fetchall()
        return {"items":[serialize(row) for row in rows]}


def create_template(path,group_id,payload):
    with transaction(path) as db:
        validate_scope(db,group_id,payload.schedule)
        rows=db.execute("SELECT name,alliance_id FROM calendar_templates WHERE group_id=?",(group_id,)).fetchall()
        if len(rows)>=100:
            raise ValueError("Maximum 100 saved schedule templates per group")
        if any(r["alliance_id"]==payload.schedule.alliance_id and r["name"].casefold()==payload.name.casefold() for r in rows):
            raise ValueError("A template with this name already exists for the alliance")
        oid=uuid.uuid4().hex
        schedule=payload.schedule.model_dump(mode="json",exclude={"request_key","bear_cycle_anchor","bear_session_key"})
        schedule["confidence"]="estimated"
        db.execute("INSERT INTO calendar_templates(id,group_id,alliance_id,name,schedule_json) VALUES (?,?,?,?,?)",
                   (oid,group_id,payload.schedule.alliance_id,payload.name,json.dumps(schedule)))
        db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES ('created','calendar_template',?,'admin')",(oid,))
        return serialize(db.execute("SELECT * FROM calendar_templates WHERE id=?",(oid,)).fetchone())


def delete_template(path,group_id,template_id):
    with transaction(path) as db:
        require_group(db,group_id,True)
        result=db.execute("DELETE FROM calendar_templates WHERE group_id=? AND id=?",(group_id,template_id))
        if not result.rowcount:
            raise LookupError("Schedule template not found")
        db.execute("INSERT INTO audit_log(action,entity_type,entity_id,actor) VALUES ('deleted','calendar_template',?,'admin')",(template_id,))
        return {"deleted":True}
