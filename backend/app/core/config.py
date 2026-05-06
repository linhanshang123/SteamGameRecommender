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


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    openai_api_key: str
    openai_embedding_model: str
    openai_embedding_dimensions: int
    clerk_secret_key: str
    cors_origins: list[str]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    raw_origins = os.getenv(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    cors_origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

    return Settings(
        supabase_url=os.getenv("SUPABASE_URL", ""),
        supabase_key=os.getenv("SUPABASE_KEY", ""),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large"),
        openai_embedding_dimensions=parse_int_env("OPENAI_EMBEDDING_DIMENSIONS", 3072),
        clerk_secret_key=os.getenv("CLERK_SECRET_KEY", ""),
        cors_origins=cors_origins,
    )
