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


def test_calendar_idempotent_creation(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    payload={"event_type":"bear_trap","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-02-28T15:00Z","precision":"minute","interval_minutes":2850,"occurrence_count":3,"request_key":"request-test-000001"}
    first=c.post(url,json=payload)
    assert first.status_code==201
    assert c.post(url,json=payload).json()==first.json()
    assert c.post(url,json={**payload,"occurrence_count":4}).status_code==409
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM calendar_occurrences").fetchone()[0]==3
        assert db.execute("SELECT COUNT(*) FROM calendar_series").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM audit_log WHERE entity_type='calendar_occurrence'").fetchone()[0]==3


def test_calendar_future_changes_preserve_exceptions(authenticated_client):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    payload={"event_type":"bear_trap","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-02-28T15:00Z","precision":"minute","interval_minutes":2880,"occurrence_count":5}
    response=c.post(url,json=payload)
    assert response.status_code==201,response.text
    rows=response.json()["items"]
    edit={k:v for k,v in payload.items() if k not in ("interval_minutes","occurrence_count")}
    assert c.put(url+"/"+rows[2]["id"],json={**edit,"starts_at":"2090-03-04T18:00Z","revision":1}).status_code==200
    target=url+"/"+rows[1]["id"]+"/future"
    preview=c.get(target).json()["items"]
    assert [r["id"] for r in preview]==[rows[i]["id"] for i in (1,3,4)]
    revisions={r["id"]:r["revision"] for r in preview}
    result=c.post(target,json={"action":"shift","shift_minutes":60,"revisions":revisions})
    assert result.status_code==200,result.text
    assert result.json()["items"][0]["starts_at"]=="2090-03-02T16:00Z"
    assert c.post(target,json={"action":"shift","shift_minutes":60,"revisions":revisions}).status_code==409
    current=c.get(target).json()["items"]
    result=c.post(target,json={"action":"cancel","revisions":{r["id"]:r["revision"] for r in current}})
    assert result.status_code==200
    assert all(r["schedule_status"]=="cancelled" for r in result.json()["items"])
    all_rows=c.get(url+"?start=2090-02-28&end=2090-03-10").json()["items"]
    assert all_rows[0]==rows[0]
    assert all_rows[2]["starts_at"]=="2090-03-04T18:00Z"
    assert all_rows[2]["schedule_status"]=="scheduled"


def test_forecast_does_not_duplicate_existing_or_cancelled_entries(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    payload={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-03-01","precision":"date","interval_minutes":20160,"occurrence_count":3,"reject_existing":True,"request_key":"forecast-request-0001"}
    first=c.post(url,json=payload)
    assert first.status_code==201,first.text
    assert c.post(url,json=payload).json()==first.json()
    assert c.post(url,json={**payload,"request_key":"forecast-request-0002"}).status_code==409
    row=first.json()["items"][1]
    edit={k:v for k,v in payload.items() if k not in ("interval_minutes","occurrence_count","reject_existing","request_key")}
    assert c.put(url+"/"+row["id"],json={**edit,"starts_at":row["starts_at"],"revision":1,"schedule_status":"cancelled"}).status_code==200
    assert c.post(url,json={**payload,"starts_at":"2090-03-15","request_key":"forecast-request-0003"}).status_code==409
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM calendar_occurrences").fetchone()[0]==3
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0

def test_advanced_calendar_rules_and_catalog_types(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    payload={"event_type":"game:lucky-wheel","scope":"state","state_id":"1001","starts_at":"2092-01-31","ends_at":"2092-02-02","precision":"date","repeat_months":1,"occurrence_count":4,"reject_existing":True}
    result=c.post(url,json=payload)
    assert result.status_code==201,result.text
    rows=result.json()["items"]
    assert [r["starts_at"] for r in rows]==["2092-01-31","2092-02-29","2092-03-31","2092-04-30"]
    assert [r["ends_at"] for r in rows]==["2092-02-02","2092-03-02","2092-04-02","2092-05-02"]
    assert all(r["series_id"]==rows[0]["series_id"] for r in rows)
    assert c.post(url,json={**payload,"event_type":"game:unknown"}).status_code==422
    assert c.post(url,json={**payload,"interval_minutes":1440}).status_code==422
    assert c.post(url,json={**payload,"occurrence_count":15}).status_code==422
    weekly={**payload,"event_type":"game:crazy-joe","starts_at":"2092-01-01","ends_at":None,"repeat_months":None,"repeat_weekdays":[1,3],"occurrence_count":4}
    # Jan 1 2092 is Tuesday.
    r=c.post(url,json=weekly)
    assert r.status_code==201,r.text
    assert [x["starts_at"] for x in r.json()["items"]]==["2092-01-01","2092-01-03","2092-01-08","2092-01-10"]
    assert c.post(url,json={**weekly,"repeat_weekdays":[0]}).status_code==422

def test_linked_cycle_atomic_idempotent_and_scoped(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar/cycles"
    common={"event_type":"canyon","scope":"alliance","alliance_id":aid,"state_id":"1001","precision":"date","confidence":"estimated"}
    phases=[{**common,"phase":phase,"starts_at":start,"ends_at":end} for phase,start,end in [
        ("Voting","2090-03-06","2090-03-08"),("Registration","2090-03-08","2090-03-10"),
        ("Matchmaking","2090-03-10","2090-03-11"),("Battle","2090-03-11",None)]]
    payload={"kind":"canyon","request_key":"cycle-request-000001","phases":phases}
    response=c.post(url,json=payload)
    assert response.status_code==201,response.text
    rows=response.json()["items"]
    assert len({r["cycle_id"] for r in rows})==1
    assert rows[-1]["precision"]=="date" and rows[-1]["ends_at"] is None
    assert c.post(url,json=payload).json()==response.json()
    assert c.get(url+"/"+rows[0]["cycle_id"]).json()["items"]==rows
    assert c.post(url,json={**payload,"request_key":"cycle-request-000002"}).status_code==409
    assert c.post(url,json={**payload,"phases":phases[::-1]}).status_code==422
    assert c.put(root+"/calendar/"+rows[0]["id"],json={**phases[0],"revision":1,"phase":"Battle"}).status_code==409
    assert c.put(root+"/calendar/"+rows[0]["id"],json={**phases[0],"revision":1,"ends_at":"2090-03-09"}).status_code==409
    assert c.get("/api/v1/groups/missing/calendar/cycles/"+rows[0]["cycle_id"]).status_code==404
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM calendar_cycles").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM calendar_occurrences").fetchone()[0]==4
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
    c.headers.pop("X-CSRF-Token")
    assert c.post(url,json=payload).status_code==403

def test_series_shift_collision_is_atomic(authenticated_client):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    base={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","precision":"date","starts_at":"2090-05-01"}
    original=c.post(url,json={**base,"occurrence_count":3,"interval_minutes":1440}).json()["items"]
    existing=c.post(url,json={**base,"starts_at":"2090-05-04"}).json()["items"][0]
    assert c.put(url+"/"+existing["id"],json={**base,"starts_at":"2090-05-04","revision":1,"schedule_status":"cancelled"}).status_code==200
    target=url+"/"+original[0]["id"]+"/future"
    preview=c.get(target).json()["items"]
    result=c.post(target,json={"action":"shift","shift_minutes":1440,"revisions":{r["id"]:r["revision"] for r in preview}})
    assert result.status_code==409,result.text
    assert c.get(target).json()["items"]==preview
    result=c.post(target,json={"action":"shift","shift_minutes":14400,"revisions":{r["id"]:r["revision"] for r in preview}})
    assert result.status_code==200,result.text


def test_rolling_calendar_renewal_preserves_overrides_and_stops(authenticated_client,settings):
    from datetime import datetime,timezone
    from app.services.calendar import renew_schedules
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    fields={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","precision":"date","starts_at":"2090-05-01"}
    payload={**fields,"occurrence_count":2,"interval_minutes":20160,"reject_existing":True,"rolling":True,"request_key":"rolling-request-0001"}
    response=c.post(url,json=payload)
    assert response.status_code==201,response.text
    rows=response.json()["items"]
    assert c.post(url,json=payload).json()==response.json()
    assert c.put(url+"/"+rows[1]["id"],json={**fields,"starts_at":"2090-05-16","revision":1,"schedule_status":"cancelled"}).status_code==200
    now=datetime(2090,5,20,tzinfo=timezone.utc)
    assert renew_schedules(settings.database_path,now)==4
    assert renew_schedules(settings.database_path,now)==0
    result=c.get(url+"?start=2090-05-01&end=2090-08-01").json()["items"]
    assert [r["starts_at"] for r in result]==["2090-05-01","2090-05-16","2090-05-29","2090-06-12","2090-06-26","2090-07-10"]
    assert result[1]["schedule_status"]=="cancelled"
    assert all(r["rolling_status"]=="active" for r in result)
    assert all(r["confidence"]=="estimated" for r in result[2:])
    target=url+"/"+result[2]["id"]+"/future"
    preview=c.get(target).json()["items"]
    assert c.post(target,json={"action":"cancel","revisions":{r["id"]:r["revision"] for r in preview}}).status_code==200
    assert renew_schedules(settings.database_path,datetime(2090,8,1,tzinfo=timezone.utc))==0
    assert all(r["rolling_status"]=="stopped" for r in c.get(url+"?start=2090-05-01&end=2090-08-01").json()["items"])
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0


def test_rolling_calendar_collision_pauses_without_overwriting(authenticated_client,settings):
    from datetime import datetime,timezone
    from app.services.calendar import renew_schedules
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    fields={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","precision":"date","starts_at":"2090-05-01"}
    assert c.post(url,json={**fields,"occurrence_count":2,"interval_minutes":20160,"rolling":True,"reject_existing":True}).status_code==201
    existing=c.post(url,json={**fields,"starts_at":"2090-05-29"}).json()["items"][0]
    assert renew_schedules(settings.database_path,datetime(2090,5,20,tzinfo=timezone.utc))==0
    result=c.get(url+"?start=2090-05-01&end=2090-07-01").json()["items"]
    assert len(result)==3 and result[-1]==existing
    assert result[0]["rolling_status"]=="conflict"


def test_edit_recurring_schedule_keeps_manual_exception_and_updates_cursor(authenticated_client,settings):
    from datetime import datetime,timezone
    from app.services.calendar import renew_schedules
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    fields={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-05-01T15:00Z","ends_at":"2090-05-01T16:00Z","precision":"minute"}
    response=c.post(url,json={**fields,"interval_minutes":20160,"occurrence_count":4,"rolling":True,"reject_existing":True})
    assert response.status_code==201,response.text
    rows=response.json()["items"]
    assert c.put(url+"/"+rows[2]["id"],json={**fields,"starts_at":"2090-05-29T18:00Z","ends_at":"2090-05-29T19:00Z","revision":1}).status_code==200
    target=url+"/"+rows[1]["id"]+"/future"
    preview=c.get(target).json()["items"]
    assert [r["id"] for r in preview]==[rows[1]["id"],rows[3]["id"]]
    result=c.post(target,json={"action":"edit","schedule":{**fields,"starts_at":"2090-05-15T17:00Z","ends_at":"2090-05-15T19:00Z","revision":1},"interval_minutes":20160,"revisions":{r["id"]:r["revision"] for r in preview}})
    assert result.status_code==200,result.text
    assert [r["starts_at"] for r in result.json()["items"]]==["2090-05-15T17:00Z","2090-06-12T17:00Z"]
    assert [r["ends_at"] for r in result.json()["items"]]==["2090-05-15T19:00Z","2090-06-12T19:00Z"]
    items=c.get(url+"?start=2090-05-01&end=2090-06-14").json()["items"]
    assert items[0]["starts_at"]==fields["starts_at"] and items[2]["starts_at"]=="2090-05-29T18:00Z"
    assert renew_schedules(settings.database_path,datetime(2090,6,13,tzinfo=timezone.utc))>0
    next_row=c.get(url+"?start=2090-06-26&end=2090-06-27").json()["items"][0]
    assert (next_row["starts_at"],next_row["ends_at"])==("2090-06-26T17:00Z","2090-06-26T19:00Z")


def test_repeated_canyon_cycles_are_atomic_and_future_battle_time_unknown(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar/cycles"
    common={"event_type":"canyon","scope":"alliance","alliance_id":aid,"state_id":"1001","precision":"date","confidence":"confirmed"}
    phases=[{**common,"phase":phase,"starts_at":start,"ends_at":end} for phase,start,end in [
        ("Voting","2090-03-06","2090-03-08"),("Registration","2090-03-08","2090-03-10"),
        ("Matchmaking","2090-03-10","2090-03-11"),("Battle","2090-03-11",None)]]
    phases[-1].update(precision="minute",starts_at="2090-03-11T15:00Z",ends_at="2090-03-11T16:00Z")
    payload={"kind":"canyon","request_key":"repeat-cycle-000001","phases":phases,"occurrence_count":3,"interval_days":28}
    response=c.post(url,json=payload)
    assert response.status_code==201,response.text
    rows=response.json()["items"]
    assert len(rows)==12 and len({r["cycle_id"] for r in rows})==3
    assert rows[7]["starts_at"]=="2090-04-08" and rows[7]["ends_at"] is None
    assert all(r["confidence"]=="estimated" for r in rows[4:])
    assert c.post(url,json=payload).json()==response.json()
    assert c.post(url,json={**payload,"request_key":"repeat-cycle-000002"}).status_code==409
    assert c.post(url,json={**payload,"interval_days":4}).status_code==422
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM calendar_cycles").fetchone()[0]==3
        assert db.execute("SELECT COUNT(*) FROM calendar_occurrences").fetchone()[0]==12
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0


def test_foundry_linked_legions_share_one_result_identity(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar/cycles"
    common={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","precision":"date","confidence":"estimated"}
    phases=[{**common,"phase":phase,"starts_at":start,"ends_at":end} for phase,start,end in [
        ("Voting","2090-03-06","2090-03-08"),("Registration","2090-03-08","2090-03-10"),
        ("Matchmaking","2090-03-10","2090-03-12"),("Legion 1","2090-03-12",None),("Legion 2","2090-03-12",None)]]
    payload={"kind":"foundry","request_key":"foundry-cycle-000001","phases":phases,"occurrence_count":2,"interval_days":14}
    response=c.post(url,json=payload)
    assert response.status_code==201,response.text
    rows=response.json()["items"]
    assert len(rows)==10 and len({r["cycle_id"] for r in rows})==2
    assert rows[3]["entry_cycle_date"]==rows[4]["entry_cycle_date"]=="2090-03-12"
    assert [r["entry_session_key"] for r in rows[3:5]]==["legion_1","legion_2"]
    assert c.post(url,json=payload).json()==response.json()
    assert c.post(url,json={**payload,"request_key":"foundry-cycle-000002"}).status_code==409
    for i,clock in ((3,"19:00"),(4,"14:00")):
        row=rows[i]
        change={**phases[i],"precision":"minute","starts_at":"2090-03-12T"+clock+"Z","confidence":"confirmed","revision":row["revision"]}
        result=c.put(root+"/calendar/"+row["id"],json=change)
        assert result.status_code==200,result.text
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
    assert c.post(root+"/calendar/"+rows[0]["id"]+"/start-entry",json={"revision":1,"confirmed":True}).status_code==409
    first=c.post(root+"/calendar/"+rows[3]["id"]+"/start-entry",json={"revision":2,"confirmed":True})
    second=c.post(root+"/calendar/"+rows[4]["id"]+"/start-entry",json={"revision":2,"confirmed":True})
    assert first.status_code==second.status_code==200,(first.text,second.text)
    assert first.json()["linked"]["id"]==second.json()["linked"]["id"]
    assert first.json()["linked"]["session_id"]!=second.json()["linked"]["session_id"]
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM event_sessions").fetchone()[0]==2
