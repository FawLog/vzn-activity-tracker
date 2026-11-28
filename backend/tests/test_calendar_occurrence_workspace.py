import pytest
from app.database import connection
from test_calendar import setup


@pytest.mark.parametrize("kind",["alliance_mobilization","alliance_championship"])
def test_single_event_workspace_confirms_and_reuses_one_record(authenticated_client,settings,kind):
    c=authenticated_client
    root,aid=setup(c)
    common={"event_type":kind,"scope":"alliance","alliance_id":aid,"state_id":"1001","precision":"date","confidence":"estimated","starts_at":"2090-06-01","ends_at":"2090-06-06"}
    row=c.post(root+"/calendar",json=common).json()["items"][0]
    url=root+"/calendar/"+row["id"]+"/workspace"
    plan=c.get(url).json()
    assert plan["event_id"] is None
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
    data={"member_id":row["id"],"revision":row["revision"],"confirmed":True}
    assert c.post(url,json={**data,"revision":999}).status_code==409
    first=c.post(url,json=data)
    assert first.status_code==200,first.text
    result=first.json()
    assert result["event_id"] and result["slots"][0]["linked"]
    assert c.post(url,json=data).json()==result
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM event_sessions").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM event_participants").fetchone()[0]==0


def test_bear_workspace_shared_across_traps_and_midnight(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    common={"event_type":"bear_trap","scope":"alliance","alliance_id":aid,"state_id":"1001","precision":"minute","confidence":"confirmed"}
    rows=[]
    for key,time in (("trap_1","2090-06-01T23:30Z"),("trap_2","2090-06-02T00:30Z")):
        row=c.post(root+"/calendar",json={**common,"starts_at":time,"phase":key.replace("_"," ").title()}).json()["items"][0]
        grouped=c.put(root+"/calendar/"+row["id"]+"/entry-group",json={"revision":row["revision"],"cycle_date":"2090-06-01","session_key":key})
        assert grouped.status_code==200,grouped.text
        rows.append(row)
    urls=[root+"/calendar/"+r["id"]+"/workspace" for r in rows]
    state=c.get(urls[0]).json()
    assert c.get(urls[1]).json()==state
    assert len(state["slots"])==2 and state["event_id"] is None
    for i,slot in enumerate(state["slots"]):
        response=c.post(urls[1-i],json={"member_id":slot["id"],"revision":slot["revision"],"confirmed":True})
        assert response.status_code==200,response.text
    result=c.get(urls[0]).json()
    assert c.get(urls[1]).json()==result
    assert result["event_id"] and all(s["linked"] for s in result["slots"])
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1
        assert db.execute("SELECT occurred_on FROM events").fetchone()[0]=="2090-06-01"
        assert db.execute("SELECT COUNT(*) FROM event_sessions").fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM event_participants").fetchone()[0]==0
