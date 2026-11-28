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
