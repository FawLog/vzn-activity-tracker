#!/usr/bin/env python3
"""Unprivileged, loopback-only webhook receiver. A signal is not deployment authority."""
import hashlib
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import re

REPO = "FawLog/vzn-activity-tracker"
MAX_BODY = 1024 * 1024
QUEUE = Path("/var/lib/vzn-deploy-inbox/pending")

def valid_event(raw, signature, event, secret):
    if not isinstance(signature, str) or not hmac.compare_digest(
        "sha256=" + hmac.new(secret, raw, hashlib.sha256).hexdigest(), signature
    ):
        return False
    if event == "ping":
        return False
    if event != "workflow_run":
        return False
    try:
        data = json.loads(raw)
        run = data["workflow_run"]
        return (data["repository"]["full_name"] == REPO and data["action"] == "completed"
                and run["head_branch"] == "main" and run["event"] == "push"
                and run["conclusion"] == "success" and run["status"] == "completed"
                and run["head_repository"]["full_name"] == REPO
                and bool(re.fullmatch("[0-9a-f]{40}", run["head_sha"])))
    except (KeyError, TypeError, ValueError):
        return False

class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def do_POST(self):
        if self.path != "/webhooks/deploy":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if not 0 < size <= MAX_BODY or self.headers.get("Transfer-Encoding"):
            self.send_error(413)
            return
        raw = self.rfile.read(size)
        if len(raw)==size and self.headers.get("X-GitHub-Event")=="ping" and hmac.compare_digest("sha256="+hmac.new(self.server.secret,raw,hashlib.sha256).hexdigest(),self.headers.get("X-Hub-Signature-256") or ""):
            self.send_response(204)
            self.end_headers()
            return
        if len(raw) != size or not valid_event(raw, self.headers.get("X-Hub-Signature-256"),
                                                self.headers.get("X-GitHub-Event"), self.server.secret):
            self.send_error(403)
            return
        # No SHA, URL or command crosses the privilege boundary. Coalesce notifications.
        try:
            fd = os.open(QUEUE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        self.send_response(202)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *args):
        # Do not log raw payload, headers or secrets.
        print("Webhook HTTP request handled", flush=True)

def main():
    secret = (Path(os.environ["CREDENTIALS_DIRECTORY"]) / "webhook-secret").read_bytes().strip()
    if len(secret) < 32:
        raise SystemExit("Webhook secret too short")
    server = HTTPServer(("127.0.0.1", 8091), Handler)
    server.secret = secret
    server.serve_forever()

if __name__ == "__main__":
    main()
