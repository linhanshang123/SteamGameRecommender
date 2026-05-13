from __future__ import annotations

import argparse
from datetime import UTC, datetime
import gc
import json
from pathlib import Path
import sys

import numpy as np
from supabase import create_client

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from app.services.recommendation.faiss_index import normalize_vector

try:
    import faiss
except ImportError as exc:
    raise RuntimeError("FAISS is not installed. Install backend requirements first.") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local FAISS artifacts from Supabase game embeddings.")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--shard-size", type=int, default=10000)
    parser.add_argument(
        "--index-kind",
        choices=("flat_ip", "sq_fp16"),
        default="flat_ip",
        help="FAISS index format. flat_ip is exact but RAM-heavier; sq_fp16 stays exhaustive with FP16 storage.",
    )
    return parser.parse_args()


def iter_embedding_rows(supabase, batch_size: int):
    last_appid: str | None = None

    while True:
        query = (
            supabase.table("games")
            .select("appid,embedding_vector")
            .not_.is_("embedding_vector", "null")
            .order("appid")
            .limit(batch_size)
        )
        if last_appid is not None:
            query = query.gt("appid", last_appid)

        response = query.execute()
        batch = response.data or []
        if not batch:
            break

        last_appid = str(batch[-1]["appid"])
        yield batch
        if len(batch) < batch_size:
            break


def create_index(dimensions: int, index_kind: str):
    if index_kind == "flat_ip":
        return faiss.IndexFlatIP(dimensions)
    if index_kind == "sq_fp16":
        return faiss.IndexScalarQuantizer(
            dimensions,
            faiss.ScalarQuantizer.QT_fp16,
            faiss.METRIC_INNER_PRODUCT,
        )
    raise ValueError(f"Unsupported index kind: {index_kind}")


def reset_artifact_dir(artifact_dir: Path) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ("games-*.index", "games-*.appids.json"):
        for path in artifact_dir.glob(pattern):
            path.unlink(missing_ok=True)
    for path in (artifact_dir / "manifest.json", artifact_dir / "games.index", artifact_dir / "games_appids.json"):
        path.unlink(missing_ok=True)


def flush_shard(
    artifact_dir: Path,
    dimensions: int,
    index_kind: str,
    shard_number: int,
    shard_appids: list[str],
    shard_vectors: list[np.ndarray],
) -> dict[str, object]:
    if not shard_appids or not shard_vectors:
        raise ValueError("Shard cannot be flushed without vectors.")

    index = create_index(dimensions, index_kind)
    shard_matrix = np.vstack(shard_vectors).astype("float32", copy=False)
    index.add(shard_matrix)

    index_file = f"games-{shard_number:04d}.index"
    mapping_file = f"games-{shard_number:04d}.appids.json"
    faiss.write_index(index, str(artifact_dir / index_file))
    (artifact_dir / mapping_file).write_text(json.dumps(shard_appids), encoding="utf-8")
    print(f"Wrote shard {shard_number:04d}: {len(shard_appids)} vectors")

    del shard_matrix, index
    gc.collect()
    return {
        "index_file": index_file,
        "mapping_file": mapping_file,
        "vector_count": len(shard_appids),
    }


def main() -> None:
    args = parse_args()
    if args.batch_size <= 0 or args.shard_size <= 0:
        raise ValueError("--batch-size and --shard-size must be positive.")

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required.")

    supabase = create_client(settings.supabase_url, settings.supabase_key)
    reset_artifact_dir(settings.faiss_artifact_dir)

    shard_appids: list[str] = []
    shard_vectors: list[np.ndarray] = []
    shard_number = 0
    indexed_count = 0
    shards: list[dict[str, object]] = []

    for batch in iter_embedding_rows(supabase, args.batch_size):
        batch_appids: list[str] = []
        batch_vectors: list[np.ndarray] = []
        for row in batch:
            appid = str(row["appid"])
            raw_vector = row.get("embedding_vector")
            if not raw_vector:
                continue
            batch_appids.append(appid)
            batch_vectors.append(normalize_vector(raw_vector, settings.openai_embedding_dimensions))

        if not batch_vectors:
            continue

        shard_appids.extend(batch_appids)
        shard_vectors.extend(batch_vectors)
        indexed_count += len(batch_appids)
        print(f"Indexed {indexed_count} embedding rows...")
        del batch_vectors, batch_appids, batch

        while len(shard_appids) >= args.shard_size:
            current_appids = shard_appids[: args.shard_size]
            current_vectors = shard_vectors[: args.shard_size]
            shards.append(
                flush_shard(
                    settings.faiss_artifact_dir,
                    settings.openai_embedding_dimensions,
                    args.index_kind,
                    shard_number,
                    current_appids,
                    current_vectors,
                )
            )
            shard_number += 1
            shard_appids = shard_appids[args.shard_size :]
            shard_vectors = shard_vectors[args.shard_size :]
            gc.collect()

        gc.collect()

    if not indexed_count:
        raise RuntimeError("No valid embedding vectors were available to index.")

    if shard_appids:
        shards.append(
            flush_shard(
                settings.faiss_artifact_dir,
                settings.openai_embedding_dimensions,
                args.index_kind,
                shard_number,
                shard_appids,
                shard_vectors,
            )
        )

    settings.faiss_manifest_path.write_text(
        json.dumps(
            {
                "vector_count": indexed_count,
                "dimensions": settings.openai_embedding_dimensions,
                "index_kind": args.index_kind,
                "shard_size": args.shard_size,
                "shards": shards,
                "built_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Wrote manifest: {settings.faiss_manifest_path}")
    print(f"Indexed vectors: {indexed_count}")


if __name__ == "__main__":
    main()
