from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from app.core.config import get_settings
from app.core.supabase import get_supabase_client
from app.schemas.steam import SteamAccountResponse, SteamOwnedGame, SteamSyncResult


STEAM_OWNED_GAMES_URL = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"


@dataclass(frozen=True)
class SteamAccountRow:
    user_id: str
    steam_id: str
    profile_url: str
    ownership_sync_status: str
    ownership_sync_error: str | None
    owned_game_count: int
    last_sync_at: str | None


def build_steam_profile_url(steam_id: str) -> str:
    return f"https://steamcommunity.com/profiles/{steam_id}"


def _steam_request(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_owned_games_from_steam(steam_id: str) -> SteamSyncResult:
    settings = get_settings()
    if not settings.steam_web_api_key:
        return SteamSyncResult(status="error", error="STEAM_WEB_API_KEY is not configured.")

    query = urlencode(
        {
            "key": settings.steam_web_api_key,
            "steamid": steam_id,
            "include_appinfo": 1,
            "include_played_free_games": 1,
            "format": "json",
        }
    )

    try:
        payload = _steam_request(f"{STEAM_OWNED_GAMES_URL}?{query}")
    except HTTPError as exc:
        return SteamSyncResult(status="error", error=f"Steam API returned HTTP {exc.code}.")
    except URLError as exc:
        return SteamSyncResult(status="error", error=f"Steam API request failed: {exc.reason}.")
    except Exception as exc:
        return SteamSyncResult(status="error", error=f"Steam API request failed: {exc}")

    response = payload.get("response") or {}
    games = response.get("games")
    if games is None:
        return SteamSyncResult(
            status="private_or_unavailable",
            error="Owned games are private or unavailable from Steam.",
        )

    owned_games: list[SteamOwnedGame] = []
    for raw_game in games:
        last_played = raw_game.get("rtime_last_played")
        last_played_at = None
        if isinstance(last_played, int) and last_played > 0:
            last_played_at = datetime.fromtimestamp(last_played, UTC).isoformat()

        owned_games.append(
            SteamOwnedGame(
                appid=str(raw_game["appid"]),
                name=raw_game.get("name"),
                playtimeForever=raw_game.get("playtime_forever"),
                lastPlayedAt=last_played_at,
            )
        )

    return SteamSyncResult(status="synced", ownedGames=owned_games)


def fetch_steam_account(user_id: str) -> SteamAccountResponse:
    supabase = get_supabase_client()
    response = (
        supabase.table("user_steam_accounts")
        .select("*")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return SteamAccountResponse(linked=False)

    row = rows[0]
    return SteamAccountResponse(
        linked=True,
        steamId=row.get("steam_id"),
        profileUrl=row.get("profile_url"),
        ownershipSyncStatus=row.get("ownership_sync_status"),
        ownershipSyncError=row.get("ownership_sync_error"),
        ownedGameCount=row.get("owned_game_count") or 0,
        lastSyncAt=row.get("last_sync_at"),
    )


def fetch_owned_appids_for_user(user_id: str) -> set[str]:
    supabase = get_supabase_client()
    response = (
        supabase.table("user_owned_games")
        .select("appid")
        .eq("user_id", user_id)
        .execute()
    )
    return {
        str(row["appid"])
        for row in (response.data or [])
        if row.get("appid")
    }


def _replace_owned_games(user_id: str, steam_id: str, games: list[SteamOwnedGame]) -> None:
    supabase = get_supabase_client()
    supabase.table("user_owned_games").delete().eq("user_id", user_id).execute()

    if not games:
        return

    rows = [
        {
            "user_id": user_id,
            "steam_id": steam_id,
            "appid": game.appid,
            "name": game.name,
            "playtime_forever": game.playtimeForever,
            "last_played_at": game.lastPlayedAt,
        }
        for game in games
    ]

    batch_size = 500
    for index in range(0, len(rows), batch_size):
        supabase.table("user_owned_games").upsert(
            rows[index : index + batch_size],
            on_conflict="user_id,appid",
        ).execute()


def link_steam_account(user_id: str, steam_id: str) -> SteamAccountResponse:
    supabase = get_supabase_client()
    existing_user_response = (
        supabase.table("user_steam_accounts")
        .select("steam_id,owned_game_count")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    existing_user_rows = existing_user_response.data or []
    previous_steam_id = str(existing_user_rows[0]["steam_id"]) if existing_user_rows else None

    existing_steam_response = (
        supabase.table("user_steam_accounts")
        .select("user_id")
        .eq("steam_id", steam_id)
        .limit(1)
        .execute()
    )
    existing_rows = existing_steam_response.data or []
    if existing_rows and existing_rows[0]["user_id"] != user_id:
        raise ValueError("This Steam account is already linked to another user.")

    profile_url = build_steam_profile_url(steam_id)
    supabase.table("user_steam_accounts").upsert(
        {
            "user_id": user_id,
            "steam_id": steam_id,
            "profile_url": profile_url,
            "ownership_sync_status": "pending",
            "ownership_sync_error": None,
        },
        on_conflict="user_id",
    ).execute()

    sync_result = fetch_owned_games_from_steam(steam_id)
    if sync_result.status == "synced":
        _replace_owned_games(user_id, steam_id, sync_result.ownedGames)
        supabase.table("user_steam_accounts").update(
            {
                "steam_id": steam_id,
                "profile_url": profile_url,
                "ownership_sync_status": "synced",
                "ownership_sync_error": None,
                "owned_game_count": len(sync_result.ownedGames),
                "last_sync_at": datetime.now(UTC).isoformat(),
            }
        ).eq("user_id", user_id).execute()
    else:
        if previous_steam_id and previous_steam_id != steam_id:
            supabase.table("user_owned_games").delete().eq("user_id", user_id).execute()
        supabase.table("user_steam_accounts").update(
            {
                "steam_id": steam_id,
                "profile_url": profile_url,
                "ownership_sync_status": sync_result.status,
                "ownership_sync_error": sync_result.error,
                "owned_game_count": 0 if previous_steam_id and previous_steam_id != steam_id else existing_user_rows[0].get("owned_game_count", 0) if existing_user_rows else 0,
                "last_sync_at": datetime.now(UTC).isoformat(),
            }
        ).eq("user_id", user_id).execute()

    return fetch_steam_account(user_id)
