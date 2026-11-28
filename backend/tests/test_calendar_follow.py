from app.database import connection
from test_calendar import setup


def test_flame_follows_svs_moves_and_renewed_cycles(authenticated_client,settings):
    c=authenticated_client
    root,_=setup(c)
    url=root+"/calendar"
    rule={"event_type":"game:flame-and-fang","state_id":"1001","starts_on":"2090-03-01"}
    assert c.get(url+"/follow",params=rule).json()["items"]==[]
    plan=c.post(url+"/follow",json=rule)
    assert plan.status_code==200,plan.text
    rid=plan.json()["active_rule_id"]
    assert c.post(url+"/follow",json=rule).json()["active_rule_id"]==rid
    fields={"event_type":"svs_preparation","scope":"state","state_id":"1001","alliance_id":None,
        "starts_at":"2090-03-06","ends_at":"2090-03-11","precision":"date","confidence":"estimated"}
    battle={**fields,"event_type":"svs_battle","phase":"Battle","starts_at":"2090-03-11","ends_at":None}
    first=c.post(url+"/cycles",json={"kind":"svs","request_key":"follow-cycle-000001","phases":[{**fields,"phase":"Preparation"},battle],
        "occurrence_count":3,"interval_days":28,"rolling":True})
    assert first.status_code==201,first.text
    rows=first.json()["items"]
    def flames(start="2090-03-01",end="2090-05-30"):
        return [r for r in c.get(url,params={"start":start,"end":end}).json()["items"] if r["event_type"]==rule["event_type"]]
    assert [r["starts_at"] for r in flames()]==["2090-03-06","2090-04-03","2090-05-01"]
    assert flames()[0]["ends_at"]=="2090-03-09" and flames()[0]["confidence"]=="estimated"
    review_url=url+"/cycles/"+rows[0]["cycle_id"]+"/reconcile"
    plan=c.get(review_url+"?following=true").json()
    shifted=c.post(review_url,json={"action":"shift","following":True,"shift_days":1,
        "series_revision":plan["series_revision"],"revisions":{r["id"]:r["revision"] for r in plan["items"]}})
    assert shifted.status_code==200,shifted.text
    assert [r["starts_at"] for r in flames()]==["2090-03-07","2090-04-04","2090-05-02"]
    from app.services.calendar import renew_schedules
    from datetime import datetime,timezone
    assert renew_schedules(settings.database_path,datetime(2090,5,1,tzinfo=timezone.utc))>0
    assert [r["starts_at"] for r in flames("2090-05-01","2090-07-01")]==["2090-05-02","2090-05-30","2090-06-27"]
    assert c.post(url,json={**fields,"event_type":rule["event_type"]}).status_code==409
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM calendar_occurrences WHERE event_type=?",(rule["event_type"],)).fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
    assert c.delete(url+"/follow/"+rid).status_code==200
    assert flames()==[]


def test_castle_week_dependency_and_manual_conflicts(authenticated_client):
    c=authenticated_client
    root,_=setup(c)
    url=root+"/calendar"
    rule={"event_type":"game:crystal-reactivation-2","state_id":"1001","starts_on":"2090-03-01"}
    manual={"event_type":rule["event_type"],"scope":"state","state_id":"1001","starts_at":"2090-03-08","precision":"date"}
    old=c.post(url,json=manual).json()["items"][0]
    assert c.post(url+"/follow",json=rule).status_code==409
    assert c.put(url+"/"+old["id"],json={**manual,"revision":old["revision"],"schedule_status":"cancelled"}).status_code==200
    assert c.post(url+"/follow",json=rule).status_code==200
    castle={**manual,"event_type":"castle_battle","starts_at":"2090-03-11"}
    assert c.post(url,json=castle).status_code==201
    castle2={**castle,"starts_at":"2090-03-25"}
    assert c.post(url,json=castle2).status_code==201
    items=[r for r in c.get(url,params={"start":"2090-03-01","end":"2090-04-01"}).json()["items"] if r.get("follow_rule_id")]
    # Derive the Friday from each actual Castle week, not a guessed fixed interval.
    from datetime import date,timedelta
    for anchor in (castle["starts_at"],castle2["starts_at"]):
        day=date.fromisoformat(anchor)
        friday=(day+timedelta(days=4-day.weekday())).isoformat()
        if friday!="2090-03-08":
            assert any(r["starts_at"]==friday for r in items)
    assert all(r["scope"]=="state" and r["confidence"]=="estimated" for r in items)
    assert c.post(url+"/follow",json={**rule,"state_id":"9999"}).status_code==409
