from datetime import date
from app.services import analytics, event_editor
from app.services.event_editor import SessionCreate, SessionSave
from test_api import create_onboarded_group

def test_published_analytics_scope_and_bear_cycles(authenticated_client,settings):
    c=authenticated_client
    gid=create_onboarded_group(c)["id"]
    aid=c.get(f"/api/v1/groups/{gid}/alliances").json()["items"][0]["id"]
    for fid in ("present","absent","partial","unknown"):
        assert c.post(f"/api/v1/groups/{gid}/players",json={"fid":fid,"nickname":fid}).status_code==201
    root=f"/api/v1/groups/{gid}/alliances/{aid}"
    eid=c.post(root+"/events",json={"event_type":"bear_trap","occurred_on":"2026-11-25"}).json()["id"]
    for key in ("trap_1","trap_2"):
        session=event_editor.create_session(settings.database_path,gid,eid,SessionCreate(session_key=key,started_at="2026-11-25T18:00:00Z"))
        sid=next(s["id"] for s in session["sessions"] if s["session_key"]==key)
        rows=[{"fid":"present","nickname":"present","eligibility":"confirmed","attendance":"confirmed_present","metrics":{"damage":4500000000}},
              {"fid":"absent","nickname":"absent","eligibility":"confirmed","attendance":"confirmed_absent"},
              {"fid":"unknown","nickname":"unknown","eligibility":"unknown"}]
        if key=="trap_1":
            rows.append({"fid":"partial","nickname":"partial","eligibility":"confirmed","attendance":"confirmed_absent"})
        event_editor.save(settings.database_path,gid,eid,sid,SessionSave(revision=0,roster_complete=True,attendance_complete=True,rows=rows))
    url=root+"/analytics?start=2026-11-01&end=2026-11-30"
    from app.database import transaction
    with transaction(settings.database_path) as db:
        for fid in ("present","absent","partial","unknown"):
            db.execute("INSERT INTO player_primary_alliance_history(player_fid,group_id,alliance_id,effective_observed_at,source_type) VALUES (?,?,?,?,?)",(fid,gid,aid,"2026-11-01T00:00:00Z","manual"))
    assert c.get(url).json()["published_events"]==0
    published=event_editor.publish(settings.database_path,gid,eid,True)
    assert published["bear_cycle_complete"] is True
    r=c.get(url)
    assert r.status_code==200,r.text
    result=r.json()
    assert result["events"][0]["metrics"]["attendance"]=={"positive":1,"negative":1,"excused":0,"unknown":2,"known":2,"eligible_unknown":2,"rate":50.0}
    assert result["events"][0]["metrics"]["damage"]["total"]=="9000000000"
    assert result["events"][0]["activity_cells"]=={"present":"positive","absent":"negative","partial":"unknown","unknown":"unknown"}
    p=c.get(f"/api/v1/groups/{gid}/players/present/activity?start=2026-11-01&end=2026-11-30").json()
    assert len(p["players"][0]["history"])==1
    assert p["players"][0]["metrics"]["bear_trap"]["attendance"]["positive"]==1
    assert c.get(root+"/analytics?start=2025-01-01&end=2026-11-30").status_code==422
    assert c.get(f"/api/v1/groups/other/alliances/{aid}/analytics?start=2026-11-01&end=2026-11-30").status_code==404
    event_editor.manage_event(settings.database_path,gid,eid,"reopen",True)
    assert event_editor.read(settings.database_path,gid,eid)["bear_cycle_complete"] is False
    assert c.get(url).json()["published_events"]==0
    event_editor.publish(settings.database_path,gid,eid)
    assert c.get(url).json()["events"][0]["metrics"]["attendance"]["negative"]==0

def test_known_registration_and_substitute_reliability():
    session={"roster_complete":True,"registration_complete":True,"attendance_complete":True}
    row={"eligibility":"unknown","registration":"registered","attendance":"unknown"}
    assert analytics.registration(row,session)=="positive"
    assert analytics.attendance(row,session)=="unknown"
    row.update(eligibility="confirmed",attendance="confirmed_absent")
    e={"sessions":[{"registration_outcome":analytics.registration(row,session),"attendance_outcome":analytics.attendance(row,session),"role":"substitute","metrics":{}}]}
    result=analytics.aggregate([e],"foundry")
    assert result["no_shows"]==1
    assert result["reliability"]["rate"]==0
    assert result["personal_points"]["total"] is None
    assert analytics.counts([])["rate"] is None

def test_unauthenticated_analytics(client):
    assert client.get("/api/v1/groups/g/alliances/a/analytics?start=2026-11-01&end=2026-11-30").status_code==401


def test_academy_host_and_incomplete_cycle(authenticated_client,settings):
    c=authenticated_client
    gid=create_onboarded_group(c)["id"]
    aid=c.get(f"/api/v1/groups/{gid}/alliances").json()["items"][0]["id"]
    academy=c.post(f"/api/v1/groups/{gid}/alliances",json={"name":"Academy","tag":"ACA","state_id":"1001"}).json()["id"]
    assert c.post(f"/api/v1/groups/{gid}/players",json={"fid":"visitor","nickname":"Visitor"}).status_code==201
    from app.database import transaction
    with transaction(settings.database_path) as db:
        db.execute("INSERT INTO player_primary_alliance_history(player_fid,group_id,alliance_id,effective_observed_at,source_type) VALUES (?,?,?,?,?)",("visitor",gid,aid,"2026-11-01T00:00:00Z","manual"))
    root=f"/api/v1/groups/{gid}/alliances/{aid}"
    eid=c.post(root+"/events",json={"event_type":"bear_trap","occurred_on":"2026-11-25"}).json()["id"]
    s=event_editor.create_session(settings.database_path,gid,eid,SessionCreate(session_key="trap_3",started_at="2026-11-25T18:00:00Z",host_alliance_id=academy))["sessions"][0]
    assert s["host_alliance_id"]==academy
    event_editor.save(settings.database_path,gid,eid,s["id"],SessionSave(revision=0,rows=[{"fid":"visitor","nickname":"Visitor","attendance":"confirmed_present","metrics":{"damage":100}}]))
    event_editor.publish(settings.database_path,gid,eid)
    report=c.get(root+"/analytics?start=2026-11-01&end=2026-11-30").json()
    assert report["events"][0]["metrics"]["attendance"]["positive"]==1
    assert report["events"][0]["evidence"][0]["host_alliance_id"]==academy
    assert analytics.bear_cycle([{"session_key":"trap_1","attendance_outcome":"negative"}],["trap_1"],False)=="unknown"
    assert analytics.bear_cycle([{"session_key":"trap_1","attendance_outcome":"negative"}],["trap_1","trap_3"],True)=="unknown"
