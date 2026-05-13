from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path


def load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def parse_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    openai_api_key: str
    openai_embedding_model: str
    openai_embedding_dimensions: int
    steam_web_api_key: str
    clerk_secret_key: str
    cors_origins: list[str]
    faiss_artifact_dir: Path
    faiss_index_path: Path
    faiss_mapping_path: Path
    faiss_manifest_path: Path
    faiss_preload_on_startup: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    backend_dir = Path(__file__).resolve().parents[2]
    raw_origins = os.getenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]
    raw_faiss_artifact_dir = os.getenv("FAISS_ARTIFACT_DIR", ".cache/faiss")
    faiss_artifact_dir = Path(raw_faiss_artifact_dir)
    if not faiss_artifact_dir.is_absolute():
        faiss_artifact_dir = backend_dir / faiss_artifact_dir

    return Settings(
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_key=os.getenv("SUPABASE_KEY", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
        openai_embedding_dimensions=parse_int_env("OPENAI_EMBEDDING_DIMENSIONS", 3072),
        steam_web_api_key=os.getenv("STEAM_WEB_API_KEY", ""),
        clerk_secret_key=os.getenv("CLERK_SECRET_KEY", ""),
        cors_origins=cors_origins,
        faiss_artifact_dir=faiss_artifact_dir,
        faiss_index_path=faiss_artifact_dir / "games.index",
        faiss_mapping_path=faiss_artifact_dir / "games_appids.json",
        faiss_manifest_path=faiss_artifact_dir / "manifest.json",
        faiss_preload_on_startup=parse_bool_env("FAISS_PRELOAD_ON_STARTUP", False),
    )
