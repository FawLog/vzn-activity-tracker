"""Versioned HTTP API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from ..config import Settings
from ..database import database_is_ready
from ..schemas import EventCreate, LoginRequest, PlayerCreate
from ..security import verify_password
from ..services import records
from ..services.sessions import (
    clear_login_failures,
    create_session,
    destroy_session,
    load_session,
    login_is_blocked,
    record_login_failure,
    require_admin,
    require_csrf,
    rotate_authenticated_session,
)


def create_api_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/health")
    async def health() -> dict[str, object]:
        ready, migration_version = database_is_ready(settings.database_path)
        if not ready:
            raise HTTPException(status_code=503, detail="Database unavailable")
        return {"status": "ok", "database": "ready", "migration_version": migration_version}

    @router.get("/auth/csrf")
    async def csrf(request: Request, response: Response) -> dict[str, object]:
        session = load_session(request, settings)
        if session is None:
            session = create_session(settings, response)
        return {"csrf_token": session.csrf_token, "authenticated": session.is_authenticated}

    @router.get("/auth/session")
    async def session_status(request: Request) -> dict[str, object]:
        session = load_session(request, settings)
        return {
            "authenticated": bool(session and session.is_authenticated),
            "csrf_token": session.csrf_token if session else None,
        }

    @router.post("/auth/login")
    async def login(request: Request, response: Response, payload: LoginRequest) -> dict[str, object]:
        session = load_session(request, settings)
        if session is None:
            raise HTTPException(status_code=403, detail="Start a session before signing in")
        require_csrf(request, session)
        if login_is_blocked(request, settings):
            raise HTTPException(status_code=429, detail="Too many sign-in attempts. Try again later")
        if not verify_password(payload.password, settings.admin_password_hash):
            record_login_failure(request, settings)
            raise HTTPException(status_code=401, detail="Invalid credentials")
        clear_login_failures(request, settings)
        authenticated = rotate_authenticated_session(settings, response, session)
        return {"authenticated": True, "csrf_token": authenticated.csrf_token}

    @router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(request: Request, response: Response) -> Response:
        session = require_admin(request, settings)
        require_csrf(request, session)
        destroy_session(settings, response, session)
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @router.get("/overview")
    async def get_overview(request: Request) -> dict[str, object]:
        require_admin(request, settings)
        return records.overview(settings.database_path)

    @router.get("/players")
    async def get_players(
        request: Request,
        q: str = Query(default="", max_length=80),
        sort: str = Query(default="nickname"),
        direction: str = Query(default="asc", pattern="^(asc|desc)$"),
    ) -> dict[str, object]:
        require_admin(request, settings)
        return {"items": records.list_players(settings.database_path, query=q, sort=sort, direction=direction)}

    @router.post("/players", status_code=status.HTTP_201_CREATED)
    async def post_player(request: Request, payload: PlayerCreate) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return records.create_player(settings.database_path, payload)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/players/{fid}")
    async def get_player(request: Request, fid: str) -> dict[str, object]:
        require_admin(request, settings)
        player = records.get_player(settings.database_path, fid)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        return player

    @router.get("/events")
    async def get_events(
        request: Request,
        sort: str = Query(default="occurred_on"),
        direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    ) -> dict[str, object]:
        require_admin(request, settings)
        return {"items": records.list_events(settings.database_path, sort=sort, direction=direction)}

    @router.post("/events", status_code=status.HTTP_201_CREATED)
    async def post_event(request: Request, payload: EventCreate) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        return records.create_event(settings.database_path, payload)

    @router.get("/events/{event_id}")
    async def get_event(request: Request, event_id: str) -> dict[str, object]:
        require_admin(request, settings)
        event = records.get_event(settings.database_path, event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return event

    @router.get("/rankings")
    async def get_rankings(request: Request) -> dict[str, object]:
        require_admin(request, settings)
        return {
            "categories": [
                {"id": "contribution", "status": "unavailable"},
                {"id": "attendance", "status": "unavailable"},
                {"id": "reliability", "status": "unavailable"},
            ],
            "message": "Rankings require complete, verified event data.",
        }

    @router.get("/admin/audit")
    async def get_audit(request: Request) -> dict[str, object]:
        require_admin(request, settings)
        return {"items": records.list_audit(settings.database_path)}

    return router
