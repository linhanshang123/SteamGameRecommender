from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SteamLinkRequest(BaseModel):
    steamId: str

    @field_validator("steamId")
    @classmethod
    def validate_steam_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized.isdigit():
            raise ValueError("Steam ID must contain only digits.")
        if len(normalized) < 10:
            raise ValueError("Steam ID is too short.")
        return normalized


class SteamAccountResponse(BaseModel):
    linked: bool
    steamId: str | None = None
    profileUrl: str | None = None
    ownershipSyncStatus: str | None = None
    ownershipSyncError: str | None = None
    ownedGameCount: int = 0
    lastSyncAt: str | None = None


class SteamOwnedGame(BaseModel):
    appid: str
    name: str | None = None
    playtimeForever: int | None = None
    lastPlayedAt: str | None = None


class SteamSyncResult(BaseModel):
    status: str
    ownedGames: list[SteamOwnedGame] = Field(default_factory=list)
    error: str | None = None
