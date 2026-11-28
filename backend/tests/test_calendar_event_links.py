from app.database import connection
from test_calendar import setup


def test_explicit_calendar_event_link(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    schedule={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01","precision":"date"}
    row=c.post(root+"/calendar",json=schedule).json()["items"][0]
    target=root+"/calendar/"+row["id"]+"/event-link"
    assert c.get(target).json()["items"]==[]
    event=c.post(root+"/alliances/"+aid+"/events",json={"event_type":"foundry","occurred_on":"2090-06-01","status":"draft"})
    assert event.status_code==201,event.text
    eid=event.json()["id"]
    candidate=c.get(target).json()
    assert candidate["items"][0]["id"]==eid and candidate["linked"] is None
    assert c.put(target,json={"event_id":eid,"revision":1}).status_code==200
    assert c.put(target,json={"event_id":None,"revision":1}).status_code==409
    assert c.get(root+"/events/"+eid+"/calendar").json()["items"][0]["id"]==row["id"]
    assert c.put(root+"/calendar/"+row["id"],json={**schedule,"revision":2,"schedule_status":"cancelled"}).status_code==409
    assert c.post(root+"/events/"+eid+"/manage",json={"action":"date","confirmed":True,"occurred_on":"2090-06-02"}).status_code==409
    assert c.put(target,json={"event_id":None,"revision":2}).status_code==200
    assert c.get(root+"/events/"+eid+"/calendar").json()["items"]==[]
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM event_participants").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM event_sessions").fetchone()[0]==0
    c.headers.pop("X-CSRF-Token")
    assert c.put(target,json={"event_id":eid,"revision":3}).status_code==403


def test_incompatible_link_and_delete(authenticated_client):
    c=authenticated_client
    root,aid=setup(c)
    payload={"event_type":"canyon","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01","precision":"date"}
    row=c.post(root+"/calendar",json=payload).json()["items"][0]
    target=root+"/calendar/"+row["id"]+"/event-link"
    wrong=c.post(root+"/alliances/"+aid+"/events",json={"event_type":"foundry","occurred_on":"2090-06-01","status":"draft"}).json()["id"]
    assert c.put(target,json={"event_id":wrong,"revision":1}).status_code==409
    event=c.post(root+"/alliances/"+aid+"/events",json={"event_type":"canyon","occurred_on":"2090-06-01","status":"draft"}).json()["id"]
    assert c.put(target,json={"event_id":event,"revision":1}).status_code==200
    assert c.get("/api/v1/groups/missing/events/"+event+"/calendar").status_code==404
    assert c.post(root+"/events/"+event+"/manage",json={"action":"delete","confirmed":True}).status_code==200
    assert c.get(target).json()["linked"] is None
