from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from app.schemas.recommendation import IntentConstraints, ParsedUserIntent
from app.services.recommendation.faiss_index import SemanticSearchHit
from app.services.recommendation import retrieve


class FakeRpcRequest:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return SimpleNamespace(data=self._payload)


class FakeGamesQuery:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.in_calls: list[tuple[str, list[str]]] = []
        self.gte_calls: list[tuple[str, int]] = []

    def select(self, *_args, **_kwargs):
        return self

    def in_(self, field: str, values: list[str]):
        self.in_calls.append((field, values))
        return self

    def gte(self, field: str, value: int):
        self.gte_calls.append((field, value))
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class FakeSupabaseClient:
    def __init__(self, rpc_rows: list[dict], table_rows: list[dict]):
        self.rpc_rows = rpc_rows
        self.rpc_calls: list[tuple[str, dict[str, object]]] = []
        self.games_query = FakeGamesQuery(table_rows)

    def rpc(self, name: str, params: dict[str, object]):
        self.rpc_calls.append((name, params))
        return FakeRpcRequest(self.rpc_rows)

    def table(self, name: str):
        if name != "games":
            raise AssertionError(f"Unexpected table requested: {name}")
        return self.games_query


class RetrieveTests(unittest.TestCase):
    def test_fetch_embedding_candidates_falls_back_to_supabase(self) -> None:
        intent = ParsedUserIntent(
            free_text_intent="cozy indie game",
            constraints=IntentConstraints(min_total_reviews=50),
        )
        supabase = FakeSupabaseClient(
            rpc_rows=[{"appid": "10", "similarity": 0.88}],
            table_rows=[{"appid": "10", "name": "A Short Hike"}],
        )

        fake_index = SimpleNamespace(
            search=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("missing manifest"))
        )

        with (
            patch.object(retrieve, "get_settings", return_value=SimpleNamespace(openai_api_key="test-key")),
            patch.object(retrieve, "create_query_embedding", return_value=[0.0, 0.0]),
            patch.object(retrieve, "get_faiss_semantic_index", return_value=fake_index),
        ):
            games, scores, routes = retrieve.fetch_embedding_candidates(
                supabase,
                intent,
                ownership_filtered_user_id="user-123",
            )

        self.assertEqual(["10"], [game.appid for game in games])
        self.assertEqual({"10": 0.88}, scores)
        self.assertEqual({"10": [retrieve.SUPABASE_FALLBACK_ROUTE]}, routes)
        self.assertEqual(1, len(supabase.rpc_calls))
        rpc_name, rpc_params = supabase.rpc_calls[0]
        self.assertEqual(retrieve.SUPABASE_MATCH_RPC, rpc_name)
        self.assertEqual(50, rpc_params["minimum_total_reviews"])
        self.assertEqual("user-123", rpc_params["excluded_user_id"])

    def test_fetch_embedding_candidates_prefers_faiss_when_available(self) -> None:
        intent = ParsedUserIntent(free_text_intent="tactical RPG")
        supabase = FakeSupabaseClient(
            rpc_rows=[],
            table_rows=[{"appid": "42", "name": "Into the Breach"}],
        )
        fake_index = SimpleNamespace(
            search=lambda *_args, **_kwargs: [
                SemanticSearchHit(appid="42", similarity=0.91),
            ]
        )

        with (
            patch.object(retrieve, "get_settings", return_value=SimpleNamespace(openai_api_key="test-key")),
            patch.object(retrieve, "create_query_embedding", return_value=[0.0, 0.0]),
            patch.object(retrieve, "get_faiss_semantic_index", return_value=fake_index),
        ):
            games, scores, routes = retrieve.fetch_embedding_candidates(supabase, intent)

        self.assertEqual(["42"], [game.appid for game in games])
        self.assertEqual({"42": 0.91}, scores)
        self.assertEqual({"42": [retrieve.FAISS_ROUTE]}, routes)
        self.assertEqual([], supabase.rpc_calls)


if __name__ == "__main__":
    unittest.main()
