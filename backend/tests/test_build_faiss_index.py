from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_faiss_index.py"
MODULE_SPEC = importlib.util.spec_from_file_location("build_faiss_index", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load module from {MODULE_PATH}")
build_faiss_index = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(build_faiss_index)


class FakeRpcRequest:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return SimpleNamespace(data=self._payload)


class FakeSupabaseClient:
    def __init__(self, payloads: list[object]):
        self._payloads = list(payloads)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def rpc(self, name: str, params: dict[str, object]):
        if not self._payloads:
            raise AssertionError("No fake RPC payloads remain.")
        self.calls.append((name, params))
        return FakeRpcRequest(self._payloads.pop(0))


class BuildFaissIndexTests(unittest.TestCase):
    def test_iter_embedding_rows_pages_through_rpc(self) -> None:
        client = FakeSupabaseClient(
            [
                [
                    {"appid": "10", "embedding_vector_text": "[1.0, 0.0]"},
                    {"appid": "20", "embedding_vector_text": "[0.0, 1.0]"},
                ],
                [
                    {"appid": "30", "embedding_vector_text": "[0.5, 0.5]"},
                ],
            ]
        )

        batches = list(build_faiss_index.iter_embedding_rows(client, 2))

        self.assertEqual(2, len(batches))
        self.assertEqual(
            [
                (
                    build_faiss_index.EMBEDDING_EXPORT_RPC,
                    {"after_appid": None, "batch_count": 2},
                ),
                (
                    build_faiss_index.EMBEDDING_EXPORT_RPC,
                    {"after_appid": "20", "batch_count": 2},
                ),
            ],
            client.calls,
        )

    def test_fetch_embedding_batch_wraps_rpc_failures(self) -> None:
        client = FakeSupabaseClient([RuntimeError("boom")])

        with self.assertRaisesRegex(RuntimeError, "Apply the latest Supabase migrations"):
            build_faiss_index.fetch_embedding_batch(client, 100, None)

    def test_main_writes_manifest_and_shards_from_rpc_batches(self) -> None:
        artifact_root = Path(__file__).resolve().parent / "_tmp_faiss_artifacts"
        artifact_dir = artifact_root / uuid.uuid4().hex
        artifact_dir.mkdir(parents=True, exist_ok=False)
        try:
            settings = SimpleNamespace(
                supabase_url="https://example.supabase.co",
                supabase_key="service-role-key",
                faiss_artifact_dir=artifact_dir,
                faiss_manifest_path=artifact_dir / "manifest.json",
                openai_embedding_dimensions=2,
            )
            client = FakeSupabaseClient(
                [
                    [
                        {"appid": "10", "embedding_vector_text": "[1.0, 0.0]"},
                        {"appid": "20", "embedding_vector_text": "[0.0, 1.0]"},
                    ],
                    [
                        {"appid": "30", "embedding_vector_text": "[0.5, 0.5]"},
                    ],
                ]
            )
            args = SimpleNamespace(batch_size=2, shard_size=2, index_kind="flat_ip")

            with (
                patch.object(build_faiss_index, "parse_args", return_value=args),
                patch.object(build_faiss_index, "get_settings", return_value=settings),
                patch.object(build_faiss_index, "create_client", return_value=client),
                patch.object(
                    build_faiss_index.faiss,
                    "write_index",
                    side_effect=lambda index, path: Path(path).write_bytes(b"test-index"),
                ),
            ):
                build_faiss_index.main()

            manifest = json.loads(settings.faiss_manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(3, manifest["vector_count"])
            self.assertEqual(2, manifest["dimensions"])
            self.assertEqual("flat_ip", manifest["index_kind"])
            self.assertEqual(2, len(manifest["shards"]))

            for shard in manifest["shards"]:
                self.assertTrue((artifact_dir / shard["index_file"]).exists())
                self.assertTrue((artifact_dir / shard["mapping_file"]).exists())
        finally:
            shutil.rmtree(artifact_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
