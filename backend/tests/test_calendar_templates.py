from app.database import connection
from test_calendar import setup


def test_templates_are_scoped_reusable_and_do_not_create_events(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/calendar/templates"
    schedule={"event_type":"foundry","scope":"alliance","alliance_id":aid,"state_id":"1001",
              "precision":"minute","starts_at":"2090-05-01T15:00Z","ends_at":"2090-05-01T16:00Z",
              "interval_minutes":20160,"occurrence_count":4,"rolling":True,"reject_existing":True}
    assert c.get(url).json()=={"items":[]}
    response=c.post(url,json={"name":"Legion 1","schedule":schedule})
    assert response.status_code==201,response.text
    template=response.json()
    assert template["schedule"]["confidence"]=="estimated"
    assert template["schedule"]["rolling"] is True
    assert "request_key" not in template["schedule"]
    assert c.get(url).json()=={"items":[template]}
    assert c.post(url,json={"name":" legion 1 ","schedule":schedule}).status_code==409
    other=c.post("/api/v1/groups",json={"name":"Other","primary_alliance_name":"Other","primary_alliance_tag":"OTH","primary_alliance_state_id":"1001"}).json()
    other_url=f"/api/v1/groups/{other['id']}/calendar/templates"
    assert c.get(other_url).json()=={"items":[]}
    assert c.post(other_url,json={"name":"Other","schedule":schedule}).status_code==404
    assert c.delete(other_url+"/"+template["id"]).status_code==404
    assert c.post(url,json={"name":"Invalid","schedule":{**schedule,"interval_minutes":0}}).status_code==422
    with connection(settings.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM calendar_occurrences").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0]==0
    copied={**template["schedule"],"starts_at":"2090-06-01T15:00Z","ends_at":"2090-06-01T16:00Z"}
    created=c.post(root+"/calendar",json=copied)
    assert created.status_code==201,created.text
    assert len(created.json()["items"])==4
    assert c.delete(url+"/"+template["id"]).status_code==200
    assert c.get(url).json()=={"items":[]}
    assert len(c.get(root+"/calendar?start=2090-06-01&end=2090-08-01").json()["items"])==4
    c.headers.pop("X-CSRF-Token")
    assert c.post(url,json={"name":"New","schedule":schedule}).status_code==403
    assert c.delete(url+"/"+template["id"]).status_code==403


def test_templates_require_auth(client):
    assert client.get("/api/v1/groups/missing/calendar/templates").status_code==401
