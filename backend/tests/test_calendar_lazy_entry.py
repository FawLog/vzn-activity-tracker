from app.database import connection
from test_calendar import setup


def test_lazy_entry_does_not_write_on_read_and_retries_safely(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    base={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01T15:00Z","precision":"minute","phase":"Legion 1"}
    row=c.post(root+"/calendar",json=base).json()["items"][0]
    target=root+"/calendar/"+row["id"]
    assert c.get(target+"/event-link").json()["linked"] is None
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
    payload={"revision":1,"confirmed":True}
    result=c.post(target+"/start-entry",json=payload)
    assert result.status_code==200,result.text
    linked=result.json()["linked"]
    assert linked["session_key"]=="legion_1"
    assert c.post(target+"/start-entry",json=payload).json()["linked"]==linked
    row2=c.post(root+"/calendar",json={**base,"starts_at":"2090-06-01T20:00Z","phase":"Legion 2"}).json()["items"][0]
    result2=c.post(root+"/calendar/"+row2["id"]+"/start-entry",json=payload)
    assert result2.status_code==200,result2.text
    assert result2.json()["linked"]["id"]==linked["id"]
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM event_sessions").fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM event_session_roster").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM event_participants").fetchone()[0]==0


def test_lazy_entry_refuses_ambiguous_identity(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    base={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01T15:00Z","precision":"minute"}
    for patch in ({},{"event_type":"bear_trap","phase":"Trap 1"},{"confidence":"estimated","phase":"Legion 1"},{"event_type":"canyon","phase":"Registration"}):
        row=c.post(root+"/calendar",json={**base,**patch}).json()["items"][0]
        assert c.post(root+"/calendar/"+row["id"]+"/start-entry",json={"revision":1,"confirmed":True}).status_code==409
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0


def test_lazy_entry_reuses_single_main_record(authenticated_client):
    c=authenticated_client
    root,aid=setup(c)
    eid=c.post(root+"/alliances/"+aid+"/events",json={"event_type":"alliance_mobilization","occurred_on":"2090-06-01","status":"draft"}).json()["id"]
    row=c.post(root+"/calendar",json={"event_type":"alliance_mobilization","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01","precision":"date"}).json()["items"][0]
    result=c.post(root+"/calendar/"+row["id"]+"/start-entry",json={"revision":1,"confirmed":True})
    assert result.status_code==200,result.text
    assert result.json()["linked"]["id"]==eid
