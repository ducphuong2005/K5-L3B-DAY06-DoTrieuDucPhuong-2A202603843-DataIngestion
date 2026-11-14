"""Store and search vectors using PostgreSQL + pgvector with exact cosine distance and metadata filtering."""
from __future__ import annotations

import json
from typing import Any

import psycopg

from .models import Chunk

PERMITTED_FILTER_KEYS = {
    "section",
    "chapter_title",
    "book_number",
    "language",
    "document_type",
    "year",
    "category",
    "page_id",
}


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{float(v):.8f}" for v in vec) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url or not database_url.strip():
            raise ValueError("database_url must be provided")
        if dimensions <= 0:
            raise ValueError("dimensions must be a positive integer")
        self.database_url = database_url.strip()
        self.dimensions = int(dimensions)

    def create_schema(self) -> None:
        """Create pgvector extension and rag_chunks table with vector column and metadata indexes."""
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                # Check if table exists with a different vector dimension
                cur.execute(
                    """
                    SELECT format_type(a.atttypid, a.atttypmod)
                    FROM pg_attribute a
                    JOIN pg_class c ON a.attrelid = c.oid
                    WHERE c.relname = 'rag_chunks' AND a.attname = 'embedding';
                    """
                )
                row = cur.fetchone()
                expected_type = f"vector({self.dimensions})"
                if row and row[0] != expected_type:
                    cur.execute("DROP TABLE rag_chunks;")

                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS rag_chunks (
                        strategy TEXT NOT NULL,
                        chunk_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        page INTEGER NOT NULL,
                        text TEXT NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        embedding vector({self.dimensions}) NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (strategy, chunk_id)
                    );
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rag_chunks_strategy_doc ON rag_chunks (strategy, document_id);"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS idx_rag_chunks_metadata_gin ON rag_chunks USING GIN (metadata);"
                )
            conn.commit()

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        """Validate lengths/dimensions, remove obsolete chunks for updated documents, and upsert idempotently."""
        if not strategy or not strategy.strip():
            raise ValueError("strategy must be a non-empty string")
        if len(chunks) != len(vectors):
            raise ValueError(
                f"Length mismatch: got {len(chunks)} chunks and {len(vectors)} vectors"
            )
        if not chunks:
            return

        for idx, vec in enumerate(vectors):
            if len(vec) != self.dimensions:
                raise ValueError(
                    f"Vector at index {idx} has dimension {len(vec)}, expected {self.dimensions}"
                )

        doc_ids = sorted({c.document_id for c in chunks})
        incoming_chunk_ids = [c.chunk_id for c in chunks]

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                # Remove obsolete chunks belonging to the re-ingested document_ids that are no longer present
                cur.execute(
                    """
                    DELETE FROM rag_chunks
                    WHERE strategy = %s
                      AND document_id = ANY(%s)
                      AND NOT (chunk_id = ANY(%s));
                    """,
                    (strategy, doc_ids, incoming_chunk_ids),
                )

                for chunk, vec in zip(chunks, vectors):
                    meta = dict(chunk.metadata)
                    meta.setdefault("document_id", chunk.document_id)
                    meta.setdefault("source", chunk.source)
                    meta.setdefault("page", chunk.page)

                    cur.execute(
                        """
                        INSERT INTO rag_chunks (
                            strategy, chunk_id, document_id, source, page, text, metadata, embedding, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector, NOW())
                        ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                            document_id = EXCLUDED.document_id,
                            source = EXCLUDED.source,
                            page = EXCLUDED.page,
                            text = EXCLUDED.text,
                            metadata = EXCLUDED.metadata,
                            embedding = EXCLUDED.embedding,
                            updated_at = NOW();
                        """,
                        (
                            strategy,
                            chunk.chunk_id,
                            chunk.document_id,
                            chunk.source,
                            int(chunk.page),
                            chunk.text,
                            json.dumps(meta, ensure_ascii=False),
                            _vector_literal(vec),
                        ),
                    )
            conn.commit()

    def count_chunks(self, strategy: str) -> int:
        """Return total stored chunks for a strategy."""
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM rag_chunks WHERE strategy = %s;", (strategy,))
                row = cur.fetchone()
                return int(row[0]) if row else 0

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Filter permitted metadata in SQL, rank by exact cosine distance (<=>), and return top-k hits."""
        if len(query_vector) != self.dimensions:
            raise ValueError(
                f"query_vector dimension {len(query_vector)} does not match store dimension {self.dimensions}"
            )
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        vec_str = _vector_literal(query_vector)
        where_clauses = ["strategy = %s"]
        params: list[Any] = [vec_str, strategy]

        if filters:
            for key, val in filters.items():
                if key not in PERMITTED_FILTER_KEYS:
                    raise ValueError(f"Unsupported or unpermitted metadata filter key: {key!r}")
                if val is None:
                    continue
                where_clauses.append("metadata ->> %s = %s")
                params.extend([str(key), str(val)])

        params.extend([vec_str, int(top_k)])
        where_sql = " AND ".join(where_clauses)

        query_sql = f"""
            SELECT
                chunk_id,
                document_id,
                source,
                page,
                text,
                metadata,
                (embedding <=> %s::vector) AS cosine_distance
            FROM rag_chunks
            WHERE {where_sql}
            ORDER BY embedding <=> %s::vector ASC, chunk_id ASC
            LIMIT %s;
        """

        results: list[dict[str, Any]] = []
        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query_sql, params)
                rows = cur.fetchall()
                for rank, (chunk_id, doc_id, source, page, text, metadata, cos_dist) in enumerate(rows, start=1):
                    dist = float(cos_dist)
                    score = round(1.0 - dist, 6)
                    meta_dict = metadata if isinstance(metadata, dict) else json.loads(metadata)
                    meta_dict.setdefault("document_id", doc_id)
                    meta_dict.setdefault("source", source)
                    meta_dict.setdefault("page", int(page))
                    results.append({
                        "rank": rank,
                        "chunk_id": chunk_id,
                        "document_id": doc_id,
                        "source": source,
                        "page": int(page),
                        "text": text,
                        "score": score,
                        "cosine_distance": round(dist, 6),
                        "metadata": meta_dict,
                    })
        return results
