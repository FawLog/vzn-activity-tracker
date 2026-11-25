"""Typed API contracts."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class EventType(StrEnum):
    SVS_PREPARATION = "svs_preparation"
    ALLIANCE_MOBILIZATION = "alliance_mobilization"
    ALLIANCE_SHOWDOWN = "alliance_showdown"
    FOUNDRY = "foundry"
    CANYON = "canyon"
    BEAR_TRAP = "bear_trap"
    ALLIANCE_CHAMPIONSHIP = "alliance_championship"
    WINTER_SIEGE = "winter_siege"
    SVS_BATTLE = "svs_battle"
    CASTLE_BATTLE = "castle_battle"
    FORTRESS_STRONGHOLD = "fortress_stronghold"


class EventStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)


class PlayerCreate(BaseModel):
    fid: str = Field(min_length=1, max_length=32)
    nickname: str = Field(min_length=1, max_length=80)

    @field_validator("fid", "nickname")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Value cannot be blank")
        return normalized


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    discord_server_id: str | None = Field(default=None, max_length=32)
    combined_statistics: bool = False
    primary_alliance_name: str = Field(min_length=1, max_length=120)
    primary_alliance_tag: str = Field(min_length=1, max_length=32)
    primary_alliance_state_id: str = Field(min_length=1, max_length=32)
    assign_legacy_events: bool = False
    confirm_legacy_assignment: bool = False

    @field_validator(
        "name",
        "discord_server_id",
        "primary_alliance_name",
        "primary_alliance_tag",
        "primary_alliance_state_id",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Value cannot be blank")
        return normalized


class GroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    discord_server_id: str | None = Field(default=None, max_length=32)
    combined_statistics: bool | None = None
    status: str | None = Field(default=None, pattern="^(active|archived)$")
    confirm_archive: bool = False

    @field_validator("name", "discord_server_id")
    @classmethod
    def normalize_group_update_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Value cannot be blank")
        return normalized


class AllianceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    tag: str = Field(min_length=1, max_length=32)
    state_id: str = Field(min_length=1, max_length=32)

    @field_validator("name", "tag", "state_id")
    @classmethod
    def normalize_alliance_text(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Value cannot be blank")
        return normalized


class AllianceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    tag: str | None = Field(default=None, min_length=1, max_length=32)
    state_id: str | None = Field(default=None, min_length=1, max_length=32)
    status: str | None = Field(default=None, pattern="^(active|archived)$")
    confirm_archive: bool = False

    @field_validator("name", "tag", "state_id")
    @classmethod
    def normalize_alliance_update_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Value cannot be blank")
        return normalized


class AllianceSyncSettingsUpdate(BaseModel):
    sync_enabled: bool


class EventCreate(BaseModel):
    event_type: EventType
    occurred_on: date
    status: EventStatus = EventStatus.DRAFT


class ApiError(BaseModel):
    code: str
    message: str
