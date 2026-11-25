import io
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from app.factory import create_app
from app.services import vision_ocr
from test_api import create_onboarded_group

PNG = bytes.fromhex("89504e470d0a1a0a") + b"fixture"


def test_google_transport(monkeypatch):
    class FakeOpener:
        def open(self, request, timeout):
            assert request.full_url == vision_ocr.ENDPOINT
            assert request.get_header("X-goog-api-key") == "fake-key"
            assert timeout == 15
            assert json.loads(request.data)["requests"][0]["features"] == [{"type": "TEXT_DETECTION"}]
            return io.BytesIO(json.dumps({"responses": [{"fullTextAnnotation": {"text": "Fox 100"}, "textAnnotations": [{"description": "Fox 100"}, {"description": "Fox", "boundingPoly": {"vertices": [{}, {"x": 10}, {"x": 10, "y": 5}, {"y": 5}]}}]}]}).encode())
    monkeypatch.setattr(vision_ocr.urllib.request, "build_opener", lambda *args: FakeOpener())
    result = vision_ocr.extract(PNG, "fake-key")
    assert result["text"] == "Fox 100"
    assert result["tokens"][0]["vertices"][0] == {"x": 0, "y": 0}
    assert "fake-key" not in str(result)


def test_bad_image():
    with pytest.raises(vision_ocr.OcrError) as caught:
        vision_ocr.extract(b"not an image", "fake-key")
    assert caught.value.status == 415


def test_preview_authorization_and_no_writes(settings, monkeypatch):
    with TestClient(create_app(replace(settings, google_vision_api_key="fake-key"))) as client:
        assert client.get("/api/v1/ocr/status").status_code == 401
        csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        login = client.post("/api/v1/auth/login", headers={"X-CSRF-Token": csrf}, json={"password": "a sufficiently long test password"})
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        assert client.get("/api/v1/ocr/status").json()["configured"] is True
        group = create_onboarded_group(client)
        gid = group["id"]
        aid = client.get(f"/api/v1/groups/{gid}/alliances").json()["items"][0]["id"]
        event = client.post(f"/api/v1/groups/{gid}/alliances/{aid}/events", json={"event_type": "bear_trap", "occurred_on": "2026-11-25", "status": "draft"}).json()
        base = f"/api/v1/groups/{gid}/events/{event['id']}"
        session = client.post(base + "/sessions", json={"session_key": "trap_1", "started_at": "2026-11-25T18:00:00Z"}).json()["sessions"][0]
        url = base + "/sessions/" + session["id"] + "/ocr/preview"
        before = client.get(base + "/editor").json()
        monkeypatch.setattr(vision_ocr, "extract", lambda image, key, credentials_path=None: {"text": "Fox", "tokens": [], "provider": "google_vision", "warnings": []})
        assert client.post(url, content=PNG, headers={"Content-Type": "image/png", "X-CSRF-Token": "invalid"}).status_code == 403
        assert client.post(url, content=PNG, headers={"Content-Type": "image/png"}).status_code == 200
        assert client.post(url, content=b"x" * (vision_ocr.MAX_IMAGE_BYTES + 1), headers={"Content-Type": "image/png"}).status_code == 413
        assert client.get(base + "/editor").json() == before


def test_service_account_precedence(monkeypatch):
    class Credentials:
        valid = True
        _token_uri = "https://oauth2.googleapis.com/token"
        def apply(self, headers):
            headers["authorization"] = "Bearer fake-token"
    monkeypatch.setattr(vision_ocr, "_credentials", lambda path: Credentials())
    headers = vision_ocr._headers("fake-api-key", "/data/secrets/google-vision.json")
    assert headers["authorization"] == "Bearer fake-token"
    assert "x-goog-api-key" not in headers


def test_service_account_failure_does_not_fallback(monkeypatch):
    def broken(path):
        raise ValueError("private credential content")
    monkeypatch.setattr(vision_ocr, "_credentials", broken)
    with pytest.raises(vision_ocr.OcrError) as caught:
        vision_ocr._headers("fake-key", "/missing.json")
    assert caught.value.status == 502
    assert "private credential content" not in str(caught.value)
