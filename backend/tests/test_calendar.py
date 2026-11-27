from app.database import connection

def setup(client):
    group=client.post("/api/v1/onboarding/groups",json={"name":"Calendar","primary_alliance_name":"Calendar","primary_alliance_tag":"CAL","primary_alliance_state_id":"1001"}).json()
    root=f"/api/v1/groups/{group['id']}"
    aid=client.get(root+"/alliances").json()["items"][0]["id"]
    return root,aid

def test_calendar_series_and_exception(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    payload={"event_type":"bear_trap","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2028-02-28T15:00Z","precision":"minute","phase":"Trap 1","interval_minutes":2850,"occurrence_count":3}
    response=c.post(url,json=payload)
    assert response.status_code==201,response.text
    rows=response.json()["items"]
    assert [r["starts_at"] for r in rows]==["2028-02-28T15:00Z","2028-03-01T14:30Z","2028-03-03T14:00Z"]
    assert [r["confidence"] for r in rows]==["confirmed","estimated","estimated"]
    query="?start=2028-02-28&end=2028-03-04"
    assert c.get(url+query).json()["items"]==rows
    edit={k:v for k,v in payload.items() if k not in ("interval_minutes","occurrence_count")}
    edit.update(starts_at="2028-03-01T16:00Z",revision=1,schedule_status="cancelled")
    target=url+"/"+rows[1]["id"]
    assert c.put(target,json=edit).status_code==200
    assert c.put(target,json=edit).status_code==409
    updated=c.get(url+query).json()["items"]
    assert updated[1]["id"]==rows[1]["id"]
    assert updated[1]["schedule_status"]=="cancelled"
    assert updated[0]==rows[0] and updated[2]==rows[2]
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type='calendar_occurrence'").fetchone()[0]==4

def test_calendar_bounds_scope_and_precision(authenticated_client):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    payload={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2028-02-29","ends_at":"2028-03-02","precision":"date"}
    assert c.post(url,json={**payload,"alliance_id":"missing"}).status_code==404
    assert c.post(url,json={**payload,"starts_at":"2028-02-29T00:00Z"}).status_code==422
    assert c.post(url,json={**payload,"interval_minutes":2850,"occurrence_count":2}).status_code==422
    assert c.post(url,json=payload).status_code==201
    assert len(c.get(url+"?start=2028-03-01&end=2028-03-02").json()["items"])==1
    assert c.get(url+"?start=2028-03-02&end=2028-03-03").json()["items"]==[]
    assert c.get(url+"?start=2028-01-01&end=2029-01-01").status_code==422
    assert c.get("/api/v1/groups/missing/calendar?start=2028-03-01&end=2028-03-02").status_code==404
    second=c.post("/api/v1/groups",json={"name":"Other","primary_alliance_name":"Other","primary_alliance_tag":"OTH","primary_alliance_state_id":"1001"}).json()
    other=f"/api/v1/groups/{second['id']}/calendar"
    assert c.post(other,json=payload).status_code==404
    assert c.get(other+"?start=2028-02-28&end=2028-03-03").json()["items"]==[]
    c.headers.pop("X-CSRF-Token")
    assert c.post(url,json=payload).status_code==403

def test_calendar_requires_auth(client):
    assert client.get("/api/v1/groups/missing/calendar?start=2028-01-01&end=2028-01-02").status_code==401
