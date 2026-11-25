"""Bounded Google Vision OCR transport. Preview only, no event writes."""
from __future__ import annotations

import base64
import json
import threading
from functools import lru_cache
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest
from google.auth.exceptions import GoogleAuthError
import urllib.error
import urllib.request

MAX_IMAGE_BYTES = 900 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
TIMEOUT_SECONDS = 15
ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
_lock = threading.Lock()


class OcrError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def is_busy() -> bool:
    return _lock.locked()


@lru_cache(maxsize=2)
def _credentials(path: str):
    return service_account.Credentials.from_service_account_file(
        path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )


def _headers(api_key: str | None, credentials_path: str | None) -> dict:
    headers = {"Content-Type": "application/json"}
    if credentials_path:
        try:
            credentials = _credentials(credentials_path)
            # Do not accept arbitrary token destinations from credential files.
            if credentials._token_uri != "https://oauth2.googleapis.com/token":
                raise ValueError("Unexpected token endpoint")
            if not credentials.valid:
                transport = GoogleRequest()
                def bounded_request(*args, **kwargs):
                    kwargs["timeout"] = 8
                    return transport(*args, **kwargs)
                try:
                    credentials.refresh(bounded_request)
                finally:
                    transport.session.close()
            credentials.apply(headers)
        except (GoogleAuthError, OSError, ValueError, TypeError, KeyError):
            raise OcrError(502, "Google service account authentication failed") from None
    elif api_key:
        headers["x-goog-api-key"] = api_key
    else:
        raise OcrError(409, "Google Vision OCR is not configured")
    return headers


def extract(image: bytes, api_key: str | None, credentials_path: str | None = None) -> dict:
    if len(image) > MAX_IMAGE_BYTES:
        raise OcrError(413, "Image exceeds OCR upload limit")
    if not (image.startswith(b"\x89PNG\r\n\x1a\n") or image.startswith(b"\xff\xd8\xff")):
        raise OcrError(415, "Use a PNG or JPEG image")
    if not api_key and not credentials_path:
        raise OcrError(409, "Google Vision OCR is not configured")
    if not _lock.acquire(blocking=False):
        raise OcrError(429, "OCR is busy; try again")
    try:
        payload = json.dumps({"requests": [{"image": {"content": base64.b64encode(image).decode("ascii")}, "features": [{"type": "TEXT_DETECTION"}]}]}).encode()
        request = urllib.request.Request(ENDPOINT, data=payload, headers=_headers(api_key, credentials_path), method="POST")
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise OcrError(502, "OCR response exceeds size limit")
            result = json.loads(raw)
            annotation = result["responses"][0]
            if not isinstance(annotation, dict):
                raise ValueError()
            if annotation.get("error"):
                code = annotation["error"].get("code")
                raise OcrError(502, "Google Vision authorization or configuration error" if code in (7, 16) else "Google Vision returned an OCR error")
            words = annotation.get("textAnnotations") or []
            text = (annotation.get("fullTextAnnotation") or {}).get("text") or (words[0].get("description", "") if words else "")
            if not isinstance(text, str):
                raise ValueError()
            tokens = []
            for word in words[1:]:
                value = word.get("description")
                vertices = (word.get("boundingPoly") or {}).get("vertices") or []
                if isinstance(value, str) and len(vertices) == 4:
                    tokens.append({"text": value, "vertices": [{"x": int(v.get("x", 0)), "y": int(v.get("y", 0))} for v in vertices]})
            return {"provider": "google_vision", "text": text.replace("\r\n", "\n").replace("\r", "\n"), "tokens": tokens, "warnings": [] if text else ["no_text_found"]}
        except OcrError:
            raise
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            raise OcrError(502 if code != 429 else 429, "Google Vision authorization or configuration error" if code in (401, 403) else "Google Vision quota exceeded" if code == 429 else "Google Vision request failed") from None
        except (TimeoutError, urllib.error.URLError, OSError):
            raise OcrError(502, "Google Vision unavailable or timed out") from None
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError):
            raise OcrError(502, "Invalid Google Vision response") from None
    finally:
        _lock.release()
