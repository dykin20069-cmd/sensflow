"""Typed response models for the public official Roblox endpoints."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RobloxModel(BaseModel):
    """Immutable Roblox payload with explicit API aliases."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)


class RobloxUser(RobloxModel):
    id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=64)


class UsernameLookupResponse(RobloxModel):
    data: tuple[RobloxUser, ...]


class RootPlace(RobloxModel):
    id: int = Field(gt=0)


class PublicGame(RobloxModel):
    universe_id: int = Field(alias="id", gt=0)
    name: str = Field(min_length=1, max_length=255)
    root_place: RootPlace = Field(alias="rootPlace")
    visits: int = Field(alias="placeVisits", ge=0)
    updated_at: datetime = Field(alias="updated")


class PublicGamesResponse(RobloxModel):
    data: tuple[PublicGame, ...]
    next_page_cursor: str | None = Field(default=None, alias="nextPageCursor")
