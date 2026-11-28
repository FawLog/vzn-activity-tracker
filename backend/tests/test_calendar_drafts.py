from app.database import connection
from test_calendar import setup


def test_create_draft_and_session_atomically(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    base={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01T15:00Z","precision":"minute"}
    row=c.post(root+"/calendar",json=base).json()["items"][0]
    target=root+"/calendar/"+row["id"]+"/draft"
    payload={"revision":1,"confirmed":True,"session_key":"legion_1"}
    result=c.post(target,json=payload)
    assert result.status_code==201,result.text
    eid=result.json()["linked"]["id"]
    assert result.json()["linked"]["status"]=="draft"
    assert c.post(target,json=payload).status_code==409
    row2=c.post(root+"/calendar",json={**base,"starts_at":"2090-06-01T20:00Z"}).json()["items"][0]
    target2=root+"/calendar/"+row2["id"]+"/draft"
    assert c.post(target2,json={**payload,"session_key":"legion_2"}).status_code==409
    assert c.post(target2,json={**payload,"event_id":eid}).status_code==409
    assert c.post(target2,json={**payload,"event_id":eid,"session_key":"legion_2"}).status_code==201
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM event_sessions").fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM event_session_roster").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM event_participants").fetchone()[0]==0


def test_bear_cycle_requires_explicit_date(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    row=c.post(root+"/calendar",json={"event_type":"bear_trap","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-02T15:00Z","precision":"minute"}).json()["items"][0]
    target=root+"/calendar/"+row["id"]+"/draft"
    payload={"revision":1,"confirmed":True,"session_key":"trap_1"}
    assert c.post(target,json=payload).status_code==409
    result=c.post(target,json={**payload,"cycle_date":"2090-06-01"})
    assert result.status_code==201,result.text
    assert result.json()["linked"]["occurred_on"]=="2090-06-01"
    assert result.json()["linked"]["started_at"].startswith("2090-06-02T15:00")
    assert c.get(root+"/calendar/"+row["id"]+"/bear-cycles?cycle_date=2090-06-01").json()["items"][0]["id"]==result.json()["linked"]["id"]


def test_draft_requires_confirmed_schedule_and_csrf(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    row=c.post(root+"/calendar",json={"event_type":"alliance_mobilization","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01","precision":"date","confidence":"estimated"}).json()["items"][0]
    target=root+"/calendar/"+row["id"]+"/draft"
    assert c.post(target,json={"revision":1,"confirmed":True}).status_code==409
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
    c.headers.pop("X-CSRF-Token")
    assert c.post(target,json={"revision":1,"confirmed":True}).status_code==403
