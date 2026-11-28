from datetime import datetime, timedelta, timezone

import pytest

from app.database import connection
from app.services.calendar import renew_schedules
from test_calendar import setup
from test_calendar_cycle_series import create


def schedule(row, **changes):
    fields = {k: row[k] for k in ("event_type", "scope", "alliance_id", "state_id", "phase", "precision",
                                  "confidence", "starts_at", "ends_at", "revision", "schedule_status")}
    return {**fields, **changes}


def apply(c, url, fields, scope):
    body = {"scope": scope, "schedule": fields}
    preview = c.post(url, json={**body, "preview": True})
    assert preview.status_code == 200, preview.text
    result = c.post(url, json={**body, "token": preview.json()["token"]})
    assert result.status_code == 200, result.text
    return result.json()["items"]


@pytest.mark.parametrize("scope", ["single", "all", "following"])
def test_scopes_from_linked_bear_preserve_results_and_other_traps(authenticated_client, settings, scope):
    c = authenticated_client
    root, aid = setup(c)
    url = root + "/calendar"
    # Historical occurrence and future 48-hour recurrences; independent of test execution date.
    day = datetime.now(timezone.utc).date() - timedelta(days=1)
    start = day.isoformat() + "T00:00Z"
    end = day.isoformat() + "T00:30Z"
    base = {"event_type": "bear_trap", "scope": "alliance", "alliance_id": aid, "state_id": "1001",
            "starts_at": start, "ends_at": end, "precision": "minute", "phase": "Trap 2",
            "occurrence_count": 4, "interval_minutes": 2880, "rolling": True, "reject_existing": True,
            "bear_cycle_anchor": start, "bear_session_key": "trap_2"}
    response = c.post(url, json=base)
    assert response.status_code == 201, response.text
    rows = response.json()["items"]
    response = c.post(url, json={**base, "phase": "Trap 1", "bear_session_key": "trap_1",
                                  "starts_at": day.isoformat() + "T15:00Z", "ends_at": day.isoformat() + "T15:30Z"})
    assert response.status_code == 201, response.text
    others = response.json()["items"]
    target = url + "/" + rows[0]["id"]
    linked = c.post(target + "/start-entry", json={"revision": rows[0]["revision"], "confirmed": True})
    assert linked.status_code == 200, linked.text
    link = linked.json()["linked"]
    sid, eid = link["session_id"], link["id"]
    with connection(settings.database_path) as db:
        db.execute("INSERT INTO players(fid,nickname) VALUES ('123456789','Test Bear Player')")
        db.execute("""INSERT INTO event_session_roster(session_id,player_fid,nickname,eligibility,registration,attendance)
            VALUES (?, '123456789','Test Bear Player','confirmed','unknown','confirmed_present')""",(sid,))
        db.execute("""INSERT INTO event_session_metrics(session_id,player_fid,metric_key,raw_value)
            VALUES (?, '123456789','damage',123456789)""",(sid,))
        db.execute("UPDATE event_sessions SET results_complete=1 WHERE id=?", (sid,))
        db.execute("UPDATE events SET status='published',bear_cycle_complete=1 WHERE id=?", (eid,))
        db.commit()
        original_session = dict(db.execute("SELECT * FROM event_sessions WHERE id=?", (sid,)).fetchone())
        original_roster = dict(db.execute("SELECT * FROM event_session_roster WHERE session_id=?", (sid,)).fetchone())
        original_metric = dict(db.execute("SELECT * FROM event_session_metrics WHERE session_id=?", (sid,)).fetchone())
        original_rolling = dict(db.execute("SELECT * FROM calendar_rolling_series WHERE series_id=?", (rows[0]["series_id"],)).fetchone())
        original = dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (rows[0]["id"],)).fetchone())
        audit_count = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    endpoint = target + "/scoped-edit"
    info = c.get(endpoint).json()
    assert info["recurring"] and info["following_count"] == 3 and info["linked"]
    fields = schedule(original, starts_at=day.isoformat() + "T00:30Z", ends_at=day.isoformat() + "T01:00Z")
    body = {"scope": scope, "schedule": fields}
    preview = c.post(endpoint, json={**body, "preview": True})
    assert preview.status_code == 200, preview.text
    with connection(settings.database_path) as db:
        assert dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (rows[0]["id"],)).fetchone()) == original
        assert dict(db.execute("SELECT * FROM event_sessions WHERE id=?", (sid,)).fetchone()) == original_session
        assert db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == audit_count
    response = c.post(endpoint, json={**body, "token": preview.json()["token"]})
    assert response.status_code == 200, response.text
    changed = response.json()["items"]
    expected = rows[:1] if scope == "single" else rows if scope == "all" else rows[1:]
    assert [r["id"] for r in changed] == [r["id"] for r in expected]
    assert all(r["starts_at"].endswith("T00:30Z") and r["ends_at"].endswith("T01:00Z") for r in changed)
    with connection(settings.database_path) as db:
        current = dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (rows[0]["id"],)).fetchone())
        session = dict(db.execute("SELECT * FROM event_sessions WHERE id=?", (sid,)).fetchone())
        if scope == "following":
            assert current == original and session == original_session
        else:
            assert current["entry_cycle_date"] == original["entry_cycle_date"]
            assert session == {**original_session, "started_at": day.isoformat() + "T00:30:00+00:00", "revision": original_session["revision"] + 1}
        assert db.execute("SELECT status,bear_cycle_complete FROM events WHERE id=?", (eid,)).fetchone()[:] == ("published", 1)
        assert dict(db.execute("SELECT * FROM event_session_roster WHERE session_id=?", (sid,)).fetchone()) == original_roster
        assert dict(db.execute("SELECT * FROM event_session_metrics WHERE session_id=?", (sid,)).fetchone()) == original_metric
        for other in others:
            assert dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (other["id"],)).fetchone()) == other
        rolling = dict(db.execute("SELECT * FROM calendar_rolling_series WHERE series_id=?", (rows[0]["series_id"],)).fetchone())
        if scope == "single":
            assert rolling == original_rolling
            for other in rows[1:]:
                assert dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (other["id"],)).fetchone()) == other
        else:
            assert rolling["next_start"].endswith("T00:30Z")
    assert c.get(target + "/event-link").json()["linked"]["session_id"] == sid
    # Neither a stale multi-event review nor a cross-date correction can silently change records.
    assert c.post(endpoint, json={**body, "token": preview.json()["token"]}).status_code == 409
    assert c.post(endpoint, json={"scope": "single", "schedule": schedule(current, starts_at=(day-timedelta(days=1)).isoformat()+"T00:30Z", ends_at=None)}).status_code == 409


@pytest.mark.parametrize("kind", ["alliance_mobilization", "alliance_championship", "game:lucky-wheel"])
def test_same_three_scopes_for_ordinary_series(authenticated_client, settings, kind):
    c = authenticated_client
    root, aid = setup(c)
    url = root + "/calendar"
    state = kind.startswith("game:")
    response = c.post(url, json={"event_type": kind, "scope": "state" if state else "alliance", "alliance_id": None if state else aid,
                                "state_id": "1001", "starts_at": "2090-02-01", "ends_at": "2090-02-04",
                                "precision": "date", "occurrence_count": 4, "interval_minutes": 20160})
    assert response.status_code == 201, response.text
    rows = response.json()["items"]
    endpoint = url + "/" + rows[0]["id"] + "/scoped-edit"
    fields = schedule(rows[0], starts_at="2090-02-02", ends_at="2090-02-05")
    changed = apply(c, endpoint, fields, "following")
    assert [r["id"] for r in changed] == [r["id"] for r in rows[1:]]
    assert changed[0]["starts_at"] == "2090-02-16"
    with connection(settings.database_path) as db:
        assert dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (rows[0]["id"],)).fetchone()) == rows[0]
    changed = apply(c, endpoint, schedule(rows[0], schedule_status="cancelled"), "following")
    assert all(r["schedule_status"] == "cancelled" for r in changed)
    assert c.get(endpoint).json()["following_count"] == 0


def test_cycle_phase_recurs_with_explicit_legion_time_and_keeps_other_phases(authenticated_client, settings):
    c = authenticated_client
    root, aid = setup(c)
    rows = create(c, root, aid)
    first = rows[3]
    endpoint = root + "/calendar/" + first["id"] + "/scoped-edit"
    fields = schedule(first, starts_at="2090-03-12T19:00Z", ends_at="2090-03-12T20:00Z", precision="minute")
    assert c.get(endpoint).json()["following_count"] == 4
    changed = apply(c, endpoint, fields, "all")
    assert len(changed) == 5 and all(r["starts_at"].endswith("T19:00Z") for r in changed)
    assert all(r["phase"] == "Legion 1" and r["entry_cycle_date"] == r["starts_at"][:10] for r in changed)
    with connection(settings.database_path) as db:
        for original in rows:
            if original["phase"] != "Legion 1":
                assert dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?", (original["id"],)).fetchone()) == original
    assert renew_schedules(settings.database_path, datetime(2090, 5, 1, tzinfo=timezone.utc)) > 0
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM calendar_occurrences WHERE phase='Legion 1' AND precision='minute' AND substr(starts_at,12,5)='19:00'").fetchone()[0] > 5
        assert db.execute("SELECT COUNT(*) FROM calendar_occurrences WHERE phase='Legion 2' AND precision!='date'").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_scoped_preview_rejects_stale_following_occurrence_and_rolls_back_failed_all(authenticated_client, settings):
    c = authenticated_client
    root, aid = setup(c)
    url = root + "/calendar"
    response = c.post(url, json={"event_type":"game:lucky-wheel","scope":"state","state_id":"1001","starts_at":"2090-03-01",
                                "ends_at":"2090-03-04","precision":"date","occurrence_count":3,"interval_minutes":20160})
    assert response.status_code == 201
    rows = response.json()["items"]
    endpoint = url + "/" + rows[0]["id"] + "/scoped-edit"
    body = {"scope":"all","schedule":schedule(rows[0],starts_at="2090-03-02",ends_at="2090-03-05")}
    preview = c.post(endpoint,json={**body,"preview":True})
    assert preview.status_code==200,preview.text
    assert c.put(url+"/"+rows[1]["id"],json=schedule(rows[1],starts_at="2090-03-16",ends_at="2090-03-19")).status_code==200
    assert c.post(endpoint,json={**body,"token":preview.json()["token"]}).status_code==409
    with connection(settings.database_path) as db:
        assert dict(db.execute("SELECT * FROM calendar_occurrences WHERE id=?",(rows[0]["id"],)).fetchone())==rows[0]


@pytest.mark.parametrize("kind", ["alliance_mobilization", "alliance_championship"])
def test_linked_date_record_can_gain_clock_time_without_changing_event_date(authenticated_client,settings,kind):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar"
    row=c.post(url,json={"event_type":kind,"scope":"alliance","alliance_id":aid,"state_id":"1001",
        "precision":"date","starts_at":"2090-06-01","ends_at":"2090-06-06"}).json()["items"][0]
    target=url+"/"+row["id"]
    linked=c.post(target+"/start-entry",json={"revision":row["revision"],"confirmed":True})
    assert linked.status_code==200,linked.text
    event=linked.json()["linked"]
    result=c.post(target+"/scoped-edit",json={"scope":"single","schedule":schedule(row,revision=linked.json()["revision"],
        precision="minute",starts_at="2090-06-01T04:00Z",ends_at="2090-06-06T00:00Z")})
    assert result.status_code==200,result.text
    assert result.json()["items"][0]["precision"]=="minute"
    assert c.get(target+"/event-link").json()["linked"]==event
    with connection(settings.database_path) as db:
        assert db.execute("SELECT occurred_on FROM events WHERE id=?",(event["id"],)).fetchone()[0]=="2090-06-01"


def test_svs_preparation_following_scope_moves_only_dependent_future_dates(authenticated_client):
    c=authenticated_client
    root,_=setup(c)
    url=root+"/calendar"
    rule={"event_type":"game:flame-and-fang","state_id":"1001","starts_on":"2090-03-01"}
    assert c.post(url+"/follow",json=rule).status_code==200
    common={"scope":"state","state_id":"1001","alliance_id":None,"precision":"minute","confidence":"estimated"}
    phases=[{**common,"event_type":kind,"phase":phase,"starts_at":start,"ends_at":end} for kind,phase,start,end in [
        ("svs_matchmaking","Matchmaking","2090-03-04T00:00Z","2090-03-06T00:00Z"),
        ("svs_preparation","Preparation","2090-03-06T00:00Z","2090-03-11T10:00Z"),
        ("svs_battle","Battle","2090-03-11T10:00Z","2090-03-11T22:00Z"),
        ("svs_triage","Field Triage","2090-03-11T22:00Z","2090-03-14T00:00Z")]]
    result=c.post(url+"/cycles",json={"kind":"svs","request_key":"scoped-svs-cycle-01","phases":phases,"occurrence_count":3,"interval_days":28,"rolling":True})
    assert result.status_code==201,result.text
    rows=result.json()["items"]
    selected=rows[1]
    changed=apply(c,url+"/"+selected["id"]+"/scoped-edit",schedule(selected,starts_at="2090-03-07T00:00Z"),"following")
    assert [r["starts_at"] for r in changed]==["2090-04-04T00:00Z","2090-05-02T00:00Z"]
    all_rows=c.get(url,params={"start":"2090-03-01","end":"2090-05-30"}).json()["items"]
    assert [r["starts_at"] for r in all_rows if r["event_type"]=="game:flame-and-fang"]==["2090-03-06","2090-04-04","2090-05-02"]
    assert next(r for r in all_rows if r["id"]==selected["id"])["starts_at"]==selected["starts_at"]
