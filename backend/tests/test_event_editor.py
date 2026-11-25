from app.services import event_editor
from app.services.event_editor import SessionCreate, SessionSave
from test_api import create_onboarded_group
import pytest


def test_manual_sessions_and_evidence(authenticated_client, settings):
    client = authenticated_client
    group = create_onboarded_group(client)
    gid = group["id"]
    aid = client.get(f"/api/v1/groups/{gid}/alliances").json()["items"][0]["id"]
    for fid in ("main", "reserve"):
        assert client.post(f"/api/v1/groups/{gid}/players", json={"fid": fid, "nickname": fid}).status_code == 201
    event = client.post(f"/api/v1/groups/{gid}/alliances/{aid}/events", json={"event_type":"foundry","occurred_on":"2026-11-15"}).json()
    eid = event["id"]
    path = settings.database_path
    session = event_editor.create_session(path,gid,eid,SessionCreate(session_key="legion_1",started_at="2026-11-15T17:00:00Z"))["sessions"][0]
    sid = session["id"]
    rows = [{"fid":fid,"nickname":fid,"eligibility":"confirmed","registration":"registered","role":role,"attendance":"confirmed_absent"} for fid,role in (("main","main"),("reserve","substitute"))]
    with pytest.raises(ValueError, match="complete attendance"):
        event_editor.save(path,gid,eid,sid,SessionSave(revision=0,rows=rows))
    result = event_editor.save(path,gid,eid,sid,SessionSave(revision=0,attendance_complete=True,rows=rows))
    assert [r["attendance"] for r in result["sessions"][0]["rows"]] == ["confirmed_absent","confirmed_absent"]
    with pytest.raises(ValueError, match="reload"):
        event_editor.save(path,gid,eid,sid,SessionSave(revision=0,rows=[]))
    with pytest.raises(LookupError):
        event_editor.read(path,"other",eid)
    assert event_editor.publish(path,gid,eid)["status"] == "published"
    with pytest.raises(ValueError,match="draft"):
        event_editor.save(path,gid,eid,sid,SessionSave(revision=1,rows=[]))
