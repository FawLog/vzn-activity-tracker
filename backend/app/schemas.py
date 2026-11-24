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


class EventCreate(BaseModel):
    event_type: EventType
    occurred_on: date
    status: EventStatus = EventStatus.DRAFT


class ApiError(BaseModel):
    code: str
    message: str
