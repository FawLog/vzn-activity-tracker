"""Opaque server-side sessions, CSRF validation, and login throttling."""

from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response, status

from ..config import Settings
from ..database import connection, transaction
from ..security import keyed_identifier, token_hash

COOKIE_NAME = "vzn_session"
MAX_ANONYMOUS_SESSIONS = 2048


@dataclass(frozen=True)
class Session:
    raw_token: str
    csrf_token: str
    is_authenticated: bool
    expires_at: int


def _set_cookie(response: Response, settings: Settings, raw_token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=raw_token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def create_session(settings: Settings, response: Response, *, authenticated: bool = False) -> Session:
    now = int(time.time())
    raw_token = secrets.token_urlsafe(48)
    csrf = secrets.token_urlsafe(32)
    expires_at = now + settings.session_ttl_seconds
    with transaction(settings.database_path) as connection:
        connection.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (now,))
        connection.execute(
            """
            INSERT INTO admin_sessions(token_hash, csrf_token, is_authenticated, created_at, updated_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (token_hash(raw_token), csrf, int(authenticated), now, now, expires_at),
        )
        if not authenticated:
            connection.execute(
                """
                DELETE FROM admin_sessions
                WHERE token_hash IN (
                  SELECT token_hash
                  FROM admin_sessions
                  WHERE is_authenticated = 0
                  ORDER BY created_at DESC, rowid DESC
                  LIMIT -1 OFFSET ?
                )
                """,
                (MAX_ANONYMOUS_SESSIONS,),
            )
    _set_cookie(response, settings, raw_token)
    return Session(raw_token, csrf, authenticated, expires_at)


def load_session(request: Request, settings: Settings) -> Session | None:
    raw_token = request.cookies.get(COOKIE_NAME, "")
    if not raw_token:
        return None
    now = int(time.time())
    with connection(settings.database_path) as database:
        row = database.execute(
            """
            SELECT csrf_token, is_authenticated, expires_at
            FROM admin_sessions
            WHERE token_hash = ? AND expires_at > ?
            """,
            (token_hash(raw_token), now),
        ).fetchone()
    if row is None:
        return None
    return Session(raw_token, row["csrf_token"], bool(row["is_authenticated"]), row["expires_at"])


def require_session(request: Request, settings: Settings) -> Session:
    session = load_session(request, settings)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return session


def require_admin(request: Request, settings: Settings) -> Session:
    session = require_session(request, settings)
    if not session.is_authenticated:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return session


def require_csrf(request: Request, session: Session) -> None:
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not hmac.compare_digest(session.csrf_token, supplied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


def rotate_authenticated_session(
    settings: Settings,
    response: Response,
    previous_session: Session,
) -> Session:
    with transaction(settings.database_path) as connection:
        connection.execute(
            "DELETE FROM admin_sessions WHERE token_hash = ?",
            (token_hash(previous_session.raw_token),),
        )
    return create_session(settings, response, authenticated=True)


def destroy_session(settings: Settings, response: Response, session: Session) -> None:
    with transaction(settings.database_path) as connection:
        connection.execute(
            "DELETE FROM admin_sessions WHERE token_hash = ?",
            (token_hash(session.raw_token),),
        )
    response.delete_cookie(COOKIE_NAME, path="/")


def client_ip(request: Request, settings: Settings) -> str:
    peer = request.client.host if request.client else "unknown"
    if peer in settings.trusted_proxies:
        forwarded = request.headers.get("X-Forwarded-For", "")
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    return peer


def login_is_blocked(request: Request, settings: Settings) -> bool:
    now = int(time.time())
    key = keyed_identifier(client_ip(request, settings), settings.session_secret)
    with connection(settings.database_path) as database:
        row = database.execute(
            "SELECT blocked_until FROM login_attempts WHERE client_key = ?",
            (key,),
        ).fetchone()
    return bool(row and row["blocked_until"] and row["blocked_until"] > now)


def record_login_failure(request: Request, settings: Settings) -> None:
    now = int(time.time())
    key = keyed_identifier(client_ip(request, settings), settings.session_secret)
    with transaction(settings.database_path) as connection:
        connection.execute(
            """
            DELETE FROM login_attempts
            WHERE window_started_at < ?
              AND (blocked_until IS NULL OR blocked_until <= ?)
            """,
            (now - settings.login_window_seconds, now),
        )
        row = connection.execute(
            "SELECT failure_count, window_started_at FROM login_attempts WHERE client_key = ?",
            (key,),
        ).fetchone()
        if row is None or now - row["window_started_at"] >= settings.login_window_seconds:
            failure_count = 1
            window_started_at = now
        else:
            failure_count = row["failure_count"] + 1
            window_started_at = row["window_started_at"]
        blocked_until = (
            now + settings.login_window_seconds
            if failure_count >= settings.login_max_attempts
            else None
        )
        connection.execute(
            """
            INSERT INTO login_attempts(client_key, failure_count, window_started_at, blocked_until)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(client_key) DO UPDATE SET
              failure_count = excluded.failure_count,
              window_started_at = excluded.window_started_at,
              blocked_until = excluded.blocked_until
            """,
            (key, failure_count, window_started_at, blocked_until),
        )


def clear_login_failures(request: Request, settings: Settings) -> None:
    key = keyed_identifier(client_ip(request, settings), settings.session_secret)
    with transaction(settings.database_path) as connection:
        connection.execute("DELETE FROM login_attempts WHERE client_key = ?", (key,))
