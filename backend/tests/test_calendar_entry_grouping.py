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


def test_auto_bear_groups_cross_midnight_and_renews(authenticated_client,settings):
    from datetime import datetime,timezone
    from app.services.calendar import renew_schedules,missing_bear_forecasts
    c=authenticated_client
    root,aid=setup(c)
    academy=c.post(root+"/alliances",json={"name":"Academy","tag":"ACA","state_id":"1001"}).json()["id"]
    url=root+"/calendar"
    base={"event_type":"bear_trap","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01T23:30Z","precision":"minute","phase":"Trap 1","interval_minutes":2850,"occurrence_count":2,"rolling":True,"reject_existing":True,"bear_cycle_anchor":"2090-06-01T23:30Z","bear_session_key":"trap_1"}
    first=c.post(url,json=base)
    assert first.status_code==201,first.text
    rows=first.json()["items"]
    second=c.post(url,json={**base,"alliance_id":academy,"starts_at":"2090-06-02T00:30Z","bear_session_key":"trap_2"})
    assert second.status_code==201,second.text
    assert [r["entry_cycle_date"] for r in rows]==["2090-06-01","2090-06-03"]
    assert [r["entry_cycle_date"] for r in second.json()["items"]]==["2090-06-01","2090-06-03"]
    assert c.post(url,json={**base,"alliance_id":academy,"starts_at":"2090-06-02T02:00Z"}).status_code==409
    assert c.post(url,json={**base,"alliance_id":academy,"starts_at":"2090-06-02T02:00Z","bear_session_key":"trap_3","bear_cycle_anchor":"2090-06-01T23:00Z"}).status_code==409
    assert c.post(url,json={**base,"bear_cycle_anchor":None}).status_code==422
    with connection(settings.database_path) as db:
        assert missing_bear_forecasts(db,root.rsplit("/",1)[1],"2090-06-05")==["trap_1","trap_2"]
    now=datetime(2090,6,4,tzinfo=timezone.utc)
    assert renew_schedules(settings.database_path,now)>0
    assert renew_schedules(settings.database_path,now)==0
    result=c.get(url+"?start=2090-06-05&end=2090-06-07").json()["items"]
    assert len(result)==2 and {r["entry_cycle_date"] for r in result}=={"2090-06-05"}
    assert {r["entry_session_key"] for r in result}=={"trap_1","trap_2"}
    with connection(settings.database_path) as db:
        assert missing_bear_forecasts(db,root.rsplit("/",1)[1],"2090-06-05")==[]
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
    target=url+"/"+rows[0]["id"]+"/future"
    preview=c.get(target).json()["items"]
    revisions={r["id"]:r["revision"] for r in preview}
    assert c.post(target,json={"action":"shift","shift_minutes":60,"revisions":revisions}).status_code==409
    response=c.post(target,json={"action":"cancel","revisions":revisions})
    assert response.status_code==200,response.text
    assert all(r["schedule_status"]=="cancelled" for r in response.json()["items"])
    with connection(settings.database_path) as db:
        assert db.execute("SELECT status FROM calendar_rolling_series WHERE series_id=?",(rows[0]["series_id"],)).fetchone()[0]=="stopped"


def test_edit_grouped_bear_single_and_future_preserves_shared_cycles(authenticated_client,settings):
    from datetime import datetime,timezone
    from app.services.calendar import renew_schedules
    c=authenticated_client
    root,aid=setup(c)
    academy=c.post(root+"/alliances",json={"name":"Academy","tag":"ACA","state_id":"1001"}).json()["id"]
    url=root+"/calendar"
    fields={"event_type":"bear_trap","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01T15:00Z","ends_at":"2090-06-01T15:30Z","precision":"minute","phase":"Trap 1"}
    config={"interval_minutes":2880,"occurrence_count":3,"rolling":True,"reject_existing":True,"bear_cycle_anchor":"2090-06-01T15:00Z","bear_session_key":"trap_1"}
    response=c.post(url,json={**fields,**config})
    assert response.status_code==201,response.text
    rows=response.json()["items"]
    response=c.post(url,json={**fields,**config,"alliance_id":academy,"starts_at":"2090-06-01T17:00Z","ends_at":"2090-06-01T17:30Z","phase":"Trap 2","bear_session_key":"trap_2"})
    assert response.status_code==201,response.text
    other=response.json()["items"]
    single=c.put(url+"/"+rows[0]["id"],json={**fields,"starts_at":"2090-06-01T14:00Z","ends_at":"2090-06-01T14:30Z","revision":1})
    assert single.status_code==200,single.text
    assert single.json()["entry_cycle_date"]=="2090-06-01"
    assert single.json()["entry_session_key"]=="trap_1"
    before=c.get(url+"?start=2090-06-01&end=2090-06-07").json()["items"]
    assert next(r for r in before if r["id"]==rows[1]["id"])["starts_at"]=="2090-06-03T15:00Z"
    target=url+"/"+rows[1]["id"]+"/future"
    preview=c.get(target).json()
    assert preview["interval_minutes"]==2880
    revisions={r["id"]:r["revision"] for r in preview["items"]}
    edit={**fields,"starts_at":"2090-06-03T13:00Z","ends_at":"2090-06-03T13:30Z","revision":1}
    change={"action":"edit","schedule":edit,"interval_minutes":2880,"revisions":revisions}
    incompatible=c.post(target,json={**change,"interval_minutes":2850})
    assert incompatible.status_code==409,incompatible.text
    assert c.get(target).json()==preview
    saved=c.post(target,json=change)
    assert saved.status_code==200,saved.text
    assert [r["starts_at"] for r in saved.json()["items"]]==["2090-06-03T13:00Z","2090-06-05T13:00Z"]
    assert [r["entry_cycle_date"] for r in saved.json()["items"]]==["2090-06-03","2090-06-05"]
    assert c.post(target,json=change).status_code==409
    after=c.get(url+"?start=2090-06-01&end=2090-06-07").json()["items"]
    assert next(r for r in after if r["id"]==rows[0]["id"])["starts_at"]=="2090-06-01T14:00Z"
    for peer in other:
        assert next(r for r in after if r["id"]==peer["id"])["starts_at"]==peer["starts_at"]
    assert renew_schedules(settings.database_path,datetime(2090,6,6,tzinfo=timezone.utc))>0
    next_cycle=c.get(url+"?start=2090-06-07&end=2090-06-08").json()["items"]
    assert [(r["starts_at"],r["entry_cycle_date"],r["entry_session_key"]) for r in next_cycle]==[
        ("2090-06-07T13:00Z","2090-06-07","trap_1"),("2090-06-07T17:00Z","2090-06-07","trap_2")]
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0


def test_lone_grouped_bear_cadence_edit_splits_series_and_renews(authenticated_client,settings):
    from datetime import datetime,timezone
    from app.services.calendar import renew_schedules,missing_bear_forecasts
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    fields={"event_type":"bear_trap","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01T15:00Z","precision":"minute","phase":"Trap 1"}
    response=c.post(url,json={**fields,"interval_minutes":2880,"occurrence_count":4,"rolling":True,"reject_existing":True,"bear_cycle_anchor":"2090-06-01T15:00Z","bear_session_key":"trap_1"})
    assert response.status_code==201,response.text
    rows=response.json()["items"]
    target=url+"/"+rows[1]["id"]+"/future"
    preview=c.get(target).json()["items"]
    edit={**fields,"starts_at":"2090-06-03T17:00Z","revision":1}
    result=c.post(target,json={"action":"edit","schedule":edit,"interval_minutes":2850,"revisions":{r["id"]:r["revision"] for r in preview}})
    assert result.status_code==200,result.text
    new=result.json()["items"]
    assert [r["id"] for r in new]==[r["id"] for r in rows[1:]]
    assert [r["starts_at"] for r in new]==["2090-06-03T17:00Z","2090-06-05T16:30Z","2090-06-07T16:00Z"]
    assert len({r["series_id"] for r in new})==1 and new[0]["series_id"]!=rows[0]["series_id"]
    assert [r["sequence"] for r in new]==[0,1,2]
    old=c.get(url+"?start=2090-06-01&end=2090-06-02").json()["items"][0]
    assert {k:old[k] for k in rows[0]}==rows[0]
    assert renew_schedules(settings.database_path,datetime(2090,6,8,tzinfo=timezone.utc))>0
    upcoming=c.get(url+"?start=2090-06-09&end=2090-06-10").json()["items"]
    assert len(upcoming)==1 and upcoming[0]["starts_at"]=="2090-06-09T15:30Z"
    assert upcoming[0]["entry_cycle_date"]=="2090-06-09"
    with connection(settings.database_path) as db:
        assert missing_bear_forecasts(db,root.rsplit("/",1)[1],"2090-06-09")==[]
