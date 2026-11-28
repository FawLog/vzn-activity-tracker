import pytest
from app.database import connection
from test_calendar import setup


@pytest.mark.parametrize("kind",["foundry","canyon"])
def test_any_cycle_phase_resolves_one_event_and_two_legions(authenticated_client,settings,kind):
    c=authenticated_client
    root,aid=setup(c)
    common={"event_type":kind,"scope":"alliance","alliance_id":aid,"state_id":"1001","precision":"date","confidence":"estimated"}
    phases=[{**common,"phase":phase,"starts_at":start,"ends_at":end} for phase,start,end in [
        ("Voting","2090-03-06","2090-03-08"),("Registration","2090-03-08","2090-03-10"),
        ("Matchmaking","2090-03-10","2090-03-12"),("Legion 1","2090-03-12",None)]]
    response=c.post(root+"/calendar/cycles",json={"kind":kind,"request_key":"workspace-cycle-0001","phases":phases,"occurrence_count":2,"interval_days":14})
    assert response.status_code==201,response.text
    rows=response.json()["items"]
    url=root+"/calendar/cycles/"+rows[0]["cycle_id"]+"/workspace"
    state=c.get(url).json()
    assert state["event_id"] is None and len(state["slots"])==2 and state["slots"][1]["occurrence_id"] is None
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
    payload={"legion":"legion_1","starts_at":"2090-03-12T14:00Z","revisions":state["revisions"]}
    assert c.post(url,json={**payload,"starts_at":"2090-03-13T14:00Z"}).status_code==409
    first=c.post(url,json=payload)
    assert first.status_code==200,first.text
    one=first.json()
    assert c.post(url,json=payload).json()==one
    assert one["slots"][0]["linked"] and one["event_id"]
    assert c.get(root+"/calendar/cycles/"+rows[1]["cycle_id"]+"/workspace").json()==one
    second={"legion":"legion_2","starts_at":"2090-03-12T19:00Z","revisions":one["revisions"]}
    assert c.post(url,json={**second,"starts_at":"2090-03-12T14:00Z"}).status_code==409
    assert c.get(url).json()==one
    result=c.post(url,json=second)
    assert result.status_code==200,result.text
    two=result.json()
    assert two["event_id"]==one["event_id"] and all(s["linked"] for s in two["slots"])
    assert len({s["session_id"] for s in two["slots"]})==2
    assert c.get(url).json()==two
    assert c.get(root+"/calendar/cycles/"+rows[4]["cycle_id"]+"/workspace").json()["event_id"] is None
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM event_sessions").fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM event_participants").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM calendar_event_links").fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM calendar_occurrences").fetchone()[0]==9


def test_cycle_workspace_reuses_two_planned_sessions_and_rejects_stale_revision(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    from test_calendar_cycle_series import create
    rows=create(c,root,aid,rolling=False)
    url=root+"/calendar/cycles/"+rows[0]["cycle_id"]+"/workspace"
    original=c.get(url).json()
    second=c.post(url,json={"legion":"legion_2","starts_at":"2090-03-12T19:00Z","revisions":original["revisions"]})
    assert second.status_code==200,second.text
    one=second.json()
    payload={"legion":"legion_1","starts_at":"2090-03-12T14:00Z","revisions":original["revisions"]}
    assert c.post(url,json=payload).status_code==409
    assert c.post(url,json={**payload,"revisions":one["revisions"]}).status_code==200
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM calendar_occurrences").fetchone()[0]==25
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM event_sessions").fetchone()[0]==2
