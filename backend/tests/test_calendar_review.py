from app.database import connection
from test_calendar import setup


def test_calendar_review_is_read_only_and_session_scoped(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    base={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01T15:00Z","precision":"minute"}
    row=c.post(root+"/calendar",json=base).json()["items"][0]
    target=root+"/calendar/"+row["id"]
    result=c.post(target+"/draft",json={"revision":1,"confirmed":True,"session_key":"legion_1"})
    assert result.status_code==201,result.text
    data=result.json()
    assert data["review"]["scope"]=="session"
    assert data["review"]["registration"]=="not_recorded"
    assert data["review"]["publication"]=="draft"
    eid=data["linked"]["id"]
    sid=data["linked"]["session_id"]
    # A saved completeness flag without any player evidence cannot be called reviewed.
    with connection(settings.database_path) as db:
        db.execute("UPDATE event_sessions SET registration_complete=1 WHERE id=?",(sid,))
        db.execute("UPDATE events SET status='published' WHERE id=?",(eid,))
        db.commit()
    review=c.get(target+"/event-link").json()["review"]
    assert review["publication"]=="published"
    assert review["registration"]=="partial"
    assert review["final_attendance_review"] is False
    rows=c.get(root+"/calendar?start=2090-06-01&end=2090-06-02").json()["items"]
    assert rows[0]["review"]==review
    other=c.post(root+"/calendar",json={**base,"starts_at":"2090-06-01T20:00Z"}).json()["items"][0]
    rows=c.get(root+"/calendar?start=2090-06-01&end=2090-06-02").json()["items"]
    assert "review" not in next(r for r in rows if r["id"]==other["id"])
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM event_session_roster").fetchone()[0]==0


def test_championship_only_registration_applicable(authenticated_client):
    c=authenticated_client
    root,aid=setup(c)
    row=c.post(root+"/calendar",json={"event_type":"alliance_championship","scope":"alliance","alliance_id":aid,"state_id":"1001","starts_at":"2090-06-01","precision":"date"}).json()["items"][0]
    result=c.post(root+"/calendar/"+row["id"]+"/draft",json={"revision":1,"confirmed":True})
    assert result.status_code==201,result.text
    review=result.json()["review"]
    assert review["attendance"]=="not_applicable"
    assert review["results"]=="not_applicable"
    assert review["final_attendance_review"] is None
