from fastapi import APIRouter, Header, HTTPException

from app.api.recommendations import require_user_id
from app.schemas.steam import SteamAccountResponse, SteamLinkRequest
from app.services.steam import fetch_steam_account, link_steam_account

router = APIRouter(prefix="/steam", tags=["steam"])


@router.get("/account", response_model=SteamAccountResponse)
def read_steam_account(
    x_user_id: str | None = Header(default=None),
) -> SteamAccountResponse:
    try:
        return fetch_steam_account(require_user_id(x_user_id))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/link", response_model=SteamAccountResponse)
def create_steam_link(
    request: SteamLinkRequest,
    x_user_id: str | None = Header(default=None),
) -> SteamAccountResponse:
    try:
        return link_steam_account(require_user_id(x_user_id), request.steamId)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
