from __future__ import annotations

import html
import re

from openai import OpenAI

from app.core.config import Settings


TAG_RE = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
BROKEN_CHAR_RE = re.compile(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff\ufffd]")
MULTI_SPACE_RE = re.compile(r"\s+")


def clean_query_text(text: str) -> str:
    cleaned = html.unescape(text or "")
    cleaned = BROKEN_CHAR_RE.sub("", cleaned)
    cleaned = TAG_RE.sub(" ", cleaned)
    cleaned = URL_RE.sub(" ", cleaned)
    cleaned = MULTI_SPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def create_embedding_client(settings: Settings) -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for embedding generation.")
    return OpenAI(api_key=settings.openai_api_key)


def create_embeddings(
    texts: list[str],
    settings: Settings,
    client: OpenAI | None = None,
) -> list[list[float]]:
    cleaned_texts = [clean_query_text(text) for text in texts]
    if any(not text for text in cleaned_texts):
        raise ValueError("Embedding input text cannot be empty.")

    openai_client = client or create_embedding_client(settings)
    response = openai_client.embeddings.create(
        model=settings.openai_embedding_model,
        dimensions=settings.openai_embedding_dimensions,
        input=cleaned_texts,
        encoding_format="float",
    )
    return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]


def create_query_embedding(query: str, settings: Settings) -> list[float]:
    return create_embeddings([query], settings)[0]
