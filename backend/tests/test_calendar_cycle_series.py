from datetime import datetime,timezone
from app.database import connection
from app.services.calendar import renew_schedules
from test_calendar import setup


def create(c,root,aid,*,rolling=True):
    common={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","precision":"date","confidence":"estimated"}
    phases=[{**common,"phase":phase,"starts_at":start,"ends_at":end} for phase,start,end in [
        ("Voting","2090-03-06","2090-03-08"),("Registration","2090-03-08","2090-03-10"),
        ("Matchmaking","2090-03-10","2090-03-12"),("Legion 1","2090-03-12",None),("Legion 2","2090-03-12",None)]]
    payload={"kind":"foundry","request_key":"rolling-cycle-000001","phases":phases,"occurrence_count":5,"interval_days":14,"rolling":rolling}
    response=c.post(root+"/calendar/cycles",json=payload)
    assert response.status_code==201,response.text
    assert c.post(root+"/calendar/cycles",json=payload).json()==response.json()
    return response.json()["items"]


def test_cycle_renewal_is_atomic_idempotent_and_preserves_history(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    rows=create(c,root,aid)
    assert len(rows)==25
    assert renew_schedules(settings.database_path,datetime(2090,5,1,tzinfo=timezone.utc))==20
    assert renew_schedules(settings.database_path,datetime(2090,5,1,tzinfo=timezone.utc))==0
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM calendar_cycles").fetchone()[0]==9
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM calendar_occurrences WHERE phase LIKE 'Legion %' AND (precision!='date' OR ends_at IS NOT NULL)").fetchone()[0]==0
        assert db.execute("SELECT revision FROM calendar_occurrences WHERE id=?",(rows[0]["id"],)).fetchone()[0]==1
    conflict=c.post(root+"/calendar",json={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","precision":"date","starts_at":"2090-07-16","phase":"Legion 1"})
    assert conflict.status_code==201
    renew_schedules(settings.database_path,datetime(2090,6,1,tzinfo=timezone.utc))
    with connection(settings.database_path) as db:
        assert db.execute("SELECT status FROM calendar_cycle_series").fetchone()[0]=="conflict"
        assert not db.execute("SELECT 1 FROM calendar_occurrences WHERE phase='Voting' AND starts_at='2090-07-10'").fetchone()


def test_reconcile_one_and_following_protects_manual_exceptions(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    rows=create(c,root,aid)
    url=root+"/calendar/cycles/"
    one=url+rows[5]["cycle_id"]+"/reconcile"
    plan=c.get(one).json()
    payload={"action":"confirm","revisions":{r["id"]:r["revision"] for r in plan["confirm_items"]},"series_revision":plan["series_revision"]}
    assert c.post(one,json=payload).status_code==200
    assert c.post(one,json=payload).status_code==409
    target=url+rows[0]["cycle_id"]+"/reconcile"
    plan=c.get(target+"?following=true").json()
    assert len(plan["items"])==20 and plan["protected_cycles"]==1
    payload={"action":"shift","following":True,"shift_days":1,"revisions":{r["id"]:r["revision"] for r in plan["items"]},"series_revision":plan["series_revision"]}
    response=c.post(target,json=payload)
    assert response.status_code==200,response.text
    assert c.post(target,json=payload).status_code==409
    with connection(settings.database_path) as db:
        assert db.execute("SELECT starts_at FROM calendar_occurrences WHERE id=?",(rows[0]["id"],)).fetchone()[0]=="2090-03-07"
        assert db.execute("SELECT starts_at FROM calendar_occurrences WHERE id=?",(rows[5]["id"],)).fetchone()[0]==rows[5]["starts_at"]
        assert db.execute("SELECT entry_cycle_date FROM calendar_occurrences WHERE id=?",(rows[3]["id"],)).fetchone()[0]=="2090-03-13"
    assert renew_schedules(settings.database_path,datetime(2090,5,1,tzinfo=timezone.utc))>0
    with connection(settings.database_path) as db:
        assert db.execute("SELECT 1 FROM calendar_occurrences WHERE phase='Voting' AND starts_at='2090-05-16'").fetchone()
    plan=c.get(target).json()
    assert c.post(target,json={"action":"stop","series_revision":plan["series_revision"]}).status_code==200
    assert renew_schedules(settings.database_path,datetime(2090,9,1,tzinfo=timezone.utc))==0
    c.headers.pop("X-CSRF-Token")
    assert c.post(target,json={"action":"stop","series_revision":plan["series_revision"]}).status_code==403


def test_cycle_shift_rejects_protected_overlap_and_stale_revision(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    rows=create(c,root,aid,rolling=False)
    url=root+"/calendar/cycles/"
    first=url+rows[0]["cycle_id"]+"/reconcile"
    second=url+rows[5]["cycle_id"]+"/reconcile"
    plan=c.get(second).json()
    assert c.post(second,json={"action":"confirm","revisions":{r["id"]:r["revision"] for r in plan["confirm_items"]},"series_revision":plan["series_revision"]}).status_code==200
    plan=c.get(first+"?following=true").json()
    data={"action":"shift","following":True,"shift_days":14,"revisions":{r["id"]:r["revision"] for r in plan["items"]},"series_revision":plan["series_revision"]}
    assert c.post(first,json=data).status_code==409
    assert c.get(first).json()["items"][0]["starts_at"]==rows[0]["starts_at"]
    data["shift_days"]=1
    data["revisions"][rows[0]["id"]]=999
    assert c.post(first,json=data).status_code==409


def test_cadence_changes_following_cycles_and_renewal_without_moving_anchor(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    rows=create(c,root,aid)
    url=root+"/calendar/cycles/"+rows[5]["cycle_id"]+"/reconcile"
    # Confirm the anchor; confirmation is not permission to move it.
    confirm=c.get(url).json()
    assert c.post(url,json={"action":"confirm","revisions":{r["id"]:r["revision"] for r in confirm["confirm_items"]},"series_revision":confirm["series_revision"]}).status_code==200
    plan=c.get(url+"?interval_days=7").json()
    assert len(plan["items"])==15
    assert plan["proposed"][0]["starts_at"]=="2090-03-27"
    assert plan["next_start"]=="2090-04-17"
    data={"action":"cadence","following":True,"interval_days":7,"series_revision":plan["series_revision"],
        "revisions":{r["id"]:r["revision"] for r in plan["anchor_items"]+plan["items"]}}
    stale={**data,"revisions":{**data["revisions"],rows[5]["id"]:999}}
    assert c.post(url,json=stale).status_code==409
    response=c.post(url,json=data)
    assert response.status_code==200,response.text
    assert c.post(url,json=data).status_code==409
    with connection(settings.database_path) as db:
        assert db.execute("SELECT interval_days FROM calendar_cycle_series").fetchone()[0]==7
        assert db.execute("SELECT starts_at FROM calendar_occurrences WHERE id=?",(rows[5]["id"],)).fetchone()[0]=="2090-03-20"
        assert db.execute("SELECT starts_at FROM calendar_occurrences WHERE id=?",(rows[0]["id"],)).fetchone()[0]=="2090-03-06"
        assert db.execute("SELECT entry_cycle_date FROM calendar_occurrences WHERE id=?",(rows[13]["id"],)).fetchone()[0]=="2090-04-02"
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
    assert renew_schedules(settings.database_path,datetime(2090,4,16,tzinfo=timezone.utc))>0
    with connection(settings.database_path) as db:
        assert db.execute("SELECT 1 FROM calendar_occurrences WHERE phase='Voting' AND starts_at='2090-04-17'").fetchone()


def test_cadence_rejects_overlap_with_protected_cycle(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    rows=create(c,root,aid,rolling=False)
    base=root+"/calendar/cycles/"
    protected=base+rows[5]["cycle_id"]+"/reconcile"
    plan=c.get(protected).json()
    assert c.post(protected,json={"action":"confirm","revisions":{r["id"]:r["revision"] for r in plan["confirm_items"]},"series_revision":plan["series_revision"]}).status_code==200
    url=base+rows[0]["cycle_id"]+"/reconcile"
    assert c.get(url+"?interval_days=7").status_code==409
    assert c.get(url+"?interval_days=6").status_code==409
    with connection(settings.database_path) as db:
        assert db.execute("SELECT interval_days FROM calendar_cycle_series").fetchone()[0]==14
        assert db.execute("SELECT starts_at FROM calendar_occurrences WHERE id=?",(rows[10]["id"],)).fetchone()[0]=="2090-04-03"
