from app.database import connection
from test_calendar import setup


def test_bear_session_link_uses_host_and_session_date(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    eid=c.post(root+"/alliances/"+aid+"/events",json={"event_type":"bear_trap","occurred_on":"2090-06-01","status":"draft"}).json()["id"]
    result=c.post(root+"/events/"+eid+"/sessions",json={"session_key":"trap_1","started_at":"2090-06-02T15:00:00Z","host_alliance_id":aid})
    assert result.status_code==201,result.text
    sid=result.json()["sessions"][0]["id"]
    payload={"event_type":"bear_trap","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-02T15:00Z","precision":"minute","phase":"Trap 1"}
    row=c.post(root+"/calendar",json=payload).json()["items"][0]
    target=root+"/calendar/"+row["id"]+"/event-link"
    assert c.get(target).json()["sessions"][0]["id"]==sid
    assert c.put(target,json={"event_id":eid,"revision":1}).status_code==409
    assert c.put(target,json={"event_id":eid,"session_id":sid,"revision":1}).status_code==200
    assert c.get(target).json()["linked"]["session_id"]==sid
    duplicate=c.post(root+"/calendar",json={**payload,"phase":"Other"}).json()["items"][0]
    other=root+"/calendar/"+duplicate["id"]+"/event-link"
    assert c.get(other).json()["sessions"]==[]
    assert c.put(other,json={"event_id":eid,"session_id":sid,"revision":1}).status_code==409
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM event_session_roster").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1
    assert c.post(root+"/events/"+eid+"/manage",json={"action":"delete_session","confirmed":True,"session_id":sid}).status_code==200
    assert c.get(target).json()["linked"] is None


def test_legion_link_upgrade_and_wrong_time(authenticated_client):
    c=authenticated_client
    root,aid=setup(c)
    eid=c.post(root+"/alliances/"+aid+"/events",json={"event_type":"foundry","occurred_on":"2090-06-01","status":"draft"}).json()["id"]
    sid=c.post(root+"/events/"+eid+"/sessions",json={"session_key":"legion_1","started_at":"2090-06-01T15:00:00Z"}).json()["sessions"][0]["id"]
    payload={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01T14:00Z","precision":"minute"}
    row=c.post(root+"/calendar",json=payload).json()["items"][0]
    target=root+"/calendar/"+row["id"]+"/event-link"
    assert c.get(target).json()["sessions"]==[]
    assert c.put(target,json={"event_id":eid,"session_id":sid,"revision":1}).status_code==409
    row=c.post(root+"/calendar",json={**payload,"starts_at":"2090-06-01","precision":"date"}).json()["items"][0]
    target=root+"/calendar/"+row["id"]+"/event-link"
    assert c.put(target,json={"event_id":eid,"revision":1}).status_code==200
    assert c.put(target,json={"event_id":eid,"session_id":sid,"revision":2}).status_code==200
    assert c.get(root+"/events/"+eid+"/calendar").json()["items"][0]["linked_session_id"]==sid
