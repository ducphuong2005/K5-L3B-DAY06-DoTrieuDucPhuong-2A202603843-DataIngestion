"""Real embedding provider adapter using OpenAI-compatible API (ShopAI / OpenAI / OpenRouter)."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Protocol

MODEL_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
    "text-embedding-3-large": 3072,
}

MODEL_PRICE_PER_1M_TOKENS: dict[str, float] = {
    "text-embedding-3-small": 0.02,
    "text-embedding-ada-002": 0.10,
    "text-embedding-3-large": 0.13,
}


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """OpenAI-compatible API embedder (configured for ShopAI / OpenAI). Never falls back to mock vectors."""

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        batch_size: int = 32,
    ) -> None:
        self.model_name = (model_name or os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small").strip()
        self.api_key = (
            api_key
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or ""
        ).strip()
        self.base_url = (
            base_url
            or os.getenv("OPENAI_BASE_URL")
            or ("https://openrouter.ai/api/v1" if os.getenv("OPENROUTER_API_KEY") else "https://api.shopaikey.com/v1")
        ).rstrip("/")
        self.batch_size = batch_size

        if not self.api_key:
            raise RuntimeError(
                "Missing API key: set OPENAI_API_KEY in starter/.env before initializing MyEmbedder. "
                "Refusing to fall back to mock/random vectors per RULES.md."
            )

        self.dimensions = MODEL_DIMENSIONS.get(self.model_name, 1536)
        self.total_prompt_tokens = 0
        self.total_requests = 0

        # Probe the endpoint with a single test string to verify connectivity and exact dimensions
        probe_vec = self._call_api(["dimension check"])[0]
        if not probe_vec or not isinstance(probe_vec, list):
            raise RuntimeError(f"Embedding provider returned invalid vector for model {self.model_name}")
        self.dimensions = len(probe_vec)

    def _call_api(self, inputs: list[str]) -> list[list[float]]:
        if not inputs:
            return []

        url = f"{self.base_url}/embeddings"
        payload = json.dumps({
            "model": self.model_name,
            "input": inputs,
        }).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "OpenAI/Python 1.50.0",
        }

        last_err: Exception | None = None
        for attempt in range(1, 4):
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                data_items = sorted(body.get("data", []), key=lambda item: item.get("index", 0))
                vectors = [[float(x) for x in item["embedding"]] for item in data_items]
                if len(vectors) != len(inputs):
                    raise RuntimeError(
                        f"Expected {len(inputs)} embeddings from {url}, got {len(vectors)}"
                    )
                usage = body.get("usage") or {}
                self.total_prompt_tokens += int(usage.get("prompt_tokens") or usage.get("total_tokens") or 0)
                self.total_requests += 1
                return vectors
            except urllib.error.HTTPError as exc:
                err_body = ""
                try:
                    err_body = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                last_err = RuntimeError(
                    f"HTTP {exc.code} from {url} (attempt {attempt}/3): {err_body[:300]}"
                )
                if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(1.5 * attempt)
                    continue
                raise last_err from exc
            except Exception as exc:
                last_err = exc
                if attempt < 3:
                    time.sleep(1.5 * attempt)
                    continue
                raise RuntimeError(f"Embedding API request to {url} failed: {exc}") from exc

        raise RuntimeError(f"Embedding API request failed: {last_err}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        if not texts:
            return []
        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            batch_vecs = self._call_api(batch)
            for vec in batch_vecs:
                if len(vec) != self.dimensions:
                    raise RuntimeError(
                        f"Dimension mismatch: expected {self.dimensions}, got {len(vec)}"
                    )
            all_vectors.extend(batch_vecs)
        return all_vectors

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        if not question or not question.strip():
            raise ValueError("Query question must be a non-empty string")
        vec = self._call_api([question.strip()])[0]
        if len(vec) != self.dimensions:
            raise RuntimeError(
                f"Query vector dimension mismatch: expected {self.dimensions}, got {len(vec)}"
            )
        return vec

    def estimated_cost_usd(self) -> float:
        price_per_1m = MODEL_PRICE_PER_1M_TOKENS.get(self.model_name, 0.02)
        return round((self.total_prompt_tokens / 1_000_000.0) * price_per_1m, 6)
