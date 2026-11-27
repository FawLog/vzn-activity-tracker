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
    result = event_editor.save(path,gid,eid,sid,SessionSave(revision=0,attendance_complete=True,roster_complete=True,rows=rows))
    assert [r["attendance"] for r in result["sessions"][0]["rows"]] == ["confirmed_absent","confirmed_absent"]
    with pytest.raises(ValueError, match="reload"):
        event_editor.save(path,gid,eid,sid,SessionSave(revision=0,rows=[]))
    with pytest.raises(LookupError):
        event_editor.read(path,"other",eid)
    assert event_editor.publish(path,gid,eid)["status"] == "published"
    with pytest.raises(ValueError,match="draft"):
        event_editor.save(path,gid,eid,sid,SessionSave(revision=1,rows=[]))


def test_session_http_save_contract(authenticated_client):
    client = authenticated_client
    gid = create_onboarded_group(client)["id"]
    aid = client.get(f"/api/v1/groups/{gid}/alliances").json()["items"][0]["id"]
    assert client.post(f"/api/v1/groups/{gid}/players", json={"fid":"bear-player","nickname":"Bear Player"}).status_code == 201
    eid = client.post(f"/api/v1/groups/{gid}/alliances/{aid}/events", json={"event_type":"bear_trap","occurred_on":"2026-11-15"}).json()["id"]
    root = f"/api/v1/groups/{gid}/events/{eid}"
    response = client.post(root+"/sessions", json={"session_key":"trap_1","started_at":"2026-11-15T17:00:00Z"})
    assert response.status_code == 201, response.text
    session = response.json()["sessions"][0]
    assert "event_id" not in session
    assert session["roster_complete"] is False
    sid = session["id"]
    payload = {key:value for key,value in session.items() if key not in ("id","session_key","started_at","host_alliance_id")}
    payload["rows"] = [{"fid":"bear-player","nickname":"Bear Player","metrics":{"damage":4500000000}}]
    saved = client.put(root+"/sessions/"+sid, json=payload)
    assert saved.status_code == 200, saved.text
    session = saved.json()["sessions"][0]
    assert session["rows"][0]["metrics"]["damage"] == 4500000000
    payload = {key:value for key,value in session.items() if key not in ("id","session_key","started_at","host_alliance_id")}
    assert client.put(root+"/sessions/"+sid, json=payload).status_code == 200
    assert client.get(root+"/editor").json()["sessions"][0]["revision"] == 2


def test_event_management_lifecycle(authenticated_client):
    client = authenticated_client
    gid = create_onboarded_group(client)["id"]
    aid = client.get(f"/api/v1/groups/{gid}/alliances").json()["items"][0]["id"]
    assert client.post(f"/api/v1/groups/{gid}/players",json={"fid":"p1","nickname":"Player"}).status_code == 201
    event = client.post(f"/api/v1/groups/{gid}/alliances/{aid}/events",json={"event_type":"alliance_championship","occurred_on":"2026-11-25"}).json()
    root = f"/api/v1/groups/{gid}/events/{event['id']}"
    sessions = client.get(root+"/editor").json()["sessions"]
    assert len(sessions)==1 and sessions[0]["session_key"]=="main"
    sid=sessions[0]["id"]
    assert client.post(root+"/manage",json={"action":"delete","confirmed":False}).status_code==409
    assert client.post(root+"/manage",json={"action":"date","confirmed":True,"occurred_on":"2026-11-26"}).status_code==200
    assert client.get(root).json()["occurred_on"]=="2026-11-26"
    session=client.get(root+"/editor").json()["sessions"][0]
    assert session["started_at"].startswith("2026-11-26")
    assert client.put(root+"/sessions/"+sid,json={"revision":session["revision"],"rows":[{"fid":"p1","nickname":"Player","registration":"registered"}]}).status_code==200
    assert client.post(root+"/manage",json={"action":"date","confirmed":True,"occurred_on":"2026-11-27"}).status_code==409
    assert client.post(root+"/publish").status_code==200
    assert client.post(root+"/manage",json={"action":"reopen","confirmed":True}).status_code==200
    assert client.get(root).json()["status"]=="draft"
    assert client.get(root+"/editor").json()["sessions"][0]["rows"][0]["fid"]=="p1"
    assert client.post(root+"/manage",json={"action":"delete","confirmed":True},headers={"X-CSRF-Token":"invalid"}).status_code==403
    assert client.post(root+"/manage",json={"action":"delete","confirmed":True}).status_code==200
    assert client.get(root).status_code==404
    assert client.get(f"/api/v1/groups/{gid}/players/p1").status_code==200


@pytest.mark.parametrize("kind", ["bear_trap", "foundry", "canyon"])
def test_finalize_complete_attendance(authenticated_client, settings, kind):
    from app.services.analytics import report
    from datetime import date
    c = authenticated_client
    gid = create_onboarded_group(c)["id"]
    aid = c.get(f"/api/v1/groups/{gid}/alliances").json()["items"][0]["id"]
    academy = c.post(f"/api/v1/groups/{gid}/alliances", json={"name":"Academy","tag":"ACA","state_id":"1001"}).json()["id"]
    roster = ["present","absent","excused","no-duty"]
    for fid in roster + ["visitor"]:
        assert c.post(f"/api/v1/groups/{gid}/players", json={"fid":fid,"nickname":fid}).status_code == 201
    eid = c.post(f"/api/v1/groups/{gid}/alliances/{aid}/events",json={"event_type":kind,"occurred_on":"2026-11-25"}).json()["id"]
    root = f"/api/v1/groups/{gid}/events/{eid}"
    keys = ["trap_1","trap_2","trap_3"] if kind=="bear_trap" else ["legion_1","legion_2"]
    revisions = {}
    for index,key in enumerate(keys):
        payload = {"session_key":key,"started_at":"2026-11-25T18:00:00Z"}
        if kind=="bear_trap" and index==2:
            payload["host_alliance_id"]=academy
        result = c.post(root+"/sessions",json=payload)
        assert result.status_code==201, result.text
        s = next(s for s in result.json()["sessions"] if s["session_key"]==key)
        rows = [{"fid":"visitor","nickname":"visitor","attendance":"confirmed_present"}]
        if index==len(keys)-1:
            rows.append({"fid":"present","nickname":"present","attendance":"confirmed_present","metrics":{"damage" if kind=="bear_trap" else "personal_points":100}})
        if kind!="bear_trap" and index==0:
            rows.append({"fid":"absent","nickname":"absent","registration":"registered","role":"main"})
        payload = {"revision":0,"rows":rows}
        if kind == "foundry":
            for row in rows:
                row["registration"] = "registered"
                row["role"] = "substitute" if row["fid"] == "absent" else "main"
                row["metrics"] = {"personal_points": 0 if row["fid"] == "absent" else 100}
            payload.update(registration_complete=True,results_complete=True)
        result = c.put(root+"/sessions/"+s["id"],json=payload)
        assert result.status_code==200,result.text
        revisions[s["id"]]=1
    if kind=="bear_trap":
        roster.append("academy-absent")
        assert c.post(f"/api/v1/groups/{gid}/players", json={"fid":"academy-absent","nickname":"academy-absent"}).status_code == 201
    review={"roster":roster,"excused":["excused"],"no_duty":["no-duty"],"expected_sessions":len(keys),"revisions":revisions}
    if kind=="bear_trap":
        assert c.post(root+"/publish",json=review).status_code==409
        review["home_alliances"]={**{f:aid for f in roster if f!="academy-absent"},"academy-absent":academy,"visitor":academy}
        assert c.post(root+"/publish",json={**review,"home_alliances":{**review["home_alliances"],"academy-absent":"outside"}}).status_code==409
    assert c.post(root+"/publish",json={**review,"expected_sessions":len(keys)+1}).status_code==409
    assert c.post(root+"/publish",json={**review,"revisions":{}}).status_code==409
    assert c.post(root+"/publish",json={**review,"excused":["present"]}).status_code==409
    assert c.post(root+"/publish",json={**review,"roster":roster+["outside-group"]}).status_code==409
    assert c.get(root+"/editor").json()["status"]=="draft"
    response=c.post(root+"/publish",json=review)
    assert response.status_code==200,response.text
    expected={"present":"positive","visitor":"positive","absent":"negative","excused":"excused","no-duty":"no_duty"}
    if kind=="bear_trap":
        expected["academy-absent"]="negative"
        scoped=report(settings.database_path,gid,academy,date(2026,11,25),date(2026,11,25))
        assert scoped["events"][0]["activity_cells"]=={"visitor":"positive","academy-absent":"negative"}
        assert scoped["events"][0]["metrics"]["attendance"]["rate"]==50
        combined=report(settings.database_path,gid,None,date(2026,11,25),date(2026,11,25))
        assert combined["events"][0]["metrics"]["attendance"]["known"]==4
    assert {r["fid"]:r["outcome"] for r in response.json()["completion"]}==expected
    data=report(settings.database_path,gid,aid,date(2026,11,25),date(2026,11,25))
    cells=data["events"][0]["activity_cells"]
    assert cells["present"]=="positive" and cells["absent"]==("no_show" if kind=="foundry" else "negative")
    assert cells["excused"]=="excused" and cells["no-duty"]=="excused"
    if kind!="bear_trap":
        assert data["events"][0]["metrics"]["no_shows"]==1
    personal=report(settings.database_path,gid,None,date(2026,11,25),date(2026,11,25),"absent")
    assert personal["players"][0]["history"][0]["cycle_attendance"]=="negative"
    assert c.post(root+"/manage",json={"action":"reopen","confirmed":True}).status_code==200
    reopened=c.get(root+"/editor").json()
    assert len(reopened["completion"])==len(expected)
    assert report(settings.database_path,gid,aid,date(2026,11,25),date(2026,11,25))["published_events"]==0
    review["revisions"]={s["id"]:s["revision"] for s in reopened["sessions"]}
    review["excused"]=["excused","absent"]
    response=c.post(root+"/publish",json=review)
    assert response.status_code==200,response.text
    assert next(r for r in response.json()["completion"] if r["fid"]=="absent")["outcome"]=="excused"
    assert c.post(root+"/manage",json={"action":"reopen","confirmed":True}).status_code==200
    assert c.post(root+"/publish").status_code==200
    assert c.get(root+"/editor").json()["completion"]==[]


def test_foundry_cycle_registration_and_zero_vs_missing(authenticated_client, settings):
    from app.services.analytics import report
    from datetime import date
    c = authenticated_client
    gid = create_onboarded_group(c)["id"]
    aid = c.get(f"/api/v1/groups/{gid}/alliances").json()["items"][0]["id"]
    roster = ["attended", "no-show", "unselected", "both"]
    for fid in roster:
        assert c.post(f"/api/v1/groups/{gid}/players", json={"fid":fid,"nickname":fid}).status_code == 201
    eid = c.post(f"/api/v1/groups/{gid}/alliances/{aid}/events", json={"event_type":"foundry","occurred_on":"2026-11-29"}).json()["id"]
    root = f"/api/v1/groups/{gid}/events/{eid}"
    def row(fid, score, role="main"):
        return {"fid":fid,"nickname":fid,"registration":"registered","role":role,
                "attendance":"confirmed_present","metrics":{} if score is None else {"personal_points":score}}
    ids = []
    for key in ("legion_1","legion_2"):
        result = c.post(root+"/sessions", json={"session_key":key,"started_at":"2026-11-29T18:00:00Z"})
        assert result.status_code==201
        ids.append(next(s["id"] for s in result.json()["sessions"] if s["session_key"]==key))
    l1 = [row("no-show",0,"substitute"),row("both",0)]
    l2 = [row("attended",100),row("both",200)]
    def save(sid, revision, rows, complete=True):
        return c.put(root+"/sessions/"+sid,json={"revision":revision,"rows":rows,"registration_complete":True,"results_complete":complete})
    assert save(ids[0],0,l1,False).status_code==200
    assert save(ids[1],0,[row("attended",None),row("both",200)]).status_code==200
    review={"roster":roster,"expected_sessions":2,"revisions":dict.fromkeys(ids,1)}
    assert c.post(root+"/publish",json=review).status_code==409
    assert save(ids[0],1,l1).status_code==200
    review["revisions"][ids[0]]=2
    assert c.post(root+"/publish",json=review).status_code==409
    assert save(ids[1],1,l2).status_code==200
    review["revisions"][ids[1]]=2
    assert c.post(root+"/publish",json=review).status_code==200
    data=report(settings.database_path,gid,aid,date(2026,11,29),date(2026,11,29))
    event=data["events"][0]
    assert event["activity_cells"]=={"attended":"positive","both":"positive","no-show":"no_show","unselected":"not_registered"}
    assert event["metrics"]["registration"]["positive"]==3
    assert event["metrics"]["registration"]["negative"]==1
    assert event["metrics"]["attendance"]["rate"]==50
    assert event["metrics"]["no_shows"]==2
    assert event["metrics"]["missed_unregistered"]==1
    assert event["metrics"]["missed_registered"]==1
