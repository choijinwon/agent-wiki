from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from contextlib import contextmanager

from .chunking import chunk_text, normalize_text

TOKEN_RE = re.compile(r"[0-9A-Za-z_가-힣]{2,}")
VECTOR_SIZE = 192


@dataclass(frozen=True)
class SearchResult:
    chunk_id: str
    document_id: str
    title: str
    source: str
    content: str
    score: float
    ordinal: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def _features(text: str) -> list[str]:
    words = _tokens(text)
    grams: list[str] = []
    for word in words:
        for width in (2, 3):
            grams.extend(word[index : index + width] for index in range(max(0, len(word) - width + 1)))
    return words + grams


def _embedding(text: str) -> list[float]:
    vector = [0.0] * VECTOR_SIZE
    for feature in _features(text):
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % VECTOR_SIZE
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))


class KnowledgeStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    chunk_id UNINDEXED,
                    content,
                    tokenize='unicode61'
                );
                """
            )

    def add_document(
        self,
        *,
        title: str,
        content: str,
        source: str = "manual",
        chunk_size: int = 900,
        chunk_overlap: int = 120,
    ) -> dict[str, Any]:
        title = normalize_text(title)
        content = normalize_text(content)
        source = normalize_text(source) or "manual"
        if not title:
            raise ValueError("title is required")
        if not content:
            raise ValueError("content is required")

        identity = hashlib.sha256(f"{source}\0{title}".encode()).hexdigest()[:20]
        parts = chunk_text(content, chunk_size, chunk_overlap)
        created_at = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            old_ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM chunks WHERE document_id = ?", (identity,)
                )
            ]
            if old_ids:
                connection.executemany(
                    "DELETE FROM chunks_fts WHERE chunk_id = ?",
                    [(chunk_id,) for chunk_id in old_ids],
                )
            connection.execute("DELETE FROM documents WHERE id = ?", (identity,))
            connection.execute(
                "INSERT INTO documents(id, title, source, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (identity, title, source, content, created_at),
            )
            for ordinal, part in enumerate(parts):
                chunk_id = f"{identity}:{ordinal}"
                connection.execute(
                    "INSERT INTO chunks(id, document_id, ordinal, content, embedding) VALUES (?, ?, ?, ?, ?)",
                    (chunk_id, identity, ordinal, part, json.dumps(_embedding(part))),
                )
                connection.execute(
                    "INSERT INTO chunks_fts(chunk_id, content) VALUES (?, ?)",
                    (chunk_id, part),
                )
        return {
            "id": identity,
            "title": title,
            "source": source,
            "chunk_count": len(parts),
            "created_at": created_at,
        }

    def list_documents(self) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT d.id, d.title, d.source, d.created_at, COUNT(c.id) AS chunk_count
                FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
                GROUP BY d.id ORDER BY d.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_document(self, document_id: str) -> bool:
        with self._connection() as connection:
            chunk_ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM chunks WHERE document_id = ?", (document_id,)
                )
            ]
            if chunk_ids:
                connection.executemany(
                    "DELETE FROM chunks_fts WHERE chunk_id = ?",
                    [(chunk_id,) for chunk_id in chunk_ids],
                )
            cursor = connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            return cursor.rowcount > 0

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        query = normalize_text(query)
        if not query:
            return []
        limit = min(max(limit, 1), 20)
        terms = list(dict.fromkeys(_tokens(query)))[:16]
        query_features = set(_features(query))
        query_vector = _embedding(query)

        with self._connection() as connection:
            lexical: dict[str, float] = {}
            if terms:
                expression = " OR ".join(f'"{term.replace(chr(34), "")}"' for term in terms)
                try:
                    rows = connection.execute(
                        "SELECT chunk_id, bm25(chunks_fts) AS rank FROM chunks_fts "
                        "WHERE chunks_fts MATCH ? ORDER BY rank LIMIT 80",
                        (expression,),
                    ).fetchall()
                    for position, row in enumerate(rows):
                        lexical[row["chunk_id"]] = 1.0 / (1.0 + position)
                except sqlite3.OperationalError:
                    lexical = {}

            rows = connection.execute(
                """
                SELECT c.id, c.document_id, c.ordinal, c.content, c.embedding,
                       d.title, d.source
                FROM chunks c JOIN documents d ON d.id = c.document_id
                """
            ).fetchall()

        query_terms = set(terms)
        ranked: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            chunk_terms = set(_tokens(row["content"]))
            overlap = len(query_terms & chunk_terms) / max(len(query_terms), 1)
            chunk_features = set(_features(row["content"]))
            subword = len(query_features & chunk_features) / max(len(query_features), 1)
            semantic = max(subword, max(0.0, _cosine(query_vector, json.loads(row["embedding"]))))
            fts = lexical.get(row["id"], 0.0)
            score = 0.45 * fts + 0.35 * overlap + 0.20 * semantic
            if score > 0.01:
                ranked.append((score, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            SearchResult(
                chunk_id=row["id"],
                document_id=row["document_id"],
                title=row["title"],
                source=row["source"],
                content=row["content"],
                score=round(score, 4),
                ordinal=row["ordinal"],
            )
            for score, row in ranked[:limit]
        ]

    def stats(self) -> dict[str, int]:
        with self._connection() as connection:
            documents = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            chunks = connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return {"documents": documents, "chunks": chunks}
