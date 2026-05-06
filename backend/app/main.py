from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.recommendations import router as recommendations_router
from app.api.steam import router as steam_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="SteamRecommender Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(recommendations_router)
app.include_router(steam_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
