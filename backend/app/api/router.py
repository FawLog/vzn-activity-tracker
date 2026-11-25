"""Versioned HTTP API and group-scoped authorization boundaries."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from ..config import Settings
from ..database import database_is_ready
from ..schemas import (
    AllianceCreate,
    AllianceUpdate,
    EventCreate,
    GroupCreate,
    GroupUpdate,
    LoginRequest,
    PlayerCreate,
)
from ..security import verify_password
from ..services import records
from ..services import groups
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


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


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
        return {"authenticated": bool(session and session.is_authenticated), "csrf_token": session.csrf_token if session else None}

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

    @router.get("/onboarding")
    async def get_onboarding(request: Request) -> dict[str, object]:
        require_admin(request, settings)
        return groups.onboarding_status(settings.database_path)

    @router.post("/onboarding/groups", status_code=status.HTTP_201_CREATED)
    async def post_onboarding_group(request: Request, payload: GroupCreate) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return groups.create_group(settings.database_path, payload, onboarding=True)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/groups")
    async def get_groups(request: Request) -> dict[str, object]:
        require_admin(request, settings)
        return {"items": groups.list_groups(settings.database_path)}

    @router.post("/groups", status_code=status.HTTP_201_CREATED)
    async def post_group(request: Request, payload: GroupCreate) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return groups.create_group(settings.database_path, payload)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/groups/{group_id}")
    async def get_group(request: Request, group_id: str) -> dict[str, object]:
        require_admin(request, settings)
        group = groups.get_group(settings.database_path, group_id)
        if group is None:
            raise _not_found("Group not found")
        return group

    @router.patch("/groups/{group_id}")
    async def patch_group(request: Request, group_id: str, payload: GroupUpdate) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            group = groups.update_group(settings.database_path, group_id, payload)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if group is None:
            raise _not_found("Group not found")
        return group

    @router.get("/groups/{group_id}/alliances")
    async def get_alliances(request: Request, group_id: str) -> dict[str, object]:
        require_admin(request, settings)
        alliances = groups.list_alliances(settings.database_path, group_id)
        if alliances is None:
            raise _not_found("Group not found")
        return {"items": alliances}

    @router.post("/groups/{group_id}/alliances", status_code=status.HTTP_201_CREATED)
    async def post_alliance(request: Request, group_id: str, payload: AllianceCreate) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            alliance = groups.create_additional_alliance(settings.database_path, group_id, payload)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if alliance is None:
            raise _not_found("Group not found")
        return alliance

    @router.patch("/groups/{group_id}/alliances/{alliance_id}")
    async def patch_alliance(
        request: Request,
        group_id: str,
        alliance_id: str,
        payload: AllianceUpdate,
    ) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            alliance = groups.update_alliance(settings.database_path, group_id, alliance_id, payload)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if alliance is None:
            raise _not_found("Alliance not found in selected group")
        return alliance

    @router.get("/groups/{group_id}/overview")
    async def get_overview(request: Request, group_id: str) -> dict[str, object]:
        require_admin(request, settings)
        overview = records.overview(settings.database_path, group_id)
        if overview is None:
            raise _not_found("Group not found")
        return overview

    @router.get("/groups/{group_id}/players")
    async def get_players(
        request: Request,
        group_id: str,
        alliance_id: str | None = Query(default=None, max_length=64),
        affiliation: str | None = Query(default=None, pattern="^(all|alliance|unconfirmed)$"),
        q: str = Query(default="", max_length=80),
        sort: str = Query(default="nickname"),
        direction: str = Query(default="asc", pattern="^(asc|desc)$"),
    ) -> dict[str, object]:
        require_admin(request, settings)
        try:
            players = records.list_players(
                settings.database_path,
                group_id,
                alliance_id=alliance_id,
                affiliation=affiliation,
                query=q,
                sort=sort,
                direction=direction,
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if players is None:
            raise _not_found("Group not found")
        return {"items": players}

    @router.post("/groups/{group_id}/players", status_code=status.HTTP_201_CREATED)
    async def post_player(request: Request, group_id: str, payload: PlayerCreate) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return records.create_player(settings.database_path, group_id, payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/groups/{group_id}/players/{fid}")
    async def get_player(request: Request, group_id: str, fid: str) -> dict[str, object]:
        require_admin(request, settings)
        player = records.get_player(settings.database_path, group_id, fid)
        if player is None:
            raise _not_found("Player not found in selected group")
        return player

    @router.get("/groups/{group_id}/alliances/{alliance_id}/events")
    async def get_events(
        request: Request,
        group_id: str,
        alliance_id: str,
        sort: str = Query(default="occurred_on"),
        direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    ) -> dict[str, object]:
        require_admin(request, settings)
        events = records.list_events(settings.database_path, group_id, alliance_id, sort=sort, direction=direction)
        if events is None:
            raise _not_found("Alliance not found in selected group")
        return {"items": events}

    @router.post("/groups/{group_id}/alliances/{alliance_id}/events", status_code=status.HTTP_201_CREATED)
    async def post_event(
        request: Request,
        group_id: str,
        alliance_id: str,
        payload: EventCreate,
    ) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return records.create_event(settings.database_path, group_id, alliance_id, payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/groups/{group_id}/events/{event_id}")
    async def get_event(request: Request, group_id: str, event_id: str) -> dict[str, object]:
        require_admin(request, settings)
        event = records.get_event(settings.database_path, group_id, event_id)
        if event is None:
            raise _not_found("Event not found in selected group")
        return event

    @router.get("/groups/{group_id}/rankings")
    async def get_rankings(request: Request, group_id: str) -> dict[str, object]:
        require_admin(request, settings)
        if groups.get_group(settings.database_path, group_id) is None:
            raise _not_found("Group not found")
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
