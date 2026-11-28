"""Versioned HTTP API and group-scoped authorization boundaries."""

from __future__ import annotations

import asyncio
import os
import re
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from ..config import Settings
from ..database import database_is_ready
from ..schemas import (
    AllianceCreate,
    AllianceSyncSettingsUpdate,
    AllianceUpdate,
    EventCreate,
    GroupCreate,
    GroupUpdate,
    LoginRequest,
    PlayerCreate,
    WhiteoutStatsConnectionConfirm,
    WhiteoutStatsPreviewRequest,
)
from ..security import verify_password
from ..services import records, event_editor, vision_ocr, analytics, calendar
from ..services.event_editor import SessionCreate, SessionSave
from ..services import groups
from ..services import whiteoutstats, state_calendar, calendar_templates
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


class EventManagement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["delete","reopen","date","delete_session"]
    confirmed: bool
    occurred_on: date | None = None
    session_id: str | None = None


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


def create_api_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    async def initial_sync(group: dict[str, object]) -> dict[str, object]:
        if not settings.whiteoutstats_api_key:
            return {"status": "not_configured", "message": "Synchronization is not configured"}
        alliances = groups.list_alliances(settings.database_path, str(group["id"]))
        if not alliances:
            return {"status": "failed", "message": "Primary alliance was not persisted"}
        return (
            await asyncio.to_thread(
                whiteoutstats.sync_alliance,
                settings.database_path,
                settings,
                str(group["id"]),
                str(alliances[0]["id"]),
                trigger_type="initial",
            )
        ).payload()

    def confirmed_aid(token: str | None, *, state_id: str, tag: str, expected_aid: str | None = None) -> str | None:
        if not settings.whiteoutstats_api_key:
            return None
        return whiteoutstats.confirmed_preview_aid(
            settings,
            token,
            state_id=state_id,
            tag=tag,
            expected_aid=expected_aid,
        )

    @router.get("/health")
    async def health() -> dict[str, object]:
        ready, migration_version = database_is_ready(settings.database_path)
        if not ready:
            raise HTTPException(status_code=503, detail="Database unavailable")
        return {"status": "ok", "database": "ready", "migration_version": migration_version}

    @router.get("/version")
    async def version(request: Request, response: Response) -> dict[str, object]:
        require_admin(request, settings)
        response.headers["Cache-Control"] = "no-store"
        tag = os.getenv("VZN_IMAGE_TAG", "")
        match = re.fullmatch(r"ci-([0-9a-f]{40})", tag)
        return {"sha": match.group(1) if match else None}

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
            aid = confirmed_aid(
                payload.whiteoutstats_preview_token,
                state_id=payload.primary_alliance_state_id,
                tag=payload.primary_alliance_tag,
            )
            group = groups.create_group(
                settings.database_path,
                payload,
                onboarding=True,
                sync_enabled=bool(settings.whiteoutstats_api_key),
                whiteoutstats_alliance_id=aid,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        group["initial_sync"] = await initial_sync(group)
        return group

    @router.get("/groups")
    async def get_groups(request: Request) -> dict[str, object]:
        require_admin(request, settings)
        return {"items": groups.list_groups(settings.database_path)}

    @router.post("/groups", status_code=status.HTTP_201_CREATED)
    async def post_group(request: Request, payload: GroupCreate) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            aid = confirmed_aid(
                payload.whiteoutstats_preview_token,
                state_id=payload.primary_alliance_state_id,
                tag=payload.primary_alliance_tag,
            )
            group = groups.create_group(
                settings.database_path,
                payload,
                sync_enabled=bool(settings.whiteoutstats_api_key),
                whiteoutstats_alliance_id=aid,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        group["initial_sync"] = await initial_sync(group)
        return group

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

    @router.post("/whiteoutstats/alliances/preview")
    async def post_whiteoutstats_preview(
        request: Request,
        payload: WhiteoutStatsPreviewRequest,
    ) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        return await asyncio.to_thread(whiteoutstats.preview_alliance, settings, payload.state_id, payload.tag)

    @router.post("/groups/{group_id}/alliances", status_code=status.HTTP_201_CREATED)
    async def post_alliance(request: Request, group_id: str, payload: AllianceCreate) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            aid = confirmed_aid(payload.whiteoutstats_preview_token, state_id=payload.state_id, tag=payload.tag)
            alliance = groups.create_additional_alliance(
                settings.database_path,
                group_id,
                payload,
                sync_enabled=bool(settings.whiteoutstats_api_key),
                whiteoutstats_alliance_id=aid,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if alliance is None:
            raise _not_found("Group not found")
        if settings.whiteoutstats_api_key:
            alliance["initial_sync"] = (
                await asyncio.to_thread(
                    whiteoutstats.sync_alliance, settings.database_path, settings, group_id, str(alliance["id"]), trigger_type="initial"
                )
            ).payload()
        else:
            alliance["initial_sync"] = {"status": "not_configured", "message": "Synchronization is not configured"}
        return alliance

    @router.post("/groups/{group_id}/alliances/{alliance_id}/whiteoutstats/connect")
    async def post_alliance_connection(
        request: Request,
        group_id: str,
        alliance_id: str,
        payload: WhiteoutStatsConnectionConfirm,
    ) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        if not settings.whiteoutstats_api_key:
            raise HTTPException(status_code=409, detail="WhiteoutStats API key is not configured on the backend")
        alliance = groups.get_alliance(settings.database_path, group_id, alliance_id)
        if alliance is None:
            raise _not_found("Alliance not found in selected group")
        try:
            aid = confirmed_aid(
                payload.preview_token,
                state_id=str(alliance["state_id"]),
                tag=str(alliance["tag"]),
                expected_aid=str(alliance["whiteoutstats_alliance_id"]) if alliance["whiteoutstats_alliance_id"] else None,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        connected = groups.connect_whiteoutstats_alliance(
            settings.database_path,
            group_id,
            alliance_id,
            str(aid),
            sync_enabled=bool(settings.whiteoutstats_api_key),
        )
        if connected is None:
            raise _not_found("Alliance not found in selected group")
        connected["initial_sync"] = (
            await asyncio.to_thread(
                whiteoutstats.sync_alliance,
                settings.database_path,
                settings,
                group_id,
                alliance_id,
                trigger_type="initial",
            )
        ).payload()
        return connected

    @router.patch("/groups/{group_id}/alliances/{alliance_id}")
    async def patch_alliance(
        request: Request,
        group_id: str,
        alliance_id: str,
        payload: AllianceUpdate,
    ) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        existing = groups.get_alliance(settings.database_path, group_id, alliance_id)
        if existing is None:
            raise _not_found("Alliance not found in selected group")
        new_tag = payload.tag if payload.tag is not None else str(existing["tag"])
        new_state_id = payload.state_id if payload.state_id is not None else str(existing["state_id"])
        if existing["whiteoutstats_alliance_id"] and (new_tag != existing["tag"] or new_state_id != existing["state_id"]):
            if not settings.whiteoutstats_api_key:
                raise HTTPException(status_code=409, detail="WhiteoutStats API key is required to verify a State ID or tag change")
            try:
                confirmed_aid(
                    payload.whiteoutstats_preview_token,
                    state_id=new_state_id,
                    tag=new_tag,
                    expected_aid=str(existing["whiteoutstats_alliance_id"]),
                )
            except ValueError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
        try:
            alliance = groups.update_alliance(settings.database_path, group_id, alliance_id, payload)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if alliance is None:
            raise _not_found("Alliance not found in selected group")
        return alliance

    @router.get("/groups/{group_id}/alliances/{alliance_id}/sync")
    async def get_alliance_sync(request: Request, group_id: str, alliance_id: str) -> dict[str, object]:
        require_admin(request, settings)
        result = whiteoutstats.sync_status(
            settings.database_path, group_id, alliance_id, configured=bool(settings.whiteoutstats_api_key)
        )
        if result is None:
            raise _not_found("Alliance not found in selected group")
        return result

    @router.patch("/groups/{group_id}/alliances/{alliance_id}/sync")
    async def patch_alliance_sync(
        request: Request, group_id: str, alliance_id: str, payload: AllianceSyncSettingsUpdate
    ) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            result = whiteoutstats.update_sync_settings(
                settings.database_path, group_id, alliance_id, enabled=payload.sync_enabled, configured=bool(settings.whiteoutstats_api_key)
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if result is None:
            raise _not_found("Alliance not found in selected group")
        return result

    @router.post("/groups/{group_id}/alliances/{alliance_id}/sync")
    async def post_alliance_sync(request: Request, group_id: str, alliance_id: str) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        result = await asyncio.to_thread(
            whiteoutstats.sync_alliance, settings.database_path, settings, group_id, alliance_id, trigger_type="manual"
        )
        return result.payload()

    @router.get("/groups/{group_id}/state-calendar-profiles")
    async def get_state_calendar_profiles(request: Request, group_id: str):
        require_admin(request, settings)
        try:
            return state_calendar.state_dates(settings.database_path, group_id)
        except LookupError as error:
            raise _not_found(str(error)) from error

    @router.put("/groups/{group_id}/state-calendar-profiles/{state_id}")
    async def put_state_calendar_profile(request: Request, group_id: str, state_id: str, payload: state_calendar.StateDateUpdate):
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return state_calendar.update_date(settings.database_path, group_id, state_id, payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/groups/{group_id}/calendar/templates")
    async def get_calendar_templates(request: Request, group_id: str):
        require_admin(request, settings)
        try:
            return calendar_templates.list_templates(settings.database_path, group_id)
        except LookupError as error:
            raise _not_found(str(error)) from error

    @router.post("/groups/{group_id}/calendar/templates", status_code=201)
    async def post_calendar_template(request: Request, group_id: str, payload: calendar_templates.TemplateCreate):
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return calendar_templates.create_template(settings.database_path, group_id, payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.delete("/groups/{group_id}/calendar/templates/{template_id}")
    async def delete_calendar_template(request: Request, group_id: str, template_id: str):
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return calendar_templates.delete_template(settings.database_path, group_id, template_id)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/groups/{group_id}/calendar/bear-schedule", status_code=201)
    async def post_bear_schedule(request: Request,group_id: str,payload: calendar.BearScheduleCreate):
        session=require_admin(request,settings)
        require_csrf(request,session)
        try:
            return calendar.create_bear_schedule(settings.database_path,group_id,payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @router.get("/groups/{group_id}/calendar")
    async def get_calendar(request: Request, group_id: str, start: date, end: date) -> dict[str, object]:
        require_admin(request, settings)
        try:
            return calendar.list_occurrences(settings.database_path, group_id, start, end)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/groups/{group_id}/calendar", status_code=201)
    async def post_calendar(request: Request, group_id: str, payload: calendar.CalendarCreate) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return calendar.create(settings.database_path, group_id, payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/groups/{group_id}/calendar/cycles", status_code=201)
    async def post_calendar_cycle(request: Request, group_id: str, payload: calendar.CalendarCycleCreate):
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return calendar.create_cycle(settings.database_path,group_id,payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @router.get("/groups/{group_id}/calendar/cycles/{cycle_id}")
    async def get_calendar_cycle(request: Request, group_id: str, cycle_id: str):
        require_admin(request, settings)
        try:
            return calendar.get_cycle(settings.database_path,group_id,cycle_id)
        except LookupError as error:
            raise _not_found(str(error)) from error

    @router.get("/groups/{group_id}/calendar/cycles/{cycle_id}/workspace")
    async def get_cycle_workspace(request: Request,group_id: str,cycle_id: str):
        require_admin(request,settings)
        try:
            return calendar.get_cycle_workspace(settings.database_path,group_id,cycle_id)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @router.post("/groups/{group_id}/calendar/cycles/{cycle_id}/workspace")
    async def post_cycle_workspace(request: Request,group_id: str,cycle_id: str,payload: calendar.CycleWorkspaceStart):
        require_csrf(request,require_admin(request,settings))
        try:
            return calendar.start_cycle_workspace(settings.database_path,group_id,cycle_id,payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @router.get("/groups/{group_id}/calendar/cycles/{cycle_id}/reconcile")
    async def get_cycle_reconcile(request: Request,group_id: str,cycle_id: str,following: bool=False,interval_days: int|None=None):
        require_admin(request,settings)
        try:
            return calendar.preview_cycle_reconcile(settings.database_path,group_id,cycle_id,following,interval_days)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @router.post("/groups/{group_id}/calendar/cycles/{cycle_id}/reconcile")
    async def post_cycle_reconcile(request: Request,group_id: str,cycle_id: str,payload: calendar.CycleReconcile):
        session=require_admin(request,settings)
        require_csrf(request,session)
        try:
            return calendar.reconcile_cycle(settings.database_path,group_id,cycle_id,payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @router.put("/groups/{group_id}/calendar/{occurrence_id}")
    async def put_calendar(request: Request, group_id: str, occurrence_id: str, payload: calendar.CalendarUpdate) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return calendar.update(settings.database_path, group_id, occurrence_id, payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/groups/{group_id}/calendar/{occurrence_id}/event-link")
    async def get_calendar_event_link(request: Request,group_id: str,occurrence_id: str):
        require_admin(request,settings)
        try:
            return calendar.event_link(settings.database_path,group_id,occurrence_id)
        except LookupError as error:
            raise _not_found(str(error)) from error

    @router.put("/groups/{group_id}/calendar/{occurrence_id}/event-link")
    async def put_calendar_event_link(request: Request,group_id: str,occurrence_id: str,payload: calendar.CalendarEventLink):
        require_csrf(request,require_admin(request,settings))
        try:
            return calendar.set_event_link(settings.database_path,group_id,occurrence_id,payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @router.put("/groups/{group_id}/calendar/{occurrence_id}/entry-group")
    async def put_calendar_entry_group(request: Request,group_id: str,occurrence_id: str,payload: calendar.EntryGrouping):
        require_csrf(request,require_admin(request,settings))
        try:
            return calendar.set_entry_grouping(settings.database_path,group_id,occurrence_id,payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @router.post("/groups/{group_id}/calendar/{occurrence_id}/start-entry")
    async def post_calendar_start_entry(request: Request,group_id: str,occurrence_id: str,payload: calendar.CalendarEntryStart):
        require_csrf(request,require_admin(request,settings))
        try:
            return calendar.start_entry(settings.database_path,group_id,occurrence_id,payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @router.post("/groups/{group_id}/calendar/{occurrence_id}/draft",status_code=201)
    async def post_calendar_draft(request: Request,group_id: str,occurrence_id: str,payload: calendar.CalendarDraftCreate):
        require_csrf(request,require_admin(request,settings))
        try:
            return calendar.create_linked_draft(settings.database_path,group_id,occurrence_id,payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @router.get("/groups/{group_id}/calendar/{occurrence_id}/bear-cycles")
    async def get_calendar_bear_cycles(request: Request,group_id: str,occurrence_id: str,cycle_date: date):
        require_admin(request,settings)
        try:
            return calendar.draft_bear_cycles(settings.database_path,group_id,occurrence_id,cycle_date)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409,detail=str(error)) from error

    @router.get("/groups/{group_id}/events/{event_id}/calendar")
    async def get_event_calendar(request: Request,group_id: str,event_id: str):
        require_admin(request,settings)
        try:
            return calendar.event_schedules(settings.database_path,group_id,event_id)
        except LookupError as error:
            raise _not_found(str(error)) from error

    @router.get("/groups/{group_id}/calendar/{occurrence_id}/future")
    async def get_calendar_future(request: Request, group_id: str, occurrence_id: str) -> dict[str, object]:
        require_admin(request, settings)
        try:
            return calendar.preview_future(settings.database_path, group_id, occurrence_id)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/groups/{group_id}/calendar/{occurrence_id}/future")
    async def post_calendar_future(request: Request, group_id: str, occurrence_id: str, payload: calendar.CalendarFutureChange) -> dict[str, object]:
        session = require_admin(request, settings)
        require_csrf(request, session)
        try:
            return calendar.change_future(settings.database_path, group_id, occurrence_id, payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/groups/{group_id}/overview")
    async def get_overview(request: Request, group_id: str, alliance_id: str | None = Query(default=None, max_length=64)) -> dict[str, object]:
        require_admin(request, settings)
        try:
            overview = records.overview(settings.database_path, group_id, alliance_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
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
        limit: int = Query(default=100, ge=1, le=250),
        offset: int = Query(default=0, ge=0),
        include_aliases: bool = False,
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
                limit=limit,
                offset=offset,
                include_aliases=include_aliases,
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if players is None:
            raise _not_found("Group not found")
        return players

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

    @router.post("/groups/{group_id}/events/{event_id}/manage")
    async def manage_event(request: Request, group_id: str, event_id: str, payload: EventManagement):
        require_csrf(request, require_admin(request, settings))
        try:
            event_editor.manage_event(settings.database_path, group_id, event_id, payload.action, payload.confirmed, payload.occurred_on, payload.session_id)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"status":"ok"}

    @router.get("/groups/{group_id}/events/{event_id}/editor")
    async def get_event_editor(request: Request, group_id: str, event_id: str):
        require_admin(request, settings)
        try:
            return event_editor.read(settings.database_path, group_id, event_id)
        except LookupError as error:
            raise _not_found(str(error)) from error

    @router.post("/groups/{group_id}/events/{event_id}/sessions", status_code=201)
    async def create_event_session(request: Request, group_id: str, event_id: str, payload: SessionCreate):
        require_csrf(request, require_admin(request, settings))
        try:
            return event_editor.create_session(settings.database_path, group_id, event_id, payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.put("/groups/{group_id}/events/{event_id}/sessions/{session_id}")
    async def save_event_session(request: Request, group_id: str, event_id: str, session_id: str, payload: SessionSave):
        require_csrf(request, require_admin(request, settings))
        try:
            return event_editor.save(settings.database_path, group_id, event_id, session_id, payload)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/groups/{group_id}/events/{event_id}/publish")
    async def publish_event(request: Request, group_id: str, event_id: str, bear_cycle_complete: bool = False, completion: event_editor.CompletionReview | None = None):
        require_csrf(request, require_admin(request, settings))
        try:
            return event_editor.publish(settings.database_path, group_id, event_id, bear_cycle_complete, completion)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/ocr/status")
    async def ocr_status(request: Request):
        require_admin(request, settings)
        return {"configured": bool(settings.google_vision_api_key or settings.google_application_credentials), "provider": "google_vision", "max_image_bytes": vision_ocr.MAX_IMAGE_BYTES}

    @router.post("/groups/{group_id}/events/{event_id}/sessions/{session_id}/ocr/preview")
    async def preview_ocr(request: Request, group_id: str, event_id: str, session_id: str):
        require_csrf(request, require_admin(request, settings))
        try:
            event_editor.check_ocr_scope(settings.database_path, group_id, event_id, session_id)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if not (settings.google_vision_api_key or settings.google_application_credentials):
            raise HTTPException(status_code=409, detail="Google Vision OCR is not configured")
        if request.headers.get("content-type", "").split(";")[0].lower() not in {"image/png", "image/jpeg"}:
            raise HTTPException(status_code=415, detail="Use a PNG or JPEG image")
        if vision_ocr.is_busy():
            raise HTTPException(status_code=429, detail="OCR is busy; try again after the current image completes")
        image = bytearray()
        async for chunk in request.stream():
            if len(image) + len(chunk) > vision_ocr.MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail="Image exceeds OCR upload limit")
            image.extend(chunk)
        try:
            return await asyncio.to_thread(vision_ocr.extract, bytes(image), settings.google_vision_api_key, settings.google_application_credentials)
        except vision_ocr.OcrError as error:
            raise HTTPException(status_code=error.status, detail=str(error)) from None

    @router.get("/groups/{group_id}/analytics")
    async def group_analytics(request: Request, group_id: str, start: date, end: date, alliance_id: str | None = None):
        require_admin(request, settings)
        try:
            return await asyncio.to_thread(analytics.report, settings.database_path, group_id, alliance_id, start, end)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/groups/{group_id}/alliances/{alliance_id}/analytics")
    async def alliance_analytics(request: Request, group_id: str, alliance_id: str, start: date, end: date):
        require_admin(request, settings)
        try:
            return await asyncio.to_thread(analytics.report, settings.database_path, group_id, alliance_id, start, end)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/groups/{group_id}/players/{fid}/activity")
    async def player_activity(request: Request, group_id: str, fid: str, start: date, end: date, alliance_id: str | None = None):
        require_admin(request, settings)
        try:
            return await asyncio.to_thread(analytics.report, settings.database_path, group_id, alliance_id, start, end, fid)
        except LookupError as error:
            raise _not_found(str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

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
