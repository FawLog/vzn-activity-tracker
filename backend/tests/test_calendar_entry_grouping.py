from app.database import connection
from test_calendar import setup


def test_grouped_bear_across_hosts_and_dates(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    academy=c.post(root+"/alliances",json={"name":"Academy","tag":"ACA","state_id":"1001"})
    assert academy.status_code==201,academy.text
    academy_id=academy.json()["id"]
    base={"event_type":"bear_trap","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01T15:00Z","precision":"minute","phase":"Trap 1"}
    first=c.post(root+"/calendar",json=base).json()["items"][0]
    second=c.post(root+"/calendar",json={**base,"alliance_id":academy_id,"starts_at":"2090-06-02T20:00Z"}).json()["items"][0]
    t1=root+"/calendar/"+first["id"]
    t2=root+"/calendar/"+second["id"]
    p={"revision":1,"cycle_date":"2090-06-01","session_key":"trap_1"}
    assert c.put(t1+"/entry-group",json=p).status_code==200
    assert c.put(t2+"/entry-group",json=p).status_code==409
    grouped=c.put(t2+"/entry-group",json={**p,"session_key":"trap_2"})
    assert grouped.status_code==200,grouped.text
    assert len(grouped.json()["group_members"])==2
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
    payload={"revision":2,"confirmed":True}
    one=c.post(t1+"/start-entry",json=payload)
    assert one.status_code==200,one.text
    two=c.post(t2+"/start-entry",json=payload)
    assert two.status_code==200,two.text
    assert one.json()["linked"]["id"]==two.json()["linked"]["id"]
    assert two.json()["linked"]["session_key"]=="trap_2"
    assert c.put(t2+"/entry-group",json={"revision":3}).status_code==409
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1
        assert db.execute("SELECT COUNT(DISTINCT host_alliance_id) FROM event_sessions").fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM event_session_roster").fetchone()[0]==0


def test_legions_group_across_midnight_and_protect_schedule(authenticated_client):
    c=authenticated_client
    root,aid=setup(c)
    base={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01T23:00Z","precision":"minute","phase":"Legion 1"}
    first=c.post(root+"/calendar",json=base).json()["items"][0]
    second=c.post(root+"/calendar",json={**base,"starts_at":"2090-06-02T01:00Z","phase":"Legion 2"}).json()["items"][0]
    t1=root+"/calendar/"+first["id"]
    t2=root+"/calendar/"+second["id"]
    p={"revision":1,"cycle_date":"2090-06-01","session_key":"legion_1"}
    assert c.put(t1+"/entry-group",json=p).status_code==200
    assert c.put(t2+"/entry-group",json=p).status_code==409
    assert c.put(t2+"/entry-group",json={**p,"session_key":"legion_2"}).status_code==200
    assert c.put(t1,json={**base,"revision":2,"starts_at":"2090-06-01T22:00Z"}).status_code==409
    one=c.post(t1+"/start-entry",json={"revision":2,"confirmed":True})
    two=c.post(t2+"/start-entry",json={"revision":2,"confirmed":True})
    assert one.status_code==two.status_code==200,(one.text,two.text)
    assert one.json()["linked"]["id"]==two.json()["linked"]["id"]
