from __future__ import annotations

import re
import time
from typing import Any

from .llm import AnswerGenerator
from .store import KnowledgeStore

LIST_PATTERN = re.compile(r"(문서|자료).*(목록|리스트)|무슨 문서|어떤 자료")


class KnowledgeAgent:
    """Small, observable agent that routes requests to knowledge tools."""

    def __init__(self, store: KnowledgeStore, generator: AnswerGenerator, top_k: int = 5):
        self.store = store
        self.generator = generator
        self.top_k = top_k

    def ask(self, question: str, top_k: int | None = None) -> dict[str, Any]:
        question = question.strip()
        if not question:
            raise ValueError("question is required")
        started = time.monotonic()

        if LIST_PATTERN.search(question):
            documents = self.store.list_documents()
            answer = (
                "등록된 문서가 없습니다."
                if not documents
                else "등록된 문서입니다:\n"
                + "\n".join(f"- {item['title']} ({item['source']})" for item in documents)
            )
            return {
                "answer": answer,
                "mode": "tool",
                "citations": [],
                "trace": [
                    {"step": "route", "tool": "knowledge_list_documents"},
                    {"step": "observe", "documents": len(documents)},
                ],
                "latency_ms": round((time.monotonic() - started) * 1000),
            }

        limit = min(max(top_k or self.top_k, 1), 10)
        results = self.store.search(question, limit)
        answer, mode = self.generator.generate(question, results)
        citations = [
            {
                "index": index,
                "document_id": item.document_id,
                "chunk_id": item.chunk_id,
                "title": item.title,
                "source": item.source,
                "score": item.score,
                "excerpt": " ".join(item.content.split())[:240],
            }
            for index, item in enumerate(results, 1)
        ]
        return {
            "answer": answer,
            "mode": mode,
            "citations": citations,
            "trace": [
                {"step": "route", "tool": "knowledge_search"},
                {"step": "retrieve", "matches": len(results)},
                {"step": "generate", "mode": mode},
            ],
            "latency_ms": round((time.monotonic() - started) * 1000),
        }
