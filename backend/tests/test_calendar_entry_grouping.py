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

def test_grouped_bear_finalization_requires_all_planned_sessions(authenticated_client,settings):
    from app.services.analytics import report
    from datetime import date
    c=authenticated_client
    root,aid=setup(c)
    for fid in ("present","absent"):
        assert c.post(root+"/players",json={"fid":fid,"nickname":fid}).status_code==201
    urls=[]
    for n in range(1,4):
        row=c.post(root+"/calendar",json={"event_type":"bear_trap","scope":"alliance",
            "alliance_id":aid,"state_id":"1001","starts_at":f"2090-06-01T1{n}:00Z",
            "precision":"minute","phase":f"Trap {n}"}).json()["items"][0]
        urls.append(root+"/calendar/"+row["id"])
    for n in (1,2):
        assert c.put(urls[n-1]+"/entry-group",json={"revision":1,"cycle_date":"2090-06-01","session_key":f"trap_{n}"}).status_code==200
    first=c.post(urls[0]+"/start-entry",json={"revision":2,"confirmed":True}).json()["linked"]
    event=root+"/events/"+first["id"]
    def save(link):
        response=c.put(event+"/sessions/"+link["session_id"],json={"revision":0,"rows":[{"fid":"present","nickname":"present","attendance":"confirmed_present","metrics":{"damage":100}}]})
        assert response.status_code==200,response.text
    save(first)
    review={"roster":["present","absent"],"home_alliances":{"present":aid,"absent":aid},"expected_sessions":1,"revisions":{first["session_id"]:1}}
    response=c.post(event+"/publish",json=review)
    assert response.status_code==409,response.text
    assert "planned cycle sessions" in response.text
    assert c.post(event+"/publish?bear_cycle_complete=true").status_code==409
    assert c.post(event+"/publish").status_code==200
    gid=root.rsplit("/",1)[1]
    result=report(settings.database_path,gid,None,date(2090,6,1),date(2090,6,1))
    assert result["events"][0]["activity_cells"]=={"present":"positive"}
    assert c.post(event+"/manage",json={"action":"reopen","confirmed":True}).status_code==200
    second=c.post(urls[1]+"/start-entry",json={"revision":2,"confirmed":True}).json()["linked"]
    save(second)
    review.update(expected_sessions=2,revisions={first["session_id"]:2,second["session_id"]:1})
    response=c.post(event+"/publish",json=review)
    assert response.status_code==200,response.text
    assert c.put(urls[2]+"/entry-group",json={"revision":1,"cycle_date":"2090-06-01","session_key":"trap_3"}).status_code==409
    assert c.put(urls[0]+"/event-link",json={"revision":3,"event_id":None}).status_code==409
    assert c.post(event+"/manage",json={"action":"reopen","confirmed":True}).status_code==200
    assert c.put(urls[2]+"/entry-group",json={"revision":1,"cycle_date":"2090-06-01","session_key":"trap_3"}).status_code==200
    assert c.post(event+"/manage",json={"action":"delete_session","confirmed":True,"session_id":second["session_id"]}).status_code==200
    assert c.get(urls[1]+"/event-link").json()["revision"]==4
