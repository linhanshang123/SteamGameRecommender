from fastapi import APIRouter, Header, HTTPException

from app.schemas.recommendation import (
    HistoryEntry,
    RecommendationRequest,
    RecommendationResponse,
    RecommendationSessionResponse,
)
from app.services.recommendation.service import (
    create_recommendation_session,
    get_recommendation_history,
    get_recommendation_session,
)

router = APIRouter()


def require_user_id(user_id: str | None) -> str:
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing authenticated user context.")
    return user_id


@router.post("/recommendations", response_model=RecommendationResponse)
def create_recommendation(
    request: RecommendationRequest,
    x_user_id: str | None = Header(default=None),
) -> RecommendationResponse:
    try:
        return create_recommendation_session(request.prompt, require_user_id(x_user_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get(
    "/recommendations/{session_id}",
    response_model=RecommendationSessionResponse,
)
def read_recommendation_session(
    session_id: str,
    x_user_id: str | None = Header(default=None),
) -> RecommendationSessionResponse:
    try:
        return get_recommendation_session(session_id, require_user_id(x_user_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/history", response_model=list[HistoryEntry])
def read_history(
    x_user_id: str | None = Header(default=None),
) -> list[HistoryEntry]:
    try:
        return get_recommendation_history(require_user_id(x_user_id))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
