from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import threading
from typing import Any

import numpy as np

from app.core.config import get_settings

try:
    import faiss
except ImportError:
    faiss = None


@dataclass(frozen=True)
class SemanticSearchHit:
    appid: str
    similarity: float


@dataclass(frozen=True)
class FaissShard:
    index_path: Path
    mapping_path: Path
    vector_count: int


def normalize_vector(vector: list[float] | np.ndarray | str, dimensions: int) -> np.ndarray:
    if isinstance(vector, str):
        vector = json.loads(vector)
    array = np.asarray(vector, dtype="float32")
    if array.ndim != 1:
        raise ValueError("Embedding vector must be one-dimensional.")
    if array.shape[0] != dimensions:
        raise ValueError(
            f"Embedding vector dimensions mismatch. Expected {dimensions}, got {array.shape[0]}."
        )

    norm = np.linalg.norm(array)
    if norm <= 0:
        raise ValueError("Embedding vector norm must be positive.")
    return array / norm


class FaissSemanticIndex:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded = False
        self._manifest: dict[str, Any] = {}
        self._shards: list[FaissShard] = []

    def _ensure_dependency(self) -> None:
        if faiss is None:
            raise RuntimeError(
                "FAISS is not installed. Install backend requirements before using semantic retrieval."
            )

    def _load_single_index_layout(self, settings) -> list[FaissShard]:
        missing = [
            str(path)
            for path in (settings.faiss_index_path, settings.faiss_mapping_path, settings.faiss_manifest_path)
            if not path.exists()
        ]
        if missing:
            raise RuntimeError(
                "FAISS artifacts are missing. Rebuild the local semantic index first. "
                f"Missing: {', '.join(missing)}"
            )

        appids = json.loads(settings.faiss_mapping_path.read_text(encoding="utf-8"))
        if not isinstance(appids, list) or not all(isinstance(appid, str) for appid in appids):
            raise RuntimeError("FAISS appid mapping artifact is invalid.")

        return [
            FaissShard(
                index_path=settings.faiss_index_path,
                mapping_path=settings.faiss_mapping_path,
                vector_count=len(appids),
            )
        ]

    def _load_sharded_layout(self, manifest: dict[str, Any], artifact_dir: Path) -> list[FaissShard]:
        raw_shards = manifest.get("shards")
        if not isinstance(raw_shards, list) or not raw_shards:
            raise RuntimeError("FAISS manifest is missing shard metadata.")

        shards: list[FaissShard] = []
        for raw_shard in raw_shards:
            index_file = raw_shard.get("index_file")
            mapping_file = raw_shard.get("mapping_file")
            vector_count = int(raw_shard.get("vector_count") or 0)
            if not index_file or not mapping_file or vector_count <= 0:
                raise RuntimeError("FAISS shard metadata is invalid.")

            shard = FaissShard(
                index_path=artifact_dir / str(index_file),
                mapping_path=artifact_dir / str(mapping_file),
                vector_count=vector_count,
            )
            if not shard.index_path.exists() or not shard.mapping_path.exists():
                raise RuntimeError(
                    f"FAISS shard artifact is missing: {shard.index_path} or {shard.mapping_path}"
                )
            shards.append(shard)
        return shards

    def load(self) -> None:
        if self._loaded:
            return

        with self._lock:
            if self._loaded:
                return

            self._ensure_dependency()
            settings = get_settings()
            if not settings.faiss_manifest_path.exists():
                raise RuntimeError(
                    "FAISS manifest is missing. Rebuild the local semantic index first."
                )

            manifest = json.loads(settings.faiss_manifest_path.read_text(encoding="utf-8"))
            if manifest.get("shards"):
                shards = self._load_sharded_layout(manifest, settings.faiss_artifact_dir)
            else:
                shards = self._load_single_index_layout(settings)

            dimensions = int(manifest.get("dimensions") or settings.openai_embedding_dimensions)
            if dimensions != settings.openai_embedding_dimensions:
                raise RuntimeError(
                    "FAISS artifact mismatch: manifest dimensions do not match configured embedding dimensions."
                )

            self._manifest = manifest
            self._shards = shards
            self._loaded = True

    def _search_shard(
        self,
        shard: FaissShard,
        normalized_query: np.ndarray,
        top_k: int,
        dimensions: int,
    ) -> list[SemanticSearchHit]:
        index = faiss.read_index(str(shard.index_path))
        if getattr(index, "d", dimensions) != dimensions:
            raise RuntimeError(
                f"FAISS shard dimension mismatch in {shard.index_path.name}."
            )

        appids = json.loads(shard.mapping_path.read_text(encoding="utf-8"))
        if len(appids) != index.ntotal:
            raise RuntimeError(
                f"FAISS shard mapping mismatch in {shard.mapping_path.name}."
            )

        query_matrix = normalized_query.reshape(1, -1)
        scores, indices = index.search(query_matrix, min(top_k, len(appids)))

        hits: list[SemanticSearchHit] = []
        for row_index, score in zip(indices[0], scores[0], strict=False):
            if row_index < 0:
                continue
            hits.append(
                SemanticSearchHit(
                    appid=str(appids[int(row_index)]),
                    similarity=float(score),
                )
            )
        return hits

    def search(self, query_embedding: list[float], top_k: int) -> list[SemanticSearchHit]:
        if top_k <= 0:
            return []

        self.load()
        settings = get_settings()
        normalized_query = normalize_vector(query_embedding, settings.openai_embedding_dimensions)

        merged_hits: list[SemanticSearchHit] = []
        for shard in self._shards:
            merged_hits.extend(
                self._search_shard(
                    shard,
                    normalized_query,
                    top_k,
                    settings.openai_embedding_dimensions,
                )
            )

        merged_hits.sort(key=lambda hit: hit.similarity, reverse=True)
        return merged_hits[:top_k]

    @property
    def manifest(self) -> dict[str, Any]:
        self.load()
        return dict(self._manifest)


@lru_cache(maxsize=1)
def get_faiss_semantic_index() -> FaissSemanticIndex:
    return FaissSemanticIndex()


def preload_faiss_semantic_index() -> None:
    get_faiss_semantic_index().load()
