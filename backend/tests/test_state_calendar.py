from app.services import state_calendar, whiteoutstats
from app.database import connection
from test_calendar import setup


def test_state_date_cache_and_override(authenticated_client,settings):
    c=authenticated_client
    root,aid=setup(c)
    url=root+"/state-calendar-profiles"
    assert c.get(url).json()["items"][0]["opened_on"] is None
    class Provider:
        calls=0
        def fetch_state(self,state):
            self.calls+=1
            return whiteoutstats.ProviderResponse(200,{"state":{"kid":1001,"opened_on":"2025-01-01"}})
    provider=Provider()
    assert state_calendar.sync_state(settings.database_path,provider,"1001")
    assert not state_calendar.sync_state(settings.database_path,provider,"1001")
    assert provider.calls==1
    item=c.get(url).json()["items"][0]
    assert item["source"]=="whiteoutstats"
    assert item["opened_on"]=="2025-01-01"
    result=c.put(url+"/1001",json={"opened_on":"2025-01-02","revision":item["revision"]})
    assert result.status_code==200,result.text
    assert result.json()["source"]=="manual"
    assert c.put(url+"/1001",json={"opened_on":None,"revision":item["revision"]}).status_code==409
    with connection(settings.database_path) as db:
        db.execute("UPDATE state_calendar_profiles SET last_attempt_at=NULL")
        db.commit()
    class Bad:
        def fetch_state(self,state):
            return whiteoutstats.ProviderResponse(200,{"kid":999,"opened_on":"2025-01-03"})
    assert not state_calendar.sync_state(settings.database_path,Bad(),"1001")
    current=c.get(url).json()["items"][0]
    assert current["opened_on"]=="2025-01-02"
    assert current["provider_opened_on"]=="2025-01-01"
    assert current["last_status"]=="failed"
    result=c.put(url+"/1001",json={"opened_on":None,"revision":current["revision"]})
    assert result.json()["opened_on"]=="2025-01-01"
    assert c.put(url+"/999",json={"opened_on":"2025-01-01","revision":0}).status_code==404
    c.headers.pop("X-CSRF-Token")
    assert c.put(url+"/1001",json={"opened_on":None,"revision":0}).status_code==403

def test_malformed_provider_response_keeps_cached_date(authenticated_client,settings):
    root,_=setup(authenticated_client)
    class Provider:
        def fetch_state(self,state):
            return whiteoutstats.ProviderResponse(200,{"kid":1001,"opened_on":"2025-01-01"})
    assert state_calendar.sync_state(settings.database_path,Provider(),"1001")
    for body in (None,[],{"state":[]},{"kid":1001,"opened_on":"invalid"}):
        with connection(settings.database_path) as db:
            db.execute("UPDATE state_calendar_profiles SET last_attempt_at=NULL")
            db.commit()
        class Bad:
            def fetch_state(self,state):
                return whiteoutstats.ProviderResponse(200,body)
        assert not state_calendar.sync_state(settings.database_path,Bad(),"1001")
        item=authenticated_client.get(root+"/state-calendar-profiles").json()["items"][0]
        assert item["opened_on"]=="2025-01-01" and item["last_status"]=="failed"
